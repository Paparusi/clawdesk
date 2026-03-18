-- Migration V4: Live Chat - Manual Reply, Handoff, Status Management
-- Essential CSKH features for staff intervention and conversation management

-- Add mode column to conversations (ai/manual/hybrid)
ALTER TABLE conversations 
    ADD COLUMN IF NOT EXISTS mode TEXT DEFAULT 'ai' 
    CHECK (mode IN ('ai', 'manual', 'hybrid'));

-- Add status column to conversations (active/waiting/resolved/closed)
ALTER TABLE conversations 
    ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'active' 
    CHECK (status IN ('active', 'waiting', 'resolved', 'closed'));

-- Add metadata to messages for tracking manual vs AI replies
ALTER TABLE messages 
    ADD COLUMN IF NOT EXISTS metadata JSONB DEFAULT '{}';

-- Add typing indicator tracking
CREATE TABLE IF NOT EXISTS typing_indicators (
    conversation_id UUID PRIMARY KEY REFERENCES conversations(id) ON DELETE CASCADE,
    is_typing BOOLEAN DEFAULT FALSE,
    staff_name TEXT,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_conversations_mode ON conversations(mode);
CREATE INDEX IF NOT EXISTS idx_conversations_status ON conversations(status);
CREATE INDEX IF NOT EXISTS idx_conversations_mode_status ON conversations(agent_id, mode, status);
CREATE INDEX IF NOT EXISTS idx_messages_metadata ON messages USING gin(metadata);

-- Enable RLS on typing_indicators
ALTER TABLE typing_indicators ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Service full access typing" ON typing_indicators FOR ALL TO service_role USING (true);
CREATE POLICY "Users see typing for own agents" ON typing_indicators FOR SELECT 
    USING (conversation_id IN (
        SELECT c.id FROM conversations c 
        JOIN agents a ON a.id = c.agent_id 
        WHERE a.user_id = auth.uid()
    ));

-- Function to auto-update typing indicator timestamp
CREATE OR REPLACE FUNCTION update_typing_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER typing_updated_at
    BEFORE UPDATE ON typing_indicators
    FOR EACH ROW EXECUTE FUNCTION update_typing_timestamp();

-- Function to auto-set conversation status based on mode changes
CREATE OR REPLACE FUNCTION auto_status_on_escalation() RETURNS TRIGGER AS $$
BEGIN
    -- If mode changes to manual (escalated), set status to waiting
    IF NEW.mode = 'manual' AND OLD.mode != 'manual' THEN
        NEW.status = 'waiting';
    END IF;
    
    -- If mode changes back to ai, set status to active
    IF NEW.mode = 'ai' AND OLD.mode != 'ai' AND NEW.status = 'waiting' THEN
        NEW.status = 'active';
    END IF;
    
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_auto_status
    BEFORE UPDATE ON conversations
    FOR EACH ROW
    WHEN (NEW.mode IS DISTINCT FROM OLD.mode)
    EXECUTE FUNCTION auto_status_on_escalation();

-- View for escalated conversations (waiting for staff)
CREATE OR REPLACE VIEW escalated_conversations AS
SELECT 
    c.*,
    a.name as agent_name,
    a.user_id,
    (SELECT COUNT(*) FROM messages m WHERE m.conversation_id = c.id) as total_messages,
    (SELECT content FROM messages m WHERE m.conversation_id = c.id ORDER BY created_at DESC LIMIT 1) as last_message
FROM conversations c
JOIN agents a ON a.id = c.agent_id
WHERE c.mode IN ('manual', 'hybrid') OR c.status = 'waiting'
ORDER BY c.last_message_at DESC;

-- Add escalation_config to agents settings (for Telegram notification)
-- This is already handled in JSONB settings column, no migration needed

COMMENT ON COLUMN conversations.mode IS 'Conversation mode: ai (auto-reply), manual (staff only), hybrid (AI draft + staff approve)';
COMMENT ON COLUMN conversations.status IS 'Conversation status: active, waiting (escalated), resolved, closed';
COMMENT ON COLUMN messages.metadata IS 'Additional message data: {manual: true, staff_name: "...", tool_usage: [...]}';
COMMENT ON TABLE typing_indicators IS 'Real-time typing status for conversations';
COMMENT ON VIEW escalated_conversations IS 'All conversations requiring staff attention';
