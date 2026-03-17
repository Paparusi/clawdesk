-- ClawDesk Database Schema for Supabase PostgreSQL
-- Run this in Supabase SQL Editor after creating a new project

-- Users (managed by Supabase Auth, but we need a profiles table)
CREATE TABLE profiles (
  id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
  email TEXT NOT NULL,
  name TEXT,
  plan TEXT DEFAULT 'free' CHECK (plan IN ('free', 'pro', 'business')),
  created_at TIMESTAMPTZ DEFAULT now()
);

-- Agents
CREATE TABLE agents (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
  name TEXT NOT NULL DEFAULT 'My Agent',
  description TEXT DEFAULT '',
  system_prompt TEXT DEFAULT 'Bạn là trợ lý AI chăm sóc khách hàng. Trả lời thân thiện, chính xác, ngắn gọn.',
  llm_provider TEXT DEFAULT 'openai' CHECK (llm_provider IN ('openai', 'anthropic', 'google')),
  llm_model TEXT DEFAULT 'gpt-4o-mini',
  llm_api_key TEXT DEFAULT '',  -- encrypted in production
  settings JSONB DEFAULT '{"language": "vi", "max_tokens": 500, "temperature": 0.7, "fallback_message": "Xin lỗi, tôi không hiểu câu hỏi."}',
  active BOOLEAN DEFAULT true,
  messages_total INTEGER DEFAULT 0,
  messages_today INTEGER DEFAULT 0,
  last_message_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now()
);

-- Channels per agent
CREATE TABLE channels (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  agent_id UUID NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
  type TEXT NOT NULL CHECK (type IN ('telegram', 'facebook', 'zalo', 'webchat')),
  config JSONB NOT NULL DEFAULT '{}',  -- bot_token, page_token, etc.
  enabled BOOLEAN DEFAULT true,
  connected_at TIMESTAMPTZ DEFAULT now(),
  UNIQUE(agent_id, type)
);

-- Knowledge base entries
CREATE TABLE knowledge_base (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  agent_id UUID NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
  title TEXT NOT NULL,
  content TEXT NOT NULL,
  category TEXT DEFAULT 'general',
  created_at TIMESTAMPTZ DEFAULT now()
);

-- Conversations
CREATE TABLE conversations (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  agent_id UUID NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
  channel TEXT NOT NULL,
  sender_id TEXT NOT NULL,
  sender_name TEXT DEFAULT '',
  message_count INTEGER DEFAULT 0,
  last_message_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ DEFAULT now(),
  UNIQUE(agent_id, channel, sender_id)
);

-- Messages
CREATE TABLE messages (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  conversation_id UUID NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
  role TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
  content TEXT NOT NULL,
  created_at TIMESTAMPTZ DEFAULT now()
);

-- Indexes
CREATE INDEX idx_agents_user ON agents(user_id);
CREATE INDEX idx_channels_agent ON channels(agent_id);
CREATE INDEX idx_kb_agent ON knowledge_base(agent_id);
CREATE INDEX idx_conversations_agent ON conversations(agent_id);
CREATE INDEX idx_messages_conversation ON messages(conversation_id);
CREATE INDEX idx_messages_created ON messages(created_at);

-- Row Level Security
ALTER TABLE profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE agents ENABLE ROW LEVEL SECURITY;
ALTER TABLE channels ENABLE ROW LEVEL SECURITY;
ALTER TABLE knowledge_base ENABLE ROW LEVEL SECURITY;
ALTER TABLE conversations ENABLE ROW LEVEL SECURITY;
ALTER TABLE messages ENABLE ROW LEVEL SECURITY;

-- RLS Policies (users can only see their own data)
CREATE POLICY "Users see own profile" ON profiles FOR ALL USING (id = auth.uid());
CREATE POLICY "Users see own agents" ON agents FOR ALL USING (user_id = auth.uid());
CREATE POLICY "Users see own channels" ON channels FOR ALL USING (agent_id IN (SELECT id FROM agents WHERE user_id = auth.uid()));
CREATE POLICY "Users see own kb" ON knowledge_base FOR ALL USING (agent_id IN (SELECT id FROM agents WHERE user_id = auth.uid()));
CREATE POLICY "Users see own conversations" ON conversations FOR ALL USING (agent_id IN (SELECT id FROM agents WHERE user_id = auth.uid()));
CREATE POLICY "Users see own messages" ON messages FOR ALL USING (conversation_id IN (SELECT id FROM conversations WHERE agent_id IN (SELECT id FROM agents WHERE user_id = auth.uid())));

-- Service role can access everything (for webhooks)
CREATE POLICY "Service full access profiles" ON profiles FOR ALL TO service_role USING (true);
CREATE POLICY "Service full access agents" ON agents FOR ALL TO service_role USING (true);
CREATE POLICY "Service full access channels" ON channels FOR ALL TO service_role USING (true);
CREATE POLICY "Service full access kb" ON knowledge_base FOR ALL TO service_role USING (true);
CREATE POLICY "Service full access conversations" ON conversations FOR ALL TO service_role USING (true);
CREATE POLICY "Service full access messages" ON messages FOR ALL TO service_role USING (true);

-- Auto-create profile on signup
CREATE OR REPLACE FUNCTION handle_new_user()
RETURNS TRIGGER AS $$
BEGIN
  INSERT INTO profiles (id, email, name)
  VALUES (NEW.id, NEW.email, COALESCE(NEW.raw_user_meta_data->>'name', split_part(NEW.email, '@', 1)));
  RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

CREATE TRIGGER on_auth_user_created
  AFTER INSERT ON auth.users
  FOR EACH ROW EXECUTE FUNCTION handle_new_user();

-- Updated_at trigger
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER agents_updated_at
  BEFORE UPDATE ON agents
  FOR EACH ROW EXECUTE FUNCTION update_updated_at();
