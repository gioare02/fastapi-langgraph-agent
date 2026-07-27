# AI Personal Assistant — Multi-Agent System with FastAPI + LangGraph

A personal assistant built as a multi-agent system: a supervisor routes each request to a specialized agent — task management, personal notes (RAG), a deep-research pipeline with a critic↔research loop, or general conversation — each with its own tools and database-backed memory, exposed through an authenticated REST API with a dedicated chat UI.

**Live demo:** [add Streamlit app link here] · **API:** [add Render link + `/docs` here]

## Features

- **Multi-agent orchestration**: a supervisor node classifies each request and routes it to the right specialist, instead of relying on a single general-purpose agent
- **Task manager**: add, list, and complete personal to-dos via natural language, persisted per user
- **Personal notes (RAG)**: upload your own documents/notes (including PDFs); the agent retrieves relevant passages by meaning (not just keywords) to answer questions grounded in your own content
- **Deep-research pipeline**: given a topic, a Research Agent gathers information from multiple sources **in parallel** (live web search and the user's personal notes), a Critic Agent evaluates whether the evidence is sufficient and coherent — looping back with targeted follow-up queries when it isn't, capped at a maximum number of iterations — and a Writer Agent synthesizes everything into a structured report where every claim is tied to its source
- **Reusable research memory**: finished reports are persisted per user/topic, so a repeated research request is served instantly instead of re-running the whole pipeline
- **User-scoped tools**: every tool automatically operates on the current authenticated user's data via LangGraph's `InjectedState`, never trusting the LLM to supply user identity
- **Persistent conversational memory** across sessions, per user
- **User authentication** with JWT, streaming responses, dedicated chat UI

## Tech stack

- **Backend**: FastAPI, Pydantic
- **Agent orchestration**: LangGraph — supervisor routing, tool-calling loops, parallel fan-out/fan-in nodes, and a conditional critic↔research loop with an iteration cap
- **LLM**: Anthropic Claude (via `langchain-anthropic`), including Claude's native web search tool
- **RAG / retrieval**: Chroma (vector store), HuggingFace `sentence-transformers` embeddings (local, no external API key required), `pypdf` for PDF text extraction
- **Database**: SQLModel on SQLite (users, tasks, research reports, conversation checkpoints)
- **Authentication**: OAuth2 + JWT, passwords hashed with bcrypt
- **Frontend**: Streamlit
- **Deployment**: Render (backend), Streamlit Community Cloud (frontend), continuous deployment from GitHub

## Architecture

```
User → Streamlit (UI) → authenticated HTTP requests → FastAPI
                                                          ↓
                                                    LangGraph supervisor
                                                          ↓
                ┌──────────────┬──────────────────────────────────────┬───────────────┐
                ↓              ↓                                      ↓               ↓
          Task Manager    Notes (RAG)                       Deep-Research Pipeline    General
          (DB tool loop)  (Chroma search)                                             (plain LLM)
                                              memory check → [web search ‖ notes search]
                                                                    ↓
                                                                 critic ──(insufficient)──┐
                                                                    │                     │
                                                              (sufficient)          back to research
                                                                    ↓                (max 3 loops)
                                                                 writer → save report
                ↓              ↓                                      ↓               ↓
                            SQLite (users, tasks, reports, conversation memory)
                            Chroma (personal notes + PDF embeddings)
```

The Deep-Research Pipeline is the most advanced piece: `web_researcher` and `notes_researcher` run as parallel branches from the same dispatch node (LangGraph fan-out), converge into a `critic` node that judges sufficiency and coherence, and either loop back for another research pass (with a hard cap to avoid infinite loops) or hand off to a `writer` node that produces the final, source-attributed report. A `memory` check/save pair around the whole pipeline reuses past reports instead of repeating work.

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

- `agent.py` — the multi-agent system: shared state definition, per-department tools and nodes (task manager, notes/RAG, the deep-research pipeline, general), the supervisor router, and the compiled LangGraph graph
- `main.py` — FastAPI API: user registration/login, chat endpoints (including streaming), note/PDF upload endpoints, JWT authentication
- `app_streamlit.py` — chat interface with built-in login and note/PDF upload
- `requirements.txt`, `.env.example`, `.gitignore` — project configuration

## Possible future improvements

- Fuzzy/semantic topic matching for research memory reuse (currently exact-text match)
- Persistent Postgres + a managed vector store instead of local SQLite/Chroma, for real production persistence
- Automated tests
- Export reports as PDF/Markdown files