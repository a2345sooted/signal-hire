-- V0026__add_diff_to_resumes.sql
ALTER TABLE resumes ADD COLUMN diff JSONB;
