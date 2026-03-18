-- Migration V5: AI Fanpage Manager - Facebook Comment Management
-- Date: 2026-03-18

-- Facebook comments table
CREATE TABLE IF NOT EXISTS facebook_comments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id UUID NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
    post_id TEXT NOT NULL,
    comment_id TEXT NOT NULL,
    parent_comment_id TEXT,  -- for reply threads
    sender_id TEXT NOT NULL,
    sender_name TEXT,
    message TEXT NOT NULL,
    ai_reply TEXT,
    ai_replied_at TIMESTAMPTZ,
    is_hidden BOOLEAN DEFAULT false,
    is_liked BOOLEAN DEFAULT false,
    is_spam BOOLEAN DEFAULT false,
    sentiment TEXT DEFAULT 'neutral',  -- positive/neutral/negative
    tags TEXT[] DEFAULT '{}',
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT now()
);

-- Indexes for performance
CREATE UNIQUE INDEX IF NOT EXISTS idx_fb_comments_comment_id ON facebook_comments(comment_id);
CREATE INDEX IF NOT EXISTS idx_fb_comments_agent ON facebook_comments(agent_id);
CREATE INDEX IF NOT EXISTS idx_fb_comments_post ON facebook_comments(post_id);
CREATE INDEX IF NOT EXISTS idx_fb_comments_sender ON facebook_comments(sender_id);
CREATE INDEX IF NOT EXISTS idx_fb_comments_created ON facebook_comments(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_fb_comments_unreplied ON facebook_comments(agent_id, ai_replied_at) WHERE ai_replied_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_fb_comments_spam ON facebook_comments(agent_id, is_spam) WHERE is_spam = true;

-- Row-Level Security
ALTER TABLE facebook_comments ENABLE ROW LEVEL SECURITY;

-- Service role has full access
CREATE POLICY "Service full access fb_comments" 
    ON facebook_comments FOR ALL 
    TO service_role 
    USING (true);

-- Users can only see comments for their own agents
CREATE POLICY "Users view own agent comments" 
    ON facebook_comments FOR SELECT 
    USING (
        agent_id IN (
            SELECT id FROM agents WHERE user_id = auth.uid()
        )
    );

-- Users can update comments for their own agents
CREATE POLICY "Users update own agent comments" 
    ON facebook_comments FOR UPDATE 
    USING (
        agent_id IN (
            SELECT id FROM agents WHERE user_id = auth.uid()
        )
    );

-- Users can delete comments for their own agents
CREATE POLICY "Users delete own agent comments" 
    ON facebook_comments FOR DELETE 
    USING (
        agent_id IN (
            SELECT id FROM agents WHERE user_id = auth.uid()
        )
    );

-- Function to calculate comment analytics
CREATE OR REPLACE FUNCTION get_comment_analytics(p_agent_id UUID, p_days INT DEFAULT 7)
RETURNS JSON AS $$
DECLARE
    result JSON;
BEGIN
    SELECT json_build_object(
        'total_comments', COUNT(*),
        'replied_count', COUNT(*) FILTER (WHERE ai_replied_at IS NOT NULL),
        'unreplied_count', COUNT(*) FILTER (WHERE ai_replied_at IS NULL),
        'reply_rate', ROUND(
            100.0 * COUNT(*) FILTER (WHERE ai_replied_at IS NOT NULL) / NULLIF(COUNT(*), 0), 
            2
        ),
        'spam_count', COUNT(*) FILTER (WHERE is_spam = true),
        'positive_count', COUNT(*) FILTER (WHERE sentiment = 'positive'),
        'neutral_count', COUNT(*) FILTER (WHERE sentiment = 'neutral'),
        'negative_count', COUNT(*) FILTER (WHERE sentiment = 'negative'),
        'avg_reply_time_seconds', EXTRACT(EPOCH FROM AVG(ai_replied_at - created_at) FILTER (WHERE ai_replied_at IS NOT NULL))
    )
    INTO result
    FROM facebook_comments
    WHERE agent_id = p_agent_id
      AND created_at >= NOW() - (p_days || ' days')::INTERVAL;
    
    RETURN result;
END;
$$ LANGUAGE plpgsql;
