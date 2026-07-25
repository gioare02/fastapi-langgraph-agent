from langgraph.graph import StateGraph, START, END, MessagesState
from langgraph.checkpoint.sqlite import SqliteSaver
import sqlite3
from langchain_anthropic import ChatAnthropic
from dotenv import load_dotenv

load_dotenv()

llm = ChatAnthropic(model="claude-sonnet-4-5")

web_search = {"type": "web_search_20250305", "name": "web_search", "max_uses": 3}
llm_w_tools = llm.bind_tools([web_search])

def chatbot(state: MessagesState):
    answer = llm_w_tools.invoke(state["messages"])
    return {"messages": [answer]}

graph = StateGraph(MessagesState)
graph.add_node("chatbot", chatbot)
graph.add_edge(START, "chatbot")
graph.add_edge("chatbot", END)

# crea (o apre, se esiste già) il file del database.
conn = sqlite3.connect("conversazioni.db", check_same_thread=False)
# passi la connessione al database a LangGraph, che da qui in poi gestisce da solo la struttura interna (crea le tabelle necessarie per salvare stato e messaggi).
memory = SqliteSaver(conn)
app = graph.compile(checkpointer=memory)

if __name__ == "__main__":
    config = {"configurable": {"thread_id": "conversation-1"}}
    while True:
        message = input("You: ")
        result = app.invoke({"messages": [{"role": "user", "content": message}]}, config)
        print("Bot:", result["messages"][-1].content)