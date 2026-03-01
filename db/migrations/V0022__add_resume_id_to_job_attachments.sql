ALTER TABLE job_attachments ADD COLUMN resume_id UUID REFERENCES resumes(id) ON DELETE SET NULL;

-- For existing records, attempt to populate with the latest resume for the candidate
UPDATE job_attachments ja
SET resume_id = (
    SELECT r.id FROM resumes r
    WHERE r.candidate_id = ja.candidate_id
    ORDER BY r.created_at DESC
    LIMIT 1
)
WHERE ja.resume_id IS NULL;
