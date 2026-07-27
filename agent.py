import operator
import sqlite3
from typing import Annotated

from dotenv import load_dotenv
from langchain_anthropic import ChatAnthropic
from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_core.messages import ToolMessage
from langchain_core.tools import tool
from langchain_huggingface import HuggingFaceEmbeddings
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.prebuilt import InjectedState, ToolNode, tools_condition
from sqlmodel import Field, Session, SQLModel, create_engine, select

load_dotenv()

# ---------- stato condiviso del grafo ----------

class AgentState(MessagesState):
    username: str
    route: str
    research_topic: str
    sources: Annotated[list[str], operator.add]
    critic_feedback: str
    critic_approved: bool
    research_iterations: int
    memory_hit: bool


# ---------- database: task ----------

class Task(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    username: str = Field(index=True)
    description: str
    done: bool = False
    due_date: str | None = None

tasks_engine = create_engine("sqlite:///tasks.db")
SQLModel.metadata.create_all(tasks_engine)


# ---------- database: report di ricerca (memoria) ----------

class ResearchReport(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    username: str = Field(index=True)
    topic: str = Field(index=True)
    report: str
    sources: str

reports_engine = create_engine("sqlite:///reports.db")
SQLModel.metadata.create_all(reports_engine)


# ---------- database vettoriale: note personali ----------

embeddings = HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2")

vector_store = Chroma(
    collection_name="notes",
    embedding_function=embeddings,
    persist_directory="./notes_db"
)

def split_text(text, chunk_size=500, overlap=50):
    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunks.append(text[start:end])
        start = end - overlap
    return chunks


# ---------- modello ----------

llm = ChatAnthropic(model="claude-sonnet-4-5")
web_search = {"type": "web_search_20250305", "name": "web_search", "max_uses": 5}


# ---------- tool: task manager ----------

@tool
def add_task(description: str, state: Annotated[AgentState, InjectedState], due_date: str | None = None) -> str:
    """Add a new personal task or reminder for the user. due_date is optional free text, e.g. 'tomorrow'."""
    username = state["username"]
    with Session(tasks_engine) as session:
        task = Task(username=username, description=description, due_date=due_date)
        session.add(task)
        session.commit()
        session.refresh(task)
        return f"Task added with id {task.id}: {description}"

@tool
def list_tasks(state: Annotated[AgentState, InjectedState], status: str = "pending") -> str:
    """List the user's tasks. status can be 'pending', 'done', or 'all'."""
    username = state["username"]
    with Session(tasks_engine) as session:
        query = select(Task).where(Task.username == username)
        if status == "pending":
            query = query.where(Task.done == False)
        elif status == "done":
            query = query.where(Task.done == True)
        tasks = session.exec(query).all()
        if not tasks:
            return "No tasks found."
        lines = []
        for t in tasks:
            line = f"[{t.id}] {t.description}"
            if t.due_date:
                line += f" (due: {t.due_date})"
            if t.done:
                line += " - done"
            lines.append(line)
        return "\n".join(lines)

@tool
def complete_task(task_id: int, state: Annotated[AgentState, InjectedState]) -> str:
    """Mark a task as completed, given its numeric id."""
    username = state["username"]
    with Session(tasks_engine) as session:
        task = session.get(Task, task_id)
        if not task or task.username != username:
            return "Task not found."
        task.done = True
        session.add(task)
        session.commit()
        return f"Task {task_id} marked as done."


# ---------- tool: note personali (RAG) ----------

@tool
def search_notes(query: str, state: Annotated[AgentState, InjectedState]) -> str:
    """Search the user's personal notes and documents for information relevant to the query.
    Always use this tool whenever the user asks about their own notes, uploaded documents,
    grades, or any personal information that might be stored in their notes — try this
    before ever saying you don't have access to their files."""
    username = state["username"]
    results = vector_store.similarity_search(query, k=4, filter={"username": username})
    print(f"[SEARCH_NOTES] query: {query!r} username: {username!r} risultati trovati: {len(results)}")
    if not results:
        return "No relevant notes found."
    return "\n\n".join(doc.page_content for doc in results)


# ---------- reparto: task manager ----------

task_tools = [add_task, list_tasks, complete_task]
llm_tasks = llm.bind_tools(task_tools)

def task_manager(state: AgentState):
    answer = llm_tasks.invoke(state["messages"])
    return {"messages": [answer]}


# ---------- reparto: note personali ----------

notes_tools = [search_notes]
llm_notes = llm.bind_tools(notes_tools)

def notes_agent(state: AgentState):
    last_message = state["messages"][-1]
    if isinstance(last_message, ToolMessage):
        answer = llm_notes.invoke(state["messages"])
    else:
        forced_llm = llm.bind_tools(notes_tools, tool_choice={"type": "tool", "name": "search_notes"})
        answer = forced_llm.invoke(state["messages"])
    return {"messages": [answer]}


# ---------- reparto: ricerca / report (sotto-sistema con ciclo critic <-> research) ----------

def memory_check(state: AgentState):
    topic = state["messages"][-1].content
    username = state["username"]
    with Session(reports_engine) as session:
        existing = session.exec(
            select(ResearchReport).where(
                ResearchReport.username == username,
                ResearchReport.topic == topic
            )
        ).first()
    if existing:
        print(f"[MEMORY] trovato report esistente per {topic!r}, lo riuso")
        return {"messages": [{"role": "assistant", "content": existing.report}], "research_topic": topic, "memory_hit": True}
    print(f"[MEMORY] nessun report esistente per {topic!r}, avvio ricerca nuova")
    return {"research_topic": topic, "memory_hit": False}

def memory_decision(state: AgentState):
    return "found" if state.get("memory_hit") else "not_found"

def research_dispatch(state: AgentState):
    topic = state.get("research_topic") or state["messages"][-1].content
    iterations = state.get("research_iterations", 0) + 1
    return {"research_topic": topic, "research_iterations": iterations}

def web_researcher(state: AgentState):
    topic = state["research_topic"]
    feedback = state.get("critic_feedback", "")
    query = f"{topic}. {feedback}" if feedback else topic
    llm_web = llm.bind_tools([web_search])
    result = llm_web.invoke([{"role": "user", "content": f"Search the web about: {query}. Summarize concisely."}])
    if isinstance(result.content, str):
        text = result.content
    else:
        text = "\n".join(b.get("text", "") for b in result.content if isinstance(b, dict) and b.get("type") == "text")
    return {"sources": [f"[Web search] {text}"]}

def notes_researcher(state: AgentState):
    topic = state["research_topic"]
    feedback = state.get("critic_feedback", "")
    query = f"{topic}. {feedback}" if feedback else topic
    results = vector_store.similarity_search(query, k=4, filter={"username": state["username"]})
    if not results:
        text = "No relevant personal notes found."
    else:
        text = "\n\n".join(doc.page_content for doc in results)
    return {"sources": [f"[Personal notes] {text}"]}

def critic(state: AgentState):
    topic = state["research_topic"]
    sources_text = "\n\n".join(state.get("sources", []))
    iterations = state.get("research_iterations", 0)

    prompt = (
        f"You are reviewing research collected on the topic: {topic}\n\n"
        f"Sources collected so far:\n{sources_text}\n\n"
        "Evaluate whether this is sufficient and coherent to write a solid report. "
        "If there are gaps, contradictions, or missing angles, respond starting with 'INSUFFICIENT:' "
        "followed by one specific, targeted follow-up question to search for next. "
        "If the information is sufficient, respond with exactly 'SUFFICIENT'."
    )
    response = llm.invoke([{"role": "user", "content": prompt}])
    text = response.content.strip()
    print(f"[CRITIC] iterazione {iterations} -> {text[:100]}")

    if text.startswith("SUFFICIENT") or iterations >= 3:
        return {"critic_approved": True, "critic_feedback": ""}
    feedback = text.replace("INSUFFICIENT:", "").strip()
    return {"critic_approved": False, "critic_feedback": feedback}

def critic_decision(state: AgentState):
    return "approved" if state.get("critic_approved") else "retry"

def writer(state: AgentState):
    topic = state["research_topic"]
    sources_text = "\n\n".join(state.get("sources", []))
    prompt = (
        f"Write a well-structured report on: {topic}\n\n"
        f"Use only the following sources, each already labeled with its origin:\n\n{sources_text}\n\n"
        "Structure the report with: an introduction, a comparison table if relevant, "
        "a pros/cons section, and a conclusion. For every claim, indicate whether it comes "
        "from '[Web search]' or '[Personal notes]' — never state something without grounding it "
        "in one of these sources."
    )
    answer = llm.invoke([{"role": "user", "content": prompt}])
    return {"messages": [answer]}

def memory_save(state: AgentState):
    topic = state["research_topic"]
    username = state["username"]
    report_text = state["messages"][-1].content
    sources_text = "\n\n".join(state.get("sources", []))
    with Session(reports_engine) as session:
        record = ResearchReport(username=username, topic=topic, report=report_text, sources=sources_text)
        session.add(record)
        session.commit()
    print(f"[MEMORY] report salvato per {topic!r}")
    return {}


# ---------- reparto: generico ----------

def general(state: AgentState):
    answer = llm.invoke(state["messages"])
    return {"messages": [answer]}


# ---------- supervisore ----------

def router(state: AgentState):
    recent = state["messages"][-6:]
    context = "\n".join(f"- {m.content}" for m in recent if isinstance(m.content, str))
    prompt = (
        "Classify the LATEST user request into exactly one category: "
        "task, notes, research, general. Use the recent conversation as context — "
        "short follow-up messages (e.g. 'and now?', 'yes, that one') should usually stay "
        "in the same category as the topic being discussed.\n\n"
        "- 'task': adding, listing, or completing personal to-dos/reminders\n"
        "- 'notes': questions about the user's personal notes/documents\n"
        "- 'research': requests for a report, comparison, or in-depth research\n"
        "- 'general': anything else\n\n"
        f"Recent conversation:\n{context}\n\n"
        "Reply with only the category word for the latest message."
    )
    response = llm.invoke([{"role": "user", "content": prompt}])
    category = response.content.strip().lower()
    if category not in ["task", "notes", "research", "general"]:
        category = "general"
    print(f"[ROUTER] messaggio: {state['messages'][-1].content!r} -> categoria: {category}")
    return {"route": category}

def route_decision(state: AgentState):
    return state.get("route", "general")


# ---------- grafo ----------

graph = StateGraph(AgentState)

graph.add_node("router", router)

graph.add_node("task_manager", task_manager)
graph.add_node("task_tools", ToolNode(task_tools))

graph.add_node("notes_agent", notes_agent)
graph.add_node("notes_tools", ToolNode(notes_tools))

graph.add_node("memory_check", memory_check)
graph.add_node("research_dispatch", research_dispatch)
graph.add_node("web_researcher", web_researcher)
graph.add_node("notes_researcher", notes_researcher)
graph.add_node("critic", critic)
graph.add_node("writer", writer)
graph.add_node("memory_save", memory_save)

graph.add_node("general", general)

graph.add_edge(START, "router")
graph.add_conditional_edges("router", route_decision, {
    "task": "task_manager",
    "notes": "notes_agent",
    "research": "memory_check",
    "general": "general",
})

graph.add_conditional_edges("task_manager", tools_condition, {"tools": "task_tools", END: END})
graph.add_edge("task_tools", "task_manager")

graph.add_conditional_edges("notes_agent", tools_condition, {"tools": "notes_tools", END: END})
graph.add_edge("notes_tools", "notes_agent")

graph.add_conditional_edges("memory_check", memory_decision, {
    "found": END,
    "not_found": "research_dispatch",
})
graph.add_edge("research_dispatch", "web_researcher")
graph.add_edge("research_dispatch", "notes_researcher")
graph.add_edge("web_researcher", "critic")
graph.add_edge("notes_researcher", "critic")
graph.add_conditional_edges("critic", critic_decision, {
    "retry": "research_dispatch",
    "approved": "writer",
})
graph.add_edge("writer", "memory_save")
graph.add_edge("memory_save", END)

graph.add_edge("general", END)

conn = sqlite3.connect("conversazioni.db", check_same_thread=False)
memory = SqliteSaver(conn)
app = graph.compile(checkpointer=memory)


# ---------- test da terminale ----------

if __name__ == "__main__":
    config = {"configurable": {"thread_id": "conversation-1", "username": "test"}}
    while True:
        message = input("You: ")
        result = app.invoke({"messages": [{"role": "user", "content": message}], "username": "test"}, config)
        print("Bot:", result["messages"][-1].content)

'''
class Task(SQLModel, table=True):
    Definisce una classe Task.
    * SQLModel significa che questa classe rappresenta un modello di dati.
    * table=True dice a SQLModel che questa classe deve diventare una tabella del database.
    In pratica verrà creata una tabella chiamata task.

tasks_engine = create_engine("sqlite:///tasks.db")
    Crea una connessione al database SQLite.
    Se il file tasks.db non esiste, viene creato automaticamente.

SQLModel.metadata.create_all(tasks_engine)
    Questa è la parte che crea davvero la tabella.
    SQLModel guarda tutte le classi con table=True e crea le tabelle corrispondenti nel database.

task.db
id    username      done      description        due_date
1      giorgia     False     Fare la spesa      2026-07-30
2      marco       True      Finire progetto      NULL



'''