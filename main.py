from fastapi import FastAPI
from pydantic import BaseModel
from agent import app as agent
from fastapi.responses import StreamingResponse
import os
from datetime import datetime, timedelta
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from passlib.context import CryptContext
from jose import JWTError, jwt
from sqlmodel import SQLModel, Field, Session, create_engine, select

SECRET_KEY = os.getenv("SECRET_KEY")
ALGORITHM = "HS256"
EXPIRATION_MINUTES = 60

# l'oggetto che sa come fare hash e verifica delle password (con l'algoritmo bcrypt, standard del settore).
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
# dice a FastAPI "gli endpoint protetti si aspettano un token, ottenuto facendo login su /login" — serve anche per far comparire il tasto "Authorize" nella pagina /docs.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")

class User(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    username: str = Field(unique=True, index=True)
    password_hash: str

users_engine = create_engine("sqlite:///users.db")
SQLModel.metadata.create_all(users_engine)

class RecordUser(BaseModel):
    username: str
    password: str


app = FastAPI()

@app.post("/register")
def registra(data: RecordUser):
    with Session(users_engine) as session:
        exists = session.exec(select(User).where(User.username == data.username)).first()
        if exists:
            raise HTTPException(status_code=400, detail="Username already in use")
        new = User(username=data.username, password_hash=pwd_context.hash(data.password))
        session.add(new)
        session.commit()
        return {"message": "User created"}
    
@app.post("/login")
def login(form_data: OAuth2PasswordRequestForm = Depends()):
    with Session(users_engine) as session:
        user = session.exec(select(User).where(User.username == form_data.username)).first()
        if not user or not pwd_context.verify(form_data.password, user.password_hash):
            raise HTTPException(status_code=401, detail="Credenziali non valide")
        expiration = datetime.utcnow() + timedelta(minutes=EXPIRATION_MINUTES)
        token = jwt.encode({"sub": user.username, "exp": expiration}, SECRET_KEY, algorithm=ALGORITHM)
        return {"access_token": token, "token_type": "bearer"}
    
def current_user(token: str = Depends(oauth2_scheme)):
    exception = HTTPException(status_code=401, detail="Token not valid")
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username = payload.get("sub")
        if username is None:
            raise exception
    except JWTError:
        raise exception
    return username

def extract_text(message):
    if isinstance(message.content, str):
        return message.content
    text = ""
    for block in message.content:
        if isinstance(block, dict) and block.get("type") == "text":
            text += block.get("text", "")
    return text

# il body che il client manda. thread_id: str = "default" ha un valore di default, quindi il client può anche non specificarlo e useranno tutti la stessa conversazione.
class ChatMessage(BaseModel):
    message: str
    thread_id: str = "default"

@app.post("/chat")
def chat(data: ChatMessage, username: str = Depends(current_user)):
    thread_id = f"{username}-{data.thread_id}"
    config = {"configurable": {"thread_id": thread_id}}
    # ora il messaggio arriva da una richiesta HTTP invece che da input().
    result = agent.invoke(
        {"messages": [{"role": "user", "content": data.message}]},
        config
    )
    # La risposta restituita è solo il testo (risultato["messages"][-1].content), non l'intero oggetto messaggio
    return {"reply": extract_text(result["messages"][-1])}


@app.post("/chat/stream")
def chat_stream(data: ChatMessage):
    config = {"configurable": {"thread_id": data.thread_id}}

    def genera():
        for chunk, metadata in agent.stream(
            {"messages": [{"role": "user", "content": data.message}]},
            config,
            stream_mode="messages"
        ):
            if chunk.content:
                yield chunk.content

    return StreamingResponse(genera(), media_type="text/plain")


'''
@app.post("/chat")
    Decoratore: registra questa funzione come endpoint che risponde a richieste POST sull'indirizzo /chat. 
    app qui è l'oggetto FastAPI (quello creato con app = FastAPI()), non l'agente — nomi uguali ma cose diverse, tienilo a mente.

def chat(dati: MessaggioChat):
    La funzione riceve dati, un oggetto già validato secondo il modello MessaggioChat che avevi definito (con i campi messaggio e thread_id). 
    FastAPI lo costruisce da solo leggendo il body JSON della richiesta e controllando che i tipi corrispondano 
    — se manca messaggio o è del tipo sbagliato, il client riceve già un errore automatico prima ancora che la tua funzione parta.

config = {"configurable": {"thread_id": dati.thread_id}}
    LangGraph vuole sapere a quale "conversazione" appartiene questo messaggio, per recuperare la memoria giusta. 
    Questo dizionario è il formato richiesto per dirglielo: prendi il thread_id che il client ha mandato (o il default "default" se non l'ha specificato) 
    e lo passi così com'è. Da notare: dati.thread_id — accedi ai campi dell'oggetto Pydantic con il punto, non con le parentesi quadre come faresti con un dizionario.

risultato = agent.invoke(
    {"messages": [{"role": "user", "content": dati.messaggio}]},
    config
)
    Qui chiami davvero l'agente (il grafo compilato con LangGraph, importato all'inizio del file).
    - Primo argomento: lo stato iniziale che dai in pasto al grafo. È un dizionario con la chiave "messages", che contiene una lista di messaggi 
        — qui ce n'è uno solo, quello nuovo dell'User, con "role": "user" (per dire "questo l'ha scritto la persona, non il bot") 
          e "content" che è il testo vero (dati.messaggio, cioè quello arrivato dalla richiesta HTTP).
    - Secondo argomento: il config di prima, che dice al grafo quale conversazione/memoria usare.
    .invoke(...): esegue il grafo una volta, dall'inizio (START) alla fine (END), passando dal nodo chatbot che avevi definito in agent.py 
    — quello che chiama davvero il modello Claude.
    Il risultato (risultato) è lo stato finale del grafo dopo l'esecuzione: di nuovo un dizionario con "messages", 
    ma ora la lista contiene sia il messaggio dell'User sia (grazie alla memoria) tutti i messaggi precedenti di quella conversazione, 
    più la nuova risposta del bot aggiunta in coda.

return {"risposta": risultato["messages"][-1].content}
    Non vuoi restituire al client tutta la lista di messaggi, solo l'ultima risposta.
    risultato["messages"]: la lista di tutti i messaggi.
    [-1]: l'ultimo elemento della lista
    .content: l'oggetto messaggio (creato da LangChain/LangGraph) ha diversi attributi (chi l'ha scritto, metadati, ecc.), .content è quello che contiene solo il testo vero e proprio.
    Il tutto viene incapsulato in un dizionario {"risposta": ...}, che FastAPI converte in JSON come risposta finale al client: es. {"risposta": "ciao, come posso aiutarti?"}.

In sintesi: la funzione prende il messaggio HTTP in entrata, lo trasforma nel formato che LangGraph si aspetta, lo fa girare nel grafo (che richiama Claude e gestisce la memoria), e restituisce indietro solo il testo della risposta, pulito, come JSON.
'''



'''
StreamingResponse: una classe di FastAPI, diversa dal solito return {...}. 
Invece di aspettare che la funzione finisca e mandare tutto insieme, manda pezzi di risposta man mano che sono pronti, mentre il client li riceve in tempo reale.

def genera(): — questa è una funzione "generatore". La riconosci perché usa yield invece di return. 
La differenza chiave: return esce dalla funzione consegnando un valore finale; yield "mette in pausa" la funzione, consegna un pezzo di dato, 
e resta pronta a riprendere da dove si era fermata alla chiamata successiva. È così che riesci a mandare la risposta a pezzi invece che tutta insieme.

agent.stream(...) invece di agent.invoke(...): 
    .invoke() esegue tutto il grafo e ti dà il risultato finale in un colpo solo (quello che avevi già). 
    .stream() invece ti fa "ascoltare" cosa succede mentre il grafo lavora, pezzo per pezzo.

stream_mode="messages": dice a LangGraph esattamente che tipo di pezzi vuoi vedere: i token del messaggio via via che il modello li genera 
(come vedi scrivere ChatGPT in tempo reale), invece che l'intero messaggio finito o gli aggiornamenti di stato del grafo.

for chunk, metadata in ...: ogni "pezzo" che arriva è in realtà una coppia: chunk (un frammento di messaggio, tipo poche parole o anche solo una) 
e metadata (informazioni extra tipo quale nodo del grafo l'ha generato — qui non ci serve, ma va comunque ricevuto per come è strutturato il dato).

if chunk.content: — alcuni frammenti possono essere vuoti (es. metadati senza testo vero), quindi controlli che ci sia davvero del testo prima di mandarlo.

yield chunk.content: manda quel pezzo di testo al client, subito, senza aspettare il resto della risposta.

media_type="text/plain": dici al client che tipo di contenuto sta ricevendo (testo semplice, pezzo per pezzo).
'''