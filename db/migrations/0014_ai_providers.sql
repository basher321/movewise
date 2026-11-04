-- 0014_ai_providers (spec B17): AI providers for the Student Consultancy and Job Processing
-- advisors, and the per-IP question log for the rate limit. The API keys live encrypted in
-- app_secrets (ai.claude_key, ai.openai_key, ai.gemini_key, ai.groq_key), never here.

ALTER TABLE settings
  ADD COLUMN ai jsonb NOT NULL DEFAULT
    '{"order": ["claude", "openai", "gemini", "groq"],
      "providers": {
        "claude": {"enabled": false, "model": "claude-opus-5-5"},
        "openai": {"enabled": false, "model": ""},
        "gemini": {"enabled": false, "model": ""},
        "groq": {"enabled": false, "model": ""}}}'::jsonb
    CHECK (jsonb_typeof(ai) = 'object');

-- One row per advisor question, for the limit of 20 per IP in 10 minutes. The question text is
-- never stored. Old rows are ignored, not deleted.
CREATE TABLE ai_questions (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  module text NOT NULL CHECK (module IN ('study', 'job')),
  ip text NOT NULL,
  provider text CHECK (provider IN ('claude', 'openai', 'gemini', 'groq')),
  at timestamptz NOT NULL DEFAULT clock_timestamp(),
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX ai_questions_ip_at_idx ON ai_questions (ip, at);

CREATE TRIGGER trg_ai_questions_block_change BEFORE UPDATE OR DELETE ON ai_questions
  FOR EACH ROW EXECUTE FUNCTION block_change();
