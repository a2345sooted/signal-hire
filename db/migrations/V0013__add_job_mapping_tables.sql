-- Mapping tables for attached and recommended candidates/jobs
CREATE TABLE job_attachments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id UUID NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    candidate_id UUID NOT NULL REFERENCES candidates(id) ON DELETE CASCADE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE TABLE job_recommendations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id UUID NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    candidate_id UUID NOT NULL REFERENCES candidates(id) ON DELETE CASCADE,
    score INTEGER,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX ix_job_attachments_job_id ON job_attachments (job_id);
CREATE INDEX ix_job_attachments_candidate_id ON job_attachments (candidate_id);
CREATE INDEX ix_job_recommendations_job_id ON job_recommendations (job_id);
CREATE INDEX ix_job_recommendations_candidate_id ON job_recommendations (candidate_id);
