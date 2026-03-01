-- Add details JSONB column to jobs table
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS details JSONB;
