from langgraph.graph import StateGraph, START, END, MessagesState
from langgraph.checkpoint.memory import MemorySaver
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

memoria = MemorySaver()
app = grafo.compile(checkpointer=memoria)

if __name__ == "__main__":
    config = {"configurable": {"thread_id": "conversazione-1"}}
    while True:
        messaggio = input("Tu: ")
        risultato = app.invoke({"messages": [{"role": "user", "content": messaggio}]}, config)
        print("Bot:", risultato["messages"][-1].content)