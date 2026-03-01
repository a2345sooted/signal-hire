CREATE TABLE processing_tasks (
    id UUID PRIMARY KEY,
    task_type VARCHAR(50) NOT NULL, -- jd, resume, analysis
    job_id UUID REFERENCES jobs(id) ON DELETE CASCADE,
    candidate_id UUID REFERENCES candidates(id) ON DELETE CASCADE,
    resume_id UUID REFERENCES resumes(id) ON DELETE CASCADE,
    status VARCHAR(50) NOT NULL, -- starting, processing, completed, failed, cancelled
    error_message TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX ix_processing_tasks_job_id ON processing_tasks(job_id);
CREATE INDEX ix_processing_tasks_candidate_id ON processing_tasks(candidate_id);
CREATE INDEX ix_processing_tasks_resume_id ON processing_tasks(resume_id);
CREATE INDEX ix_processing_tasks_status ON processing_tasks(status);
