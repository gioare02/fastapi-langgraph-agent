# AI Personal Assistant — Multi-Agent System with FastAPI + LangGraph

A personal assistant built as a multi-agent system: a supervisor routes each request to a specialized agent — task management, personal notes (RAG), web research, or general conversation — each with its own tools and database-backed memory, exposed through an authenticated REST API with a dedicated chat UI.

**Live demo:** [add Streamlit app link here] · **API:** [add Render link + `/docs` here]

## Features

- **Multi-agent orchestration**: a supervisor node classifies each request and routes it to the right specialist, instead of relying on a single general-purpose agent
- **Task manager**: add, list, and complete personal to-dos via natural language, persisted per user
- **Personal notes (RAG)**: upload your own documents/notes; the agent retrieves relevant passages by meaning (not just keywords) to answer questions grounded in your own content
- **Research & report agent**: combines your personal notes with live web search to produce structured, source-aware reports
- **User-scoped tools**: every tool automatically operates on the current authenticated user's data via LangGraph's `InjectedState`, never trusting the LLM to supply user identity
- **Persistent conversational memory** across sessions, per user
- **User authentication** with JWT, streaming responses, dedicated chat UI

## Tech stack

- **Backend**: FastAPI, Pydantic
- **Agent orchestration**: LangGraph (supervisor + specialized agent nodes, conditional routing, tool-calling loops)
- **LLM**: Anthropic Claude (via `langchain-anthropic`), including Claude's native web search tool
- **RAG / retrieval**: Chroma (vector store), HuggingFace `sentence-transformers` embeddings (local, no external API key required)
- **Database**: SQLModel on SQLite (users, tasks, conversation checkpoints)
- **Authentication**: OAuth2 + JWT, passwords hashed with bcrypt
- **Frontend**: Streamlit
- **Deployment**: Render (backend), Streamlit Community Cloud (frontend), continuous deployment from GitHub

## Architecture

```
User → Streamlit (UI) → authenticated HTTP requests → FastAPI
                                                          ↓
                                                    LangGraph supervisor
                                                          ↓
                        ┌──────────────┬──────────────────┬───────────────┐
                        ↓              ↓                  ↓               ↓
                  Task Manager    Notes (RAG)      Research/Report     General
                  (DB tool loop)  (Chroma search)  (web search + RAG)  (plain LLM)
                        ↓              ↓                  ↓               ↓
                            SQLite (users, tasks, conversation memory)
                            Chroma (personal notes embeddings)
```

Each specialist agent is a self-contained LangGraph subgraph: an LLM node bound to its own tools, looping through a `ToolNode` until it has enough information to answer, then returning control to the main flow.

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

- `agent.py` — the multi-agent system: shared state definition, per-department tools and nodes (task manager, notes/RAG, research/report, general), the supervisor router, and the compiled LangGraph graph
- `main.py` — FastAPI API: user registration/login, chat endpoints (including streaming), note upload endpoint, JWT authentication
- `app_streamlit.py` — chat interface with built-in login
- `requirements.txt`, `.env.example`, `.gitignore` — project configuration

## Possible future improvements

- Support uploading actual files (PDF, DOCX) for the notes/RAG agent, not just plain text
- Persistent Postgres database instead of SQLite
- Parallel/branching sub-agent execution instead of single-department routing
- Automated tests