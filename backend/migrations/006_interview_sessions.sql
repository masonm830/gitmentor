-- Phase 5: mock interview mode.
-- One row per (session, question). /interview/start pre-creates 8 rows for a session
-- (one per generated question) so /interview/evaluate is a deterministic UPDATE by
-- (session_id, question_index).

CREATE TABLE IF NOT EXISTS interview_sessions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id      UUID NOT NULL,
    repo_id         UUID NOT NULL REFERENCES repos(id),
    analysis_id    UUID NOT NULL REFERENCES analyses(id),
    question_index  INT  NOT NULL,
    question_text   TEXT NOT NULL,
    user_answer     TEXT,
    evaluation      JSONB,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (session_id, question_index)
);

CREATE INDEX IF NOT EXISTS interview_sessions_session_id_idx ON interview_sessions (session_id);
CREATE INDEX IF NOT EXISTS interview_sessions_repo_id_idx    ON interview_sessions (repo_id);
CREATE INDEX IF NOT EXISTS interview_sessions_analysis_id_idx ON interview_sessions (analysis_id);
