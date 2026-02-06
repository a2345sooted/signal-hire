-- Jobs table
CREATE TABLE jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title VARCHAR(255),
    raw_text TEXT NOT NULL,
    markdown_content TEXT,
    department TEXT,
    structured_data JSONB NOT NULL,
    embedding vector(1536),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Index for jobs vector similarity search
CREATE INDEX jobs_embedding_idx ON jobs USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);

-- Index for jobs JSONB queries
CREATE INDEX jobs_structured_data_idx ON jobs USING gin (structured_data);
