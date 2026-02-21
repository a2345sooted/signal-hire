-- Add email column to candidates table
ALTER TABLE candidates ADD COLUMN email VARCHAR(255) NOT NULL DEFAULT '';
-- Remove the default after adding the column to allow future inserts without default
ALTER TABLE candidates ALTER COLUMN email DROP DEFAULT;
