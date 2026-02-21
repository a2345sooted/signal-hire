-- Expand Job table with new fields
ALTER TABLE jobs ADD COLUMN location VARCHAR(255);
ALTER TABLE jobs ADD COLUMN work_arrangement VARCHAR(50);
ALTER TABLE jobs ADD COLUMN hybrid_days_per_week INTEGER;
ALTER TABLE jobs ADD COLUMN pay_range_min INTEGER;
ALTER TABLE jobs ADD COLUMN pay_range_max INTEGER;
ALTER TABLE jobs ADD COLUMN pay_type VARCHAR(50);
ALTER TABLE jobs ADD COLUMN employment_type VARCHAR(50);
ALTER TABLE jobs ADD COLUMN offers_relocation BOOLEAN NOT NULL DEFAULT FALSE;
