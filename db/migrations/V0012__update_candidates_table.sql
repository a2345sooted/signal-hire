-- Update candidates table with new fields
ALTER TABLE candidates ADD COLUMN phone VARCHAR(50);
ALTER TABLE candidates ADD COLUMN location VARCHAR(255);
ALTER TABLE candidates ADD COLUMN citizenship VARCHAR(255);
ALTER TABLE candidates ADD COLUMN linkedin_url VARCHAR(255);
ALTER TABLE candidates ADD COLUMN engagement_types JSONB;
ALTER TABLE candidates ADD COLUMN work_preference JSONB;
ALTER TABLE candidates ADD COLUMN open_to_relocation BOOLEAN DEFAULT FALSE;
