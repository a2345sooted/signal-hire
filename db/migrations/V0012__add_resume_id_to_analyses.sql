-- Add resume_id column to analyses table if it doesn't exist
-- (V0005 dropped it, but now we need it back to link analysis to a specific resume)
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'analyses' AND column_name = 'resume_id') THEN
        ALTER TABLE analyses ADD COLUMN resume_id UUID REFERENCES resumes(id) ON DELETE CASCADE;
    END IF;
END$$;

-- Attempt to backfill resume_id based on candidate_id and job_id if unique
-- This is heuristic but better than nothing for existing data
UPDATE analyses a
SET resume_id = (
    SELECT id FROM resumes r 
    WHERE r.candidate_id = a.candidate_id AND r.job_id = a.job_id
    LIMIT 1
)
WHERE a.resume_id IS NULL;
