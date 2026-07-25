from langgraph.graph import StateGraph, START, END, MessagesState
from langgraph.checkpoint.sqlite import SqliteSaver
import sqlite3
from langchain_anthropic import ChatAnthropic
from dotenv import load_dotenv

load_dotenv()

llm = ChatAnthropic(model="claude-sonnet-4-5")

def chatbot(state: MessagesState):
    risposta = llm.invoke(state["messages"])
    return {"messages": [risposta]}

grafo = StateGraph(MessagesState)
grafo.add_node("chatbot", chatbot)
grafo.add_edge(START, "chatbot")
grafo.add_edge("chatbot", END)

# crea (o apre, se esiste già) il file del database.
conn = sqlite3.connect("conversazioni.db", check_same_thread=False)
# passi la connessione al database a LangGraph, che da qui in poi gestisce da solo la struttura interna (crea le tabelle necessarie per salvare stato e messaggi).
memoria = SqliteSaver(conn)
app = grafo.compile(checkpointer=memoria)

if __name__ == "__main__":
    config = {"configurable": {"thread_id": "conversazione-1"}}
    while True:
        messaggio = input("Tu: ")
        risultato = app.invoke({"messages": [{"role": "user", "content": messaggio}]}, config)
        print("Bot:", risultato["messages"][-1].content)