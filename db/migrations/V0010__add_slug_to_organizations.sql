-- Add slug column to organizations table
ALTER TABLE organizations ADD COLUMN slug VARCHAR(255) UNIQUE;

-- Generate slugs for existing organizations (if any)
UPDATE organizations SET slug = LOWER(REPLACE(name, ' ', '-')) WHERE slug IS NULL;

-- Make slug column NOT NULL after populating existing data
ALTER TABLE organizations ALTER COLUMN slug SET NOT NULL;
