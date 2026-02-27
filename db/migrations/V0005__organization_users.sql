-- Organization users table (mapping users to organizations with roles)
CREATE TYPE orgrole AS ENUM ('OWNER', 'ADMIN', 'RECRUITER');

CREATE TABLE organization_users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role orgrole NOT NULL DEFAULT 'RECRUITER',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(org_id, user_id)
);

CREATE INDEX ix_organization_users_org_id ON organization_users (org_id);
CREATE INDEX ix_organization_users_user_id ON organization_users (user_id);
