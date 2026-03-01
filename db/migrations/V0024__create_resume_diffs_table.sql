CREATE TABLE resume_diffs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    optimized_resume_id UUID NOT NULL REFERENCES resumes(id) ON DELETE CASCADE,
    source_resume_id UUID NOT NULL REFERENCES resumes(id) ON DELETE CASCADE,
    storage_key VARCHAR(255),
    status VARCHAR(50) NOT NULL DEFAULT 'pending',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX ix_resume_diffs_optimized_resume_id ON resume_diffs (optimized_resume_id);
CREATE INDEX ix_resume_diffs_source_resume_id ON resume_diffs (source_resume_id);
