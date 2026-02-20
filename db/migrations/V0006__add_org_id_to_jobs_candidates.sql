-- Add org_id to jobs and candidates table
ALTER TABLE jobs ADD COLUMN org_id UUID REFERENCES organizations(id) ON DELETE CASCADE;
ALTER TABLE candidates ADD COLUMN org_id UUID REFERENCES organizations(id) ON DELETE CASCADE;

CREATE INDEX ix_jobs_org_id ON jobs (org_id);
CREATE INDEX ix_candidates_org_id ON candidates (org_id);
