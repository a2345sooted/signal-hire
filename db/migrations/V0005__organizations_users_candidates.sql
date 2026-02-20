-- Users table
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    sub VARCHAR(255) UNIQUE NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Organizations table
CREATE TABLE organizations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Organization users table (mapping users to organizations with roles)
CREATE TYPE org_role AS ENUM ('admin', 'recruiter');

CREATE TABLE organization_users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role org_role NOT NULL DEFAULT 'recruiter',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(org_id, user_id)
);

-- Candidates table
CREATE TABLE candidates (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Update resumes table to belong to a candidate
ALTER TABLE resumes ADD COLUMN candidate_id UUID REFERENCES candidates(id) ON DELETE CASCADE;

-- Update analyses table to target candidate and job instead of resume
ALTER TABLE analyses ADD COLUMN candidate_id UUID REFERENCES candidates(id) ON DELETE CASCADE;
ALTER TABLE analyses ADD COLUMN job_id UUID REFERENCES jobs(id) ON DELETE CASCADE;

-- Copy candidate_id from resumes to analyses for existing data if any (optional but good practice)
-- Assuming one-to-one or one-to-many relationship where resume belongs to candidate
-- Since this is a new setup, it might be empty.
UPDATE analyses a SET candidate_id = r.candidate_id FROM resumes r WHERE a.resume_id = r.id;
-- Note: job_id for analyses needs to be populated too.
UPDATE analyses a SET job_id = r.job_id FROM resumes r WHERE a.resume_id = r.id;

-- Now remove resume_id from analyses after migration
ALTER TABLE analyses DROP COLUMN resume_id;

-- Add indexes
CREATE INDEX ix_organization_users_org_id ON organization_users (org_id);
CREATE INDEX ix_organization_users_user_id ON organization_users (user_id);
CREATE INDEX ix_resumes_candidate_id ON resumes (candidate_id);
CREATE INDEX ix_analyses_candidate_id ON analyses (candidate_id);
CREATE INDEX ix_analyses_job_id ON analyses (job_id);
