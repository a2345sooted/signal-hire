CREATE TABLE embeddings (
    id UUID PRIMARY KEY,
    job_id UUID REFERENCES jobs(id) ON DELETE CASCADE,
    candidate_id UUID REFERENCES candidates(id) ON DELETE CASCADE,
    resume_id UUID REFERENCES resumes(id) ON DELETE CASCADE,
    embedding_type VARCHAR(50) NOT NULL, -- e.g., 'full_text', 'structured_data', 'skills_only'
    vector VECTOR(1536) NOT NULL,
    metadata JSONB, -- store info about the model used, parameters, etc.
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Index for vector search (assuming cosine similarity)
CREATE INDEX idx_embeddings_vector ON embeddings USING ivfflat (vector vector_cosine_ops) WITH (lists = 100);

-- Indices for lookups
CREATE INDEX idx_embeddings_job_id ON embeddings(job_id);
CREATE INDEX idx_embeddings_candidate_id ON embeddings(candidate_id);
CREATE INDEX idx_embeddings_resume_id ON embeddings(resume_id);

-- Migrate existing job embeddings if any
INSERT INTO embeddings (id, job_id, embedding_type, vector, created_at, updated_at)
SELECT gen_random_uuid(), id, 'legacy', embedding, created_at, updated_at
FROM jobs
WHERE embedding IS NOT NULL;

-- Migrate existing resume embeddings if any
INSERT INTO embeddings (id, resume_id, candidate_id, embedding_type, vector, created_at, updated_at)
SELECT gen_random_uuid(), id, candidate_id, 'legacy', embedding, created_at, updated_at
FROM resumes
WHERE embedding IS NOT NULL;

-- Remove legacy columns
ALTER TABLE jobs DROP COLUMN embedding;
ALTER TABLE resumes DROP COLUMN embedding;
