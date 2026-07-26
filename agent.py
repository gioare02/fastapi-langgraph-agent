from langgraph.graph import StateGraph, START, END, MessagesState
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.prebuilt import InjectedState, ToolNode, tools_condition
from langchain_anthropic import ChatAnthropic
from langchain_core.tools import tool
from dotenv import load_dotenv
from sqlmodel import SQLModel, Field, Session, create_engine, select
from typing import Annotated
import sqlite3
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_chroma import Chroma
from langchain_core.documents import Document


load_dotenv()

class AgentState(MessagesState):
    username: str

class Task(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    username: str = Field(index=True)
    description: str
    done: bool = False
    due_date: str | None = None

tasks_engine = create_engine("sqlite:///tasks.db")
SQLModel.metadata.create_all(tasks_engine)

llm = ChatAnthropic(model="claude-sonnet-4-5")

embeddings = HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2")

vector_store = Chroma(
    collection_name="notes",
    embedding_function=embeddings,
    persist_directory="./notes_db"
)

def general(state: AgentState):
    answer = llm.invoke(state["messages"])
    return {"messages": [answer]}

def router(state: AgentState):
    last_message = state["messages"][-1].content
    prompt = (
        "Classify the following user request into exactly one category: "
        "task, notes, research, general. Reply with only the category word.\n\n"
        "- 'task': adding, listing, or completing personal to-dos/reminders\n"
        "- 'notes': questions about the user's personal notes/documents\n"
        "- 'research': requests for a report, or questions needing web search\n"
        "- 'general': anything else\n\n"
        f"Request: {last_message}"
    )
    response = llm.invoke([{"role": "user", "content": prompt}])
    category = response.content.strip().lower()
    if category not in ["task", "notes", "research", "general"]:
        category = "general"
    return {"route": category}

def route_decision(state: AgentState):
    return state.get("route", "general")

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
    
@tool
def search_notes(query: str, state: Annotated[AgentState, InjectedState]) -> str:
    """Search the user's personal notes and documents for information relevant to the query."""
    username = state["username"]
    results = vector_store.similarity_search(query, k=4, filter={"username": username})
    if not results:
        return "No relevant notes found."
    return "\n\n".join(doc.page_content for doc in results)

task_tools = [add_task, list_tasks, complete_task]
llm_tasks = llm.bind_tools(task_tools)

def task_manager(state: AgentState):
    answer = llm_tasks.invoke(state["messages"])
    return {"messages": [answer]}

def split_text(text, chunk_size=500, overlap=50):
    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunks.append(text[start:end])
        start = end - overlap
    return chunks

notes_tools = [search_notes]
llm_notes = llm.bind_tools(notes_tools)

def notes_agent(state: AgentState):
    answer = llm_notes.invoke(state["messages"])
    return {"messages": [answer]}

web_search = {"type": "web_search_20250305", "name": "web_search", "max_uses": 5}
llm_researcher = llm.bind_tools([web_search, search_notes])

def researcher(state: AgentState):
    system_prompt = {
        "role": "system",
        "content": (
            "You are a research assistant. When asked for a report on a topic, "
            "check the user's personal notes for relevant information AND search the web "
            "for up-to-date information. Write a well-structured report with clear sections, "
            "and mention whether each piece of information comes from the user's notes or from web search."
        )
    }
    answer = llm_researcher.invoke([system_prompt] + state["messages"])
    return {"messages": [answer]}

research_tools = [search_notes]

graph = StateGraph(AgentState)

graph.add_node("router", router)
graph.add_node("task_manager", task_manager)
graph.add_node("task_tools", ToolNode(task_tools))
graph.add_node("notes_agent", notes_agent)
graph.add_node("notes_tools", ToolNode([search_notes]))
graph.add_node("researcher", researcher)
graph.add_node("research_tools", ToolNode([search_notes]))
graph.add_node("general", general)

graph.add_edge(START, "router")
graph.add_conditional_edges("router", route_decision, {
    "task": "task_manager",
    "notes": "notes_agent",
    "research": "researcher",
    "general": "general",
})

graph.add_conditional_edges("task_manager", tools_condition, {"tools": "task_tools", END: END})
graph.add_edge("task_tools", "task_manager")

graph.add_conditional_edges("notes_agent", tools_condition, {"tools": "notes_tools", END: END})
graph.add_edge("notes_tools", "notes_agent")

graph.add_conditional_edges("researcher", tools_condition, {"tools": "research_tools", END: END})
graph.add_edge("research_tools", "researcher")

graph.add_edge("general", END)

conn = sqlite3.connect("conversazioni.db", check_same_thread=False)
memory = SqliteSaver(conn)
app = graph.compile(checkpointer=memory)

# --- costruzione del grafo: SOLO per testare il Task Manager da solo ---
# graph = StateGraph(AgentState)
# graph.add_node("task_manager", task_manager)
# graph.add_node("task_tools", ToolNode(task_tools))

# graph.add_edge(START, "task_manager")
# graph.add_conditional_edges("task_manager", tools_condition, {"tools": "task_tools", END: END})
# graph.add_edge("task_tools", "task_manager")

# # crea (o apre, se esiste già) il file del database.
conn = sqlite3.connect("conversazioni.db", check_same_thread=False)
# # passi la connessione al database a LangGraph, che da qui in poi gestisce da solo la struttura interna (crea le tabelle necessarie per salvare stato e messaggi).
memory = SqliteSaver(conn)
app = graph.compile(checkpointer=memory)

if __name__ == "__main__":
    config = {"configurable": {"thread_id": "conversation-1", "username": "test"}}
    while True:
        message = input("You: ")
        result = app.invoke({"messages": [{"role": "user", "content": message}], "username": "test"}, config)
        print("Bot:", result["messages"][-1].content)

# web_search = {"type": "web_search_20250305", "name": "web_search", "max_uses": 3}
# llm_w_tools = llm.bind_tools([web_search])

# def chatbot(state: AgentState):
#     answer = llm_w_tools.invoke(state["messages"])
#     return {"messages": [answer]}

# graph = StateGraph(AgentState)
# graph.add_node("chatbot", chatbot)
# graph.add_edge(START, "chatbot")
# graph.add_edge("chatbot", END)

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