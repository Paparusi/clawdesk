-- Migration V3: Notifications, Enhanced Analytics, Customer Management
-- Run this migration to add new tables for upgraded ClawDesk features

-- Notifications table
CREATE TABLE IF NOT EXISTS notifications (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    agent_id UUID REFERENCES agents(id) ON DELETE CASCADE,
    type VARCHAR(50) NOT NULL, -- 'new_conversation', 'escalation', 'ticket_created', 'mention'
    title VARCHAR(255) NOT NULL,
    message TEXT,
    link VARCHAR(500), -- URL to navigate to
    is_read BOOLEAN DEFAULT FALSE,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    
    INDEX idx_notifications_user_id (user_id),
    INDEX idx_notifications_is_read (is_read),
    INDEX idx_notifications_created_at (created_at)
);

-- Enable RLS
ALTER TABLE notifications ENABLE ROW LEVEL SECURITY;

-- RLS policy: users can only see their own notifications
CREATE POLICY "Users can view their own notifications"
    ON notifications FOR SELECT
    USING (auth.uid() = user_id);

CREATE POLICY "Users can update their own notifications"
    ON notifications FOR UPDATE
    USING (auth.uid() = user_id);

-- Add saved_replies to agent settings (already handled in JSONB settings column, no migration needed)

-- Add customer metadata fields to conversations table (if not exists)
ALTER TABLE conversations 
    ADD COLUMN IF NOT EXISTS tags TEXT[] DEFAULT '{}',
    ADD COLUMN IF NOT EXISTS notes TEXT;

-- Create index for customer queries
CREATE INDEX IF NOT EXISTS idx_conversations_sender ON conversations(agent_id, sender_id);

-- Function to create notification
CREATE OR REPLACE FUNCTION create_notification(
    p_user_id UUID,
    p_agent_id UUID,
    p_type VARCHAR,
    p_title VARCHAR,
    p_message TEXT,
    p_link VARCHAR DEFAULT NULL
) RETURNS UUID AS $$
DECLARE
    new_id UUID;
BEGIN
    INSERT INTO notifications (user_id, agent_id, type, title, message, link)
    VALUES (p_user_id, p_agent_id, p_type, p_title, p_message, p_link)
    RETURNING id INTO new_id;
    
    RETURN new_id;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Trigger to create notification on conversation escalation
CREATE OR REPLACE FUNCTION notify_on_escalation() RETURNS TRIGGER AS $$
BEGIN
    IF NEW.metadata->>'escalated' = 'true' AND (OLD.metadata->>'escalated' IS NULL OR OLD.metadata->>'escalated' = 'false') THEN
        -- Get agent owner
        INSERT INTO notifications (user_id, agent_id, type, title, message, link)
        SELECT 
            a.user_id,
            NEW.agent_id,
            'escalation',
            'Cuộc hội thoại được escalate',
            'Khách hàng ' || NEW.sender_name || ' cần hỗ trợ',
            '/dashboard?tab=conversations&id=' || NEW.id
        FROM agents a
        WHERE a.id = NEW.agent_id;
    END IF;
    
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_notify_escalation
    AFTER UPDATE ON conversations
    FOR EACH ROW
    EXECUTE FUNCTION notify_on_escalation();

-- Analytics helper views

-- Daily message stats view
CREATE OR REPLACE VIEW daily_message_stats AS
SELECT 
    a.id as agent_id,
    a.user_id,
    DATE(m.created_at) as date,
    COUNT(*) as message_count,
    COUNT(DISTINCT c.id) as conversation_count
FROM agents a
JOIN conversations c ON c.agent_id = a.id
JOIN messages m ON m.conversation_id = c.id
GROUP BY a.id, a.user_id, DATE(m.created_at);

-- Customer summary view
CREATE OR REPLACE VIEW customer_summary AS
SELECT 
    c.agent_id,
    c.sender_id,
    c.sender_name,
    ARRAY_AGG(DISTINCT c.channel) as channels,
    COUNT(DISTINCT c.id) as total_conversations,
    MIN(c.created_at) as first_seen,
    MAX(c.updated_at) as last_seen,
    c.metadata
FROM conversations c
GROUP BY c.agent_id, c.sender_id, c.sender_name, c.metadata;

COMMENT ON TABLE notifications IS 'Real-time notifications for dashboard users';
COMMENT ON VIEW daily_message_stats IS 'Aggregated message statistics per agent per day';
COMMENT ON VIEW customer_summary IS 'Summary of unique customers per agent';
