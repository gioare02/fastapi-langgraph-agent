# AI Chat Assistant — FastAPI + LangGraph

A conversational AI assistant with persistent memory and web search, exposed as an authenticated REST API with a dedicated chat interface.

**Live demo:** [add Streamlit app link here] · **API:** [add Render link + `/docs` here]

## Features

- Conversations with memory: the agent remembers previous messages in the same session, even after a restart (persisted to a database)
- Built-in web search: the agent can answer with up-to-date information, beyond its base knowledge
- User authentication: registration and login with JWT tokens, each user only sees their own conversations
- Real-time streaming responses
- Dedicated chat UI, in addition to interactive API documentation

## Tech stack

- **Backend**: FastAPI, Pydantic
- **Conversational agent**: LangGraph, Anthropic Claude (via `langchain-anthropic`), Claude's native web search
- **Database**: SQLModel on SQLite (users and conversation history)
- **Authentication**: OAuth2 + JWT, passwords hashed with bcrypt
- **Frontend**: Streamlit
- **Deployment**: Render (backend), Streamlit Community Cloud (frontend), with continuous deployment from GitHub

## Architecture

```
User → Streamlit (UI) → authenticated HTTP requests → FastAPI
                                                          ↓
                                                    LangGraph agent
                                                    (Claude + web search)
                                                          ↓
                                                    SQLite (users + conversation memory)
```

## Local setup

1. Clone the repository and create a virtual environment:
   ```
   python3 -m venv venv
   source venv/bin/activate   # on Windows: venv\Scripts\activate
   ```

2. Install dependencies:
   ```
   pip install -r requirements.txt
   ```

3. Copy `.env.example` to `.env` and fill in the keys:
   ```
   cp .env.example .env
   ```
   You'll need an Anthropic API key (console.anthropic.com) and a `SECRET_KEY` of your choice for signing JWTs.

4. Start the backend and frontend (two separate terminals):
   ```
   uvicorn main:app --reload
   streamlit run app_streamlit.py
   ```

## Project structure

- `agent.py` — the conversational agent logic, built with LangGraph (persistent memory + web search)
- `main.py` — FastAPI API: user registration/login, chat endpoints (including streaming), JWT authentication
- `app_streamlit.py` — chat interface with built-in login
- `requirements.txt`, `.env.example`, `.gitignore` — project configuration

## Possible future improvements

- Additional custom tools for the agent (beyond web search)
- Persistent Postgres database instead of SQLite
- Automated tests
