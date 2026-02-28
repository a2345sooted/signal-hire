-- Migration to add candidate_recommendations table
CREATE TABLE candidate_recommendations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    candidate_id UUID NOT NULL REFERENCES candidates(id) ON DELETE CASCADE,
    job_id UUID NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    score INTEGER,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX ix_candidate_recommendations_candidate_id ON candidate_recommendations (candidate_id);
CREATE INDEX ix_candidate_recommendations_job_id ON candidate_recommendations (job_id);
