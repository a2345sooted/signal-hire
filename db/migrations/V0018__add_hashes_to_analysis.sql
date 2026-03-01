-- Add jd_hash and details_hash to analyses table
ALTER TABLE analyses ADD COLUMN IF NOT EXISTS jd_hash TEXT;
ALTER TABLE analyses ADD COLUMN IF NOT EXISTS details_hash TEXT;

-- Indexing hashes for faster lookup
CREATE INDEX IF NOT EXISTS ix_analyses_jd_hash ON analyses (jd_hash);
CREATE INDEX IF NOT EXISTS ix_analyses_details_hash ON analyses (details_hash);
