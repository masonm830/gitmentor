# GitMentor

AI-powered code learning and mock interview prep tool that analyzes your GitHub repos and teaches them back to you.

[![Live Demo](https://img.shields.io/badge/live%20demo-gitmentor--five.vercel.app-58a6ff?style=flat-square)](https://gitmentor-five.vercel.app)
[![GitHub](https://img.shields.io/badge/github-masonm830%2Fgitmentor-0d1117?style=flat-square&logo=github)](https://github.com/masonm830/gitmentor)

## What it does

Engineers who build with AI coding tools often cannot fully explain every architectural decision in interviews. GitMentor closes that gap by analyzing your codebase end to end, then producing a plain-English architecture overview, per-file explanations grounded in your real code, interview questions tied to specific functions and files, and a scored mock interview mode that evaluates accuracy, completeness, and depth.

## Features

| Feature | Description |
|---|---|
| Architecture Analysis | Plain-English overview of data flow, layers, and critical files |
| File Explorer | Per-file explanations with dependency mapping and impact-if-deleted analysis |
| Mock Interview | 8 questions grounded in your actual codebase, scored on accuracy, completeness, and depth |
| Voice Input | Speak your answers via the Web Speech API, transcribed in real time |
| Gap Detection | Flags files that were AI-generated and never manually reviewed |
| Eval Harness | LLM-as-judge pipeline with golden dataset, 100% pass rate at 8.8 average overall score |

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | React 18, Vite, Tailwind CSS |
| Backend | FastAPI, Python 3.11 |
| Orchestration | LangGraph (4-agent pipeline) |
| LLM | Claude API (Anthropic) and Groq, hybrid routing |
| RAG | LlamaIndex with pgvector (Supabase) |
| Code Analysis | tree-sitter for AST parsing (Python and JavaScript) |
| Embeddings | HuggingFace Inference API (all-MiniLM-L6-v2) |
| Database | Supabase (PostgreSQL + pgvector) |
| Auth | GitHub OAuth 2.0 |
| Deployment | Render (backend) and Vercel (frontend) |

## Architecture

A LangGraph state graph wires four specialized agents into a single analysis pipeline. Cheap structured-extraction work is routed to Groq (Llama 3.3 70B on the free tier). Generation and grading work where quality matters most goes to the Claude API.

```
GitHub Repo
    │
    ▼
Repo Analyzer (Groq)
    │
    ▼
Explanation Agent (Claude)         ← per-file, with RAG retrieval
    │
    ├──────────────┐
    ▼              ▼
Question         Gap
Generator        Detector
(Claude)         (Groq)
    │              │
    └──────┬───────┘
           ▼
Mock Interview Evaluator (Claude)  ← scored on accuracy, completeness, depth
```

The hybrid LLM strategy keeps per-session cost near $0.35 while preserving high evaluation quality. The provider boundary is a single config swap, so any agent can move between Groq, Claude, or another backend without code changes.

## Getting Started

### Prerequisites

- Python 3.11
- Node.js 18 or newer
- Supabase account (PostgreSQL with pgvector enabled)
- Groq API key
- Anthropic API key
- HuggingFace API token
- GitHub OAuth App (client ID and secret)

### Backend

```bash
git clone https://github.com/masonm830/gitmentor.git
cd gitmentor/backend
pip install -r requirements.txt
cp ../.env.example .env   # then fill in your keys
uvicorn app.main:app --reload
```

The API runs on http://127.0.0.1:8000.

### Frontend

```bash
cd ../frontend
npm install
npm run dev
```

The dev server runs on http://localhost:3000 and talks to the backend at http://127.0.0.1:8000 by default. Override with `VITE_API_BASE_URL` if needed.

### Database

In the Supabase SQL editor, run the schema files in this order:

1. `backend/supabase_schema.sql` (Phase 1: repos, files)
2. `backend/supabase_schema_phase2.sql` (Phase 2: parsed_files, dependencies)
3. `backend/supabase_schema_phase3.sql` (Phase 3: code_chunks + pgvector RPC)
4. `backend/migrations/004_analyses_table.sql`
5. `backend/migrations/005_analyses_add_file_explanations.sql`
6. `backend/migrations/006_interview_sessions.sql`
7. `backend/migrations/007_eval_runs.sql`

## Environment Variables

| Variable | Description |
|---|---|
| `SUPABASE_URL` | Supabase project URL |
| `SUPABASE_SERVICE_KEY` | Service-role key (server-side only, bypasses RLS) |
| `GITHUB_TOKEN` | Personal access token used by the backend to clone repos |
| `GROQ_API_KEY` | Groq API key for the Repo Analyzer and Gap Detector agents |
| `ANTHROPIC_API_KEY` | Anthropic API key for the Explanation, Question Generator, and Interview Evaluator agents |
| `HUGGINGFACE_API_TOKEN` | HuggingFace Inference API token for sentence embeddings |
| `GITHUB_CLIENT_ID` | OAuth App client ID |
| `GITHUB_CLIENT_SECRET` | OAuth App client secret |
| `FRONTEND_URL` | Public URL of the deployed frontend (used for OAuth redirect) |
| `VITE_API_BASE_URL` | Frontend only. Public URL of the deployed backend |

## Eval Harness

The eval harness runs 10 golden entries drawn from a real codebase (SiteTracker) through the full Interview Evaluator and compares the produced scores against expected bands. Trigger a run with `POST /api/eval/run`, or open the `/eval` dashboard for a UI view of recent runs. Current benchmark: 100% pass rate, 8.8 average overall score, 8.7 seconds average latency per entry.

## Portfolio Context

GitMentor was built as a portfolio project to demonstrate production-grade AI engineering patterns: multi-agent orchestration, hybrid LLM routing, AST-aware RAG, and LLM-as-judge evaluation. It also reflects a real personal need. The project itself was built with Claude Code and Cursor, and GitMentor was pointed at its own dependencies to make sure every architectural decision could be explained from first principles.

Other portfolio projects:

- [SiteTracker](https://site-tracker-five.vercel.app): site management dashboard (React, FastAPI, Supabase)
- [Clinical Trial Matcher](https://clinical-trial-matcher-rho.vercel.app): Claude tool-use over ClinicalTrials.gov data
