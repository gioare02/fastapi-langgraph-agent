# Progetto: Assistente conversazionale con FastAPI + LangGraph

Progetto didattico per imparare FastAPI e LangGraph, costruito passo per passo.

## Setup

1. Crea un ambiente virtuale (consigliato):
   ```
   python3 -m venv venv
   source venv/bin/activate   # su Windows: venv\Scripts\activate
   ```

2. Installa le dipendenze:
   ```
   pip install -r requirements.txt
   ```

3. Copia `.env.example` in `.env` e inserisci la tua chiave API:
   ```
   cp .env.example .env
   ```
   Poi apri `.env` e incolla la chiave ottenuta da console.anthropic.com

## Struttura del progetto

- `agent.py` — logica dell'agente conversazionale costruita con LangGraph
- `main.py` — API FastAPI che espone l'agente (fase successiva)

## Stato di avanzamento

- [x] Fase 1: agente LangGraph di base, testato da terminale
- [ ] Fase 2: esporlo con FastAPI
- [ ] Fase 3: streaming delle risposte
- [ ] Fase 4: persistenza conversazioni su database
- [ ] Fase 5: autenticazione utenti
- [ ] Fase 6: tool per l'agente
- [ ] Fase 7: deploy
