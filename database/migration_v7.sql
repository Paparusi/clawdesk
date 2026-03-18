-- Migration v7: Automation Rules + Conversation Notes + Search

-- Automation Rules table
CREATE TABLE IF NOT EXISTS automation_rules (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id UUID NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    description TEXT,
    trigger_type TEXT NOT NULL CHECK (trigger_type IN (
        'keyword', 'first_message', 'no_reply_timeout', 
        'sentiment_negative', 'channel_specific', 'business_hours',
        'comment_keyword', 'tag_added'
    )),
    trigger_config JSONB DEFAULT '{}',
    action_type TEXT NOT NULL CHECK (action_type IN (
        'send_message', 'add_tag', 'assign_agent', 'create_ticket',
        'escalate', 'send_template', 'auto_reply_comment', 'hide_comment',
        'send_inbox', 'notify_staff'
    )),
    action_config JSONB DEFAULT '{}',
    is_active BOOLEAN DEFAULT true,
    priority INTEGER DEFAULT 0,
    execution_count INTEGER DEFAULT 0,
    last_executed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_automations_agent ON automation_rules(agent_id);
CREATE INDEX IF NOT EXISTS idx_automations_active ON automation_rules(is_active, agent_id);

ALTER TABLE automation_rules ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Service full access automations" ON automation_rules FOR ALL TO service_role USING (true);

-- Conversation Notes table
CREATE TABLE IF NOT EXISTS conversation_notes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id UUID NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    user_id UUID NOT NULL,
    content TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_conv_notes ON conversation_notes(conversation_id);
CREATE INDEX IF NOT EXISTS idx_conv_notes_created ON conversation_notes(conversation_id, created_at DESC);

ALTER TABLE conversation_notes ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Service full access notes" ON conversation_notes FOR ALL TO service_role USING (true);

-- Add index for message search (if not exists)
CREATE INDEX IF NOT EXISTS idx_messages_content_search ON messages USING gin(to_tsvector('simple', content));
CREATE INDEX IF NOT EXISTS idx_messages_conversation ON messages(conversation_id, created_at DESC);
