-- Resumes table
CREATE TABLE resumes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    original_filename VARCHAR(255) NOT NULL,
    storage_key VARCHAR(255),
    raw_text TEXT NOT NULL,
    raw_text_hash VARCHAR(64),
    structured_data JSONB NOT NULL,
    embedding vector(1536),
    job_id UUID REFERENCES jobs(id) ON DELETE CASCADE,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Index for resumes vector similarity search
CREATE INDEX resumes_embedding_idx ON resumes USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);

-- Index for resumes JSONB queries
CREATE INDEX resumes_structured_data_idx ON resumes USING gin (structured_data);

-- Index for resumes hash lookups
CREATE INDEX ix_resumes_raw_text_hash ON resumes (raw_text_hash);

-- Index for resumes foreign key
CREATE INDEX ix_resumes_job_id ON resumes (job_id);
