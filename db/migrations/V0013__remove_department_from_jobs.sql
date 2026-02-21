-- Remove department from jobs table
ALTER TABLE jobs DROP COLUMN IF EXISTS department;
