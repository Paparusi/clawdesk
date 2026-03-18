-- Migration v9: Plan System & Usage Tracking
-- Run this after migration_v8.sql

-- Add plan and usage fields to profiles table
ALTER TABLE profiles ADD COLUMN IF NOT EXISTS plan TEXT DEFAULT 'free' CHECK (plan IN ('free', 'pro', 'business', 'enterprise'));
ALTER TABLE profiles ADD COLUMN IF NOT EXISTS plan_started_at TIMESTAMPTZ;
ALTER TABLE profiles ADD COLUMN IF NOT EXISTS plan_expires_at TIMESTAMPTZ;
ALTER TABLE profiles ADD COLUMN IF NOT EXISTS stripe_customer_id TEXT;

-- Usage tracking table (reset monthly)
CREATE TABLE IF NOT EXISTS usage (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    period TEXT NOT NULL,  -- '2026-03' format (year-month)
    ai_messages INTEGER DEFAULT 0,
    broadcast_sent INTEGER DEFAULT 0,
    ai_posts_generated INTEGER DEFAULT 0,
    api_calls INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE(user_id, period)
);

CREATE INDEX IF NOT EXISTS idx_usage_user_period ON usage(user_id, period);

ALTER TABLE usage ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Service full access usage" ON usage FOR ALL TO service_role USING (true);
