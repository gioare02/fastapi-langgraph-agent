# StateGraph 
È il grafo che costruirai. tipo una mappa 
Ogni nodo è una funzione Python.
START --> punto da cui parte flusso
  |
  |
Nodo A
  |
Nodo B
  |
 END --> Dice a LangGraph: “Il workflow è finito.”

# MessagesState
LangGraph deve sapere “Che informazioni mi porto dietro mentre il programma gira?”
Qui gli stai dicendo: “Lo stato sarà una lista di messaggi.”
Quindi lo state è qualcosa tipo
{
    "messages": [
        HumanMessage("Ciao"),
        AIMessage("Ciao!")
    ]
}

# MemorySaver
Serve per ricordare la conversazione.

# ChatAnthropic
Questo è semplicemente il wrapper per Claude.
È come scrivere client = OpenAI(...)

# def chatbot(state: MessagesState):
Questa funzione rappresenta un nodo del grafo.
Immagina di avere questo nodo ("chatbot")
Quando LangGraph arriva qui, esegue questa funzione.
- il parametro state vale qualcosa tipo
{
   "messages":[
      HumanMessage("Ciao")
   ]
}
cioè tutto quello che il chatbot sa.

risposta = llm.invoke(state["messages"])
Prende
[
 HumanMessage("Ciao")
]
e la manda a Claude.
Claude restituisce: AIMessage("Ciao! Come posso aiutarti?")
--> risposta diventa AIMessage(...)

return {
    "messages":[risposta]
}
Non restituisce una stringa. Restituisce un aggiornamento dello stato.
Dice a LangGraph “Aggiungi questo messaggio allo stato.”
Quindi prima avevi:
messages
    Human: Ciao

--> dopo
    Human:Ciao
    AI:Ciao!

# grafo = StateGraph(MessagesState)
Qui nasce il grafo. Per ora è vuoto.

# grafo.add_node("chatbot", chatbot)
Qui aggiungi un nodo. Adesso il grafo è
  chatbot

# grafo.add_edge(START,"chatbot")
Ora il grafo è
  START
    ↓
  chatbot

# grafo.add_edge("chatbot",END)
Dice: Quando hai finito chatbot termina.
Quindi diventa
  START
    ↓
  chatbot
    ↓
  END

# memoria = MemorySaver()
Qui crei la memoria. Non fa ancora nulla. È solo un oggetto.

# app = grafo.compile(checkpointer=memoria)
Questa è la riga finale. Prima avevi solo il progetto del grafo.
Ora LangGraph costruisce il motore eseguibile. Puoi immaginarla come
  Blueprint
    ↓
  Compile
    ↓
  Programma eseguibile





                START
                  │
                  ▼
         Analizza richiesta
                  │
      ┌───────────┴───────────┐
      ▼                       ▼
 Serve SQL?             Serve Web Search?
      │                       │
      ▼                       ▼
 Tool SQL               Tool Search
      └───────────┬───────────┘
                  ▼
            Ragionamento
                  ▼
        Serve un altro tool?
           │            │
          Sì            No
           │             ▼
           └──────────► END


il grafo di LangGraph ha uno "stato" che viaggia lungo tutta la conversazione — finora conteneva solo i messaggi (messages). Al passo precedente abbiamo aggiunto un secondo cassetto a questo stato: username, che viene impostato una volta sola, quando l'utente fa login e manda il primo messaggio — non lo scrive Claude, lo scrive il codice in main.py, con dati certi (viene dal token JWT verificato, non da quello che qualcuno scrive in chat).

InjectedState è il meccanismo che dice a un tool: "quando ti chiamano, non aspettarti che Claude ti dia l'username come argomento — vallo a prendere direttamente dallo stato del grafo, che è già lì, sicuro". Claude nemmeno "vede" che il tool ha bisogno di questa informazione — dal suo punto di vista, il tool ha solo gli argomenti normali (es. "descrizione del task"), lo username gli arriva "di nascosto", iniettato dal sistema.

Quindi il flusso completo diventa: utente loggato scrive "aggiungi comprare il latte" → Claude chiama il tool con solo descrizione = "comprare il latte" → il tool, dietro le quinte, riceve anche lo username vero (iniettato) → salva nel database la riga giusta, associata alla persona giusta.