-- Migration V6: Posts & Broadcasts
-- ClawDesk Batch 6 - Post Scheduling & Broadcast Messaging

-- Posts table for scheduled Facebook/Zalo posts
CREATE TABLE IF NOT EXISTS posts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id UUID NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
    channel TEXT DEFAULT 'facebook' CHECK (channel IN ('facebook', 'zalo')),
    content TEXT NOT NULL,
    image_url TEXT,
    status TEXT DEFAULT 'draft' CHECK (status IN ('draft', 'scheduled', 'published', 'failed')),
    scheduled_at TIMESTAMPTZ,
    published_at TIMESTAMPTZ,
    external_post_id TEXT,  -- Facebook/Zalo post ID after publishing
    engagement JSONB DEFAULT '{"likes": 0, "comments": 0, "shares": 0}'::jsonb,
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_posts_agent ON posts(agent_id);
CREATE INDEX IF NOT EXISTS idx_posts_status ON posts(status);
CREATE INDEX IF NOT EXISTS idx_posts_scheduled ON posts(scheduled_at) WHERE status = 'scheduled';

ALTER TABLE posts ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Service full access posts" ON posts 
    FOR ALL 
    TO service_role 
    USING (true);

-- Broadcasts table for mass messaging
CREATE TABLE IF NOT EXISTS broadcasts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id UUID NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
    message TEXT NOT NULL,
    channel_filter TEXT DEFAULT 'all' CHECK (channel_filter IN ('all', 'telegram', 'facebook', 'zalo', 'webchat')),
    tag_filter TEXT[] DEFAULT '{}',
    sent_count INTEGER DEFAULT 0,
    failed_count INTEGER DEFAULT 0,
    skipped_count INTEGER DEFAULT 0,
    status TEXT DEFAULT 'pending' CHECK (status IN ('pending', 'sending', 'completed', 'failed')),
    created_at TIMESTAMPTZ DEFAULT now(),
    completed_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_broadcasts_agent ON broadcasts(agent_id);
CREATE INDEX IF NOT EXISTS idx_broadcasts_status ON broadcasts(status);

ALTER TABLE broadcasts ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Service full access broadcasts" ON broadcasts 
    FOR ALL 
    TO service_role 
    USING (true);

-- Update trigger for posts
CREATE OR REPLACE FUNCTION update_posts_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER posts_update_timestamp
    BEFORE UPDATE ON posts
    FOR EACH ROW
    EXECUTE FUNCTION update_posts_timestamp();
