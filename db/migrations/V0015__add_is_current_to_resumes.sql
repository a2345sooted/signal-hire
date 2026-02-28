-- Add is_current to resumes table
ALTER TABLE resumes ADD COLUMN is_current BOOLEAN DEFAULT TRUE;
