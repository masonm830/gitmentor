-- Phase 4: analyses table
-- Stores the full output of the LangGraph multi-agent pipeline for a repo.

CREATE TABLE IF NOT EXISTS analyses (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    repo_id       UUID NOT NULL REFERENCES repos(id),
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    architecture_overview  TEXT,
    interview_questions    JSONB NOT NULL DEFAULT '[]'::jsonb,
    gap_analysis           JSONB NOT NULL DEFAULT '{}'::jsonb,
    status        TEXT NOT NULL DEFAULT 'pending'
);

CREATE INDEX IF NOT EXISTS analyses_repo_id_idx ON analyses (repo_id);
