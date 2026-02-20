-- Fix for OrgRole ENUM values (case sensitivity)
-- The code uses OrgRole.OWNER (which is "OWNER") but the ENUM in DB was ('owner', 'admin', 'recruiter')

-- 1. Create a new ENUM type with uppercase values
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'orgrole_new') THEN
        CREATE TYPE orgrole_new AS ENUM ('OWNER', 'ADMIN', 'RECRUITER');
    END IF;
END$$;

-- 2. Update the table to use the new type
-- Remove default temporarily
ALTER TABLE organization_users ALTER COLUMN role DROP DEFAULT;

-- Change column type to the new uppercase ENUM
ALTER TABLE organization_users ALTER COLUMN role TYPE orgrole_new USING UPPER(role::text)::orgrole_new;

-- 3. Cleanup: Drop the old type and rename the new one
DROP TYPE orgrole;
ALTER TYPE orgrole_new RENAME TO orgrole;

-- 4. Re-add default with the new type
ALTER TABLE organization_users ALTER COLUMN role SET DEFAULT 'RECRUITER'::orgrole;
