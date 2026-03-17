-- ClawDesk v2 Migration: RAG + Brainstorm + Tools
-- Run this in Supabase SQL Editor after initial schema

-- === FEATURE 2: RAG Knowledge Base ===

-- Knowledge chunks for RAG search
CREATE TABLE knowledge_chunks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    knowledge_id UUID NOT NULL REFERENCES knowledge_base(id) ON DELETE CASCADE,
    agent_id UUID NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
    content TEXT NOT NULL,
    chunk_index INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_chunks_agent ON knowledge_chunks(agent_id);
CREATE INDEX idx_chunks_knowledge ON knowledge_chunks(knowledge_id);
CREATE INDEX idx_chunks_content_search ON knowledge_chunks USING gin(to_tsvector('simple', content));

ALTER TABLE knowledge_chunks ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Users see own chunks" ON knowledge_chunks FOR ALL USING (agent_id IN (SELECT id FROM agents WHERE user_id = auth.uid()));
CREATE POLICY "Service full access chunks" ON knowledge_chunks FOR ALL TO service_role USING (true);


-- === FEATURE 1: Brainstorm Onboarding ===

-- Brainstorm sessions for agent setup
CREATE TABLE brainstorm_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id UUID NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
    messages JSONB DEFAULT '[]',  -- [{role, content, timestamp}]
    status TEXT DEFAULT 'active' CHECK (status IN ('active', 'finalized', 'cancelled')),
    generated_config JSONB,  -- {system_prompt, faq_entries, business_profile}
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_brainstorm_agent ON brainstorm_sessions(agent_id);

ALTER TABLE brainstorm_sessions ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Users see own brainstorm" ON brainstorm_sessions FOR ALL USING (agent_id IN (SELECT id FROM agents WHERE user_id = auth.uid()));
CREATE POLICY "Service full access brainstorm" ON brainstorm_sessions FOR ALL TO service_role USING (true);


-- === FEATURE 3: CSKH Tool System ===

-- Support tickets
CREATE TABLE tickets (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id UUID NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
    conversation_id UUID REFERENCES conversations(id) ON DELETE SET NULL,
    customer_name TEXT,
    customer_phone TEXT,
    customer_email TEXT,
    subject TEXT NOT NULL,
    description TEXT,
    priority TEXT DEFAULT 'medium' CHECK (priority IN ('low','medium','high','urgent')),
    status TEXT DEFAULT 'open' CHECK (status IN ('open','in_progress','resolved','closed')),
    category TEXT DEFAULT 'general',
    tags TEXT[] DEFAULT '{}',
    assigned_to TEXT,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now(),
    resolved_at TIMESTAMPTZ
);

CREATE INDEX idx_tickets_agent ON tickets(agent_id);
CREATE INDEX idx_tickets_conversation ON tickets(conversation_id);
CREATE INDEX idx_tickets_status ON tickets(status);
CREATE INDEX idx_tickets_priority ON tickets(priority);

ALTER TABLE tickets ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Users see own tickets" ON tickets FOR ALL USING (agent_id IN (SELECT id FROM agents WHERE user_id = auth.uid()));
CREATE POLICY "Service full access tickets" ON tickets FOR ALL TO service_role USING (true);


-- Add new columns to conversations for tool system
ALTER TABLE conversations ADD COLUMN IF NOT EXISTS tags TEXT[] DEFAULT '{}';
ALTER TABLE conversations ADD COLUMN IF NOT EXISTS escalated BOOLEAN DEFAULT false;
ALTER TABLE conversations ADD COLUMN IF NOT EXISTS customer_info JSONB DEFAULT '{}';  -- {name, phone, email, notes}
ALTER TABLE conversations ADD COLUMN IF NOT EXISTS metadata JSONB DEFAULT '{}';  -- For extensibility


-- Add new columns to agents for tool configuration
ALTER TABLE agents ADD COLUMN IF NOT EXISTS business_hours JSONB DEFAULT '{}';
-- Format: {"monday": {"open": "09:00", "close": "18:00", "enabled": true}, ...}

ALTER TABLE agents ADD COLUMN IF NOT EXISTS escalation_config JSONB DEFAULT '{"email": "", "telegram_chat_id": ""}';

ALTER TABLE agents ADD COLUMN IF NOT EXISTS tools_enabled TEXT[] DEFAULT ARRAY[
    'search_knowledge', 
    'collect_customer_info', 
    'check_business_hours', 
    'send_faq_answer', 
    'tag_conversation'
];

ALTER TABLE agents ADD COLUMN IF NOT EXISTS brainstorm_completed BOOLEAN DEFAULT false;


-- Add metadata to messages for tool calls
ALTER TABLE messages ADD COLUMN IF NOT EXISTS metadata JSONB DEFAULT '{}';
-- For storing tool_calls, tool_results, etc.


-- Trigger to update updated_at on tickets
CREATE TRIGGER tickets_updated_at
  BEFORE UPDATE ON tickets
  FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- Trigger to update updated_at on brainstorm_sessions
CREATE TRIGGER brainstorm_updated_at
  BEFORE UPDATE ON brainstorm_sessions
  FOR EACH ROW EXECUTE FUNCTION update_updated_at();


-- Update knowledge_base table to add metadata for chunking
ALTER TABLE knowledge_base ADD COLUMN IF NOT EXISTS chunk_count INTEGER DEFAULT 0;
ALTER TABLE knowledge_base ADD COLUMN IF NOT EXISTS metadata JSONB DEFAULT '{}';


-- === INDEXES FOR PERFORMANCE ===

CREATE INDEX idx_conversations_tags ON conversations USING gin(tags);
CREATE INDEX idx_conversations_escalated ON conversations(escalated) WHERE escalated = true;
CREATE INDEX idx_tickets_tags ON tickets USING gin(tags);
CREATE INDEX idx_agents_tools ON agents USING gin(tools_enabled);


-- === MIGRATION COMPLETE ===
-- Version: 2.0
-- Features: RAG Knowledge Base, Brainstorm Onboarding, CSKH Tool System
