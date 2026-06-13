-- Phase 7: eval harness run history.
-- One row per /api/eval/run invocation. The dashboard at /eval reads the
-- last 10 rows ordered by created_at desc and renders pass-rate trends plus
-- a per-entry breakdown of the most recent run.

CREATE TABLE IF NOT EXISTS eval_runs (
    id                          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at                  TIMESTAMPTZ NOT NULL DEFAULT now(),
    pass_rate                   FLOAT NOT NULL,
    avg_overall                 FLOAT NOT NULL,
    avg_accuracy                FLOAT NOT NULL,
    avg_completeness            FLOAT NOT NULL,
    avg_depth                   FLOAT NOT NULL,
    avg_semantic_similarity     FLOAT NOT NULL,
    avg_latency_seconds         FLOAT NOT NULL,
    total_entries               INT   NOT NULL,
    passed                      INT   NOT NULL,
    failed                      INT   NOT NULL,
    per_entry_results           JSONB NOT NULL DEFAULT '[]'::jsonb,
    notes                       TEXT
);

CREATE INDEX IF NOT EXISTS eval_runs_created_at_idx
    ON eval_runs (created_at DESC);
