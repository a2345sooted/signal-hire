-- Fix for OrgRole ENUM and ensure it matches the code

-- 1. Create a new ENUM type with all required roles if it doesn't exist
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'orgrole') THEN
        CREATE TYPE orgrole AS ENUM ('owner', 'admin', 'recruiter');
    END IF;
END$$;

-- 2. If org_role exists (from V0005), we should probably migrate to orgrole or vice versa.
-- The error says "type orgrole does not exist", but V0005 created "org_role".
-- SQLAlchemy by default uses lowercase class name for Enum type name if not specified.
-- OrgRole class -> "orgrole" in Postgres.

-- 3. Update the table to use the new type if it was using the old one
-- Since the user got an error on INSERT, the table exists but the type name in SQL doesn't match.

-- Remove default temporarily to allow type change
ALTER TABLE organization_users ALTER COLUMN role DROP DEFAULT;

ALTER TABLE organization_users ALTER COLUMN role TYPE orgrole USING role::text::orgrole;

-- Re-add default with the new type
ALTER TABLE organization_users ALTER COLUMN role SET DEFAULT 'recruiter'::orgrole;

-- Drop the old type if it exists and is no longer used
-- DROP TYPE IF EXISTS org_role;
