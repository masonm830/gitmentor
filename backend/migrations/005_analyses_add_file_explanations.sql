-- Phase 4 follow-up: persist per-file explanations and pipeline errors with each analysis.
-- The Phase 4 review found that file_explanations (the ExplanationAgent output)
-- was being returned via API but never written to Supabase, so reloading an
-- analysis lost the per-file content.

ALTER TABLE analyses
    ADD COLUMN IF NOT EXISTS file_explanations JSONB NOT NULL DEFAULT '{}'::jsonb,
    ADD COLUMN IF NOT EXISTS errors JSONB NOT NULL DEFAULT '[]'::jsonb;
