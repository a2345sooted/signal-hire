CREATE TABLE user_terms (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    version VARCHAR(50) NOT NULL,
    accepted_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX ix_user_terms_user_id ON user_terms (user_id);
