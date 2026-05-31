# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

B2B SaaS customer support agent that answers questions from uploaded company documents (PDF, TXT). Combines RAG, Agentic RAG, Guardrails, and Memory into a full-stack AI agent.

## Tech Stack

- **LLM**: OpenAI GPT-4o (main), GPT-4o-mini (guardrail monitor)
- **Agent framework**: LangChain
- **Vector DB**: pgvector (PostgreSQL extension) via `langchain_postgres.PGVector`
- **Keyword search**: BM25 (Hybrid Search with RRF algorithm)
- **Embeddings**: `OpenAIEmbeddings` + `CacheBackedEmbeddings`
- **Backend**: FastAPI + Python
- **Frontend**: Next.js 15 (App Router) + Tailwind CSS
- **Infra**: AWS EC2 (FastAPI) + RDS PostgreSQL (pgvector)
- **Monitoring**: LangSmith + CloudWatch

## Repository Structure

```
customer-support-agent/
├── backend/
│   ├── main.py                  # FastAPI entry point
│   ├── agent/
│   │   ├── agent.py             # create_agent configuration
│   │   ├── tools.py             # RAG search tool, refund tool, memory tools
│   │   ├── middleware.py        # PII, Guardrail, Memory middleware
│   │   └── context.py           # Context dataclass (user_id, user_tier)
│   ├── rag/
│   │   ├── loader.py            # PDFPlumber / PyMuPDF loaders
│   │   ├── splitter.py          # RecursiveCharacterTextSplitter (chunk_size=500, overlap=50)
│   │   ├── embedder.py          # OpenAIEmbeddings + CacheBackedEmbeddings
│   │   └── vectorstore.py       # pgvector store/retrieve
│   └── routers/
│       ├── chat.py              # POST /chat
│       ├── upload.py            # POST /upload
│       └── approve.py           # POST /approve, GET /pending (Human-in-the-loop)
└── frontend/
    └── app/
        ├── page.tsx             # Chat UI (streaming via SSE)
        ├── admin/page.tsx       # Document upload admin screen
        └── approve/page.tsx     # Human-in-the-loop approval screen
```

## Development Commands

### Backend

```bash
cd customer-support-agent/backend
uv run uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### Frontend

```bash
cd customer-support-agent/frontend
npm install
npm run dev
```

### Required Environment Variables

```
OPENAI_API_KEY=sk-...
DATABASE_URL=postgresql://postgres:password@localhost:5432/customer_support_db
LANGSMITH_API_KEY=ls_...
LANGCHAIN_TRACING_V2=true
NEXT_PUBLIC_API_URL=http://localhost:8000
```

## Architecture: Runtime Request Flow

```
Customer message
  → Before Agent Guardrail (profanity/PII block)
  → Agent reasoning
      ├── Needs doc context? → RAG Tool (Hybrid Search: BM25 + Vector, MMR k=5)
      ├── Refund/account change? → Human-in-the-loop (pause, admin approves via /approve)
      └── General question? → Direct answer
  → After Agent Guardrail (LLM-based hallucination check via GPT-4o-mini)
  → PII masking (email: redact, card number: mask last 4 digits)
  → Return final answer
```

## Architecture: Document Indexing Flow

```
PDF/TXT upload
  → PDFPlumber/PyMuPDF loader
  → RecursiveCharacterTextSplitter (chunk_size=500, overlap=50)
  → OpenAIEmbeddings + CacheBackedEmbeddings
  → PostgreSQL + pgvector (collection: "documents")
```

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/upload` | Upload PDF/TXT → RAG indexing |
| `POST` | `/chat` | Send message → `{ message, thread_id, user_id }` |
| `GET` | `/pending` | List Human-in-the-loop approval queue |
| `POST` | `/approve` | Submit decision `{ thread_id, decision }` to resume agent |
| `GET` | `/documents` | List uploaded documents |

`POST /chat` returns `status: "completed"` or `status: "pending_approval"` (with `thread_id` for later resume).

## Key Implementation Notes

- **Hybrid Search**: Combine BM25 (keyword) + Vector (semantic) results using RRF (Reciprocal Rank Fusion) algorithm
- **Guardrail**: Before = block bad input (can jump to `"end"`); After = validate output with GPT-4o-mini watcher, correct if `"HALLUCINATION"` detected
- **Human-in-the-loop**: `HumanInTheLoopMiddleware` pauses execution before `process_refund` tool fires; `thread_id` preserves state until admin approves/rejects
- **Memory**: Short-term via `InMemorySaver` (keyed by `thread_id`); Long-term via `InMemoryStore`/Redis injected into system prompt by `inject_memory` middleware
- **PII handling**: Server-side middleware only — client-side filtering is bypassable

## Coding Standard: Official Documentation Only

**All code must be written strictly according to the official documentation of each library/framework used in this project.**

- LangChain: https://python.langchain.com/docs/
- LangGraph: https://langchain-ai.github.io/langgraph/
- LangChain OpenAI: https://python.langchain.com/docs/integrations/providers/openai/
- FastAPI: https://fastapi.tiangolo.com/
- pgvector / langchain-postgres: https://github.com/langchain-ai/langchain-postgres

Rules:
- Do not use deprecated packages or deprecated APIs. Validate with `python -W error::DeprecationWarning -c "from X import Y"` before committing.
- `langchain-community` is sunset — do **not** import from it. Use standalone integration packages or `langchain_core` equivalents.
- `langchain_classic` re-exports are acceptable only when they pass the deprecation warning test (no `DeprecationWarning` emitted on import).
- Every import must be verified as actually importable in the project venv before it is added to the codebase.
- FastAPI code must follow the official FastAPI documentation patterns: `APIRouter` for route grouping, Pydantic models for request/response bodies, `Depends` for dependency injection, the `lifespan` context manager for startup/shutdown, and `async def` endpoints. Prefer framework-provided mechanisms over hand-rolled equivalents.

## Implementation Phases

1. **Phase 1** — RAG pipeline (pgvector store/retrieve + `/upload` API)
2. **Phase 2** — Basic Agent + RAG Tool + Hybrid Search + `/chat` API
3. **Phase 3** — Short-term & Long-term Memory
4. **Phase 4** — PII + Guardrail Middleware
5. **Phase 5** — Human-in-the-loop (`/pending`, `/approve` APIs + admin UI)
6. **Phase 6** — Frontend (streaming chat UI, admin upload UI) + LangSmith
7. **Phase 7** — AWS EC2 + RDS deployment, GitHub Actions CI/CD
