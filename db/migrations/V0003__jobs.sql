-- Jobs table
CREATE TABLE jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID REFERENCES organizations(id) ON DELETE CASCADE,
    title VARCHAR(255),
    raw_text TEXT NOT NULL,
    markdown_content TEXT,
    structured_data JSONB NOT NULL,
    embedding vector(1536),
    location VARCHAR(255),
    work_arrangement VARCHAR(50),
    hybrid_days_per_week INTEGER,
    pay_range_min INTEGER,
    pay_range_max INTEGER,
    pay_type VARCHAR(50),
    employment_type VARCHAR(50),
    offers_relocation BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Index for jobs vector similarity search
CREATE INDEX jobs_embedding_idx ON jobs USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);

-- Index for jobs JSONB queries
CREATE INDEX jobs_structured_data_idx ON jobs USING gin (structured_data);

-- Index for jobs foreign key
CREATE INDEX ix_jobs_org_id ON jobs (org_id);
