-- Migration v8: E-Commerce Features - Orders, Products, Quick Replies
-- ClawDesk Batch 9 - Vietnamese Shop Features

-- ============================================
-- ORDERS TABLE
-- ============================================
CREATE TABLE IF NOT EXISTS orders (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id UUID NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
    conversation_id UUID REFERENCES conversations(id),
    customer_name TEXT NOT NULL,
    customer_phone TEXT,
    customer_address TEXT,
    items JSONB DEFAULT '[]',  -- [{product_name, quantity, price, product_id}]
    subtotal NUMERIC(12,0) DEFAULT 0,
    shipping_fee NUMERIC(12,0) DEFAULT 0,
    discount NUMERIC(12,0) DEFAULT 0,
    total NUMERIC(12,0) DEFAULT 0,
    status TEXT DEFAULT 'new' CHECK (status IN ('new', 'confirmed', 'preparing', 'shipping', 'delivered', 'cancelled', 'returned')),
    payment_status TEXT DEFAULT 'unpaid' CHECK (payment_status IN ('unpaid', 'paid', 'refunded')),
    payment_method TEXT,
    shipping_method TEXT,
    tracking_number TEXT,
    notes TEXT,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_orders_agent ON orders(agent_id);
CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status);
CREATE INDEX IF NOT EXISTS idx_orders_conv ON orders(conversation_id);
CREATE INDEX IF NOT EXISTS idx_orders_phone ON orders(customer_phone);

ALTER TABLE orders ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Service full access orders" ON orders FOR ALL TO service_role USING (true);

-- ============================================
-- PRODUCTS TABLE
-- ============================================
CREATE TABLE IF NOT EXISTS products (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id UUID NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    description TEXT,
    price NUMERIC(12,0) NOT NULL DEFAULT 0,
    sale_price NUMERIC(12,0),
    category TEXT,
    sku TEXT,
    image_url TEXT,
    in_stock BOOLEAN DEFAULT true,
    stock_quantity INTEGER,
    variants JSONB DEFAULT '[]',  -- [{name: "Size M", price: 200000, in_stock: true}]
    tags TEXT[] DEFAULT '{}',
    metadata JSONB DEFAULT '{}',
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_products_agent ON products(agent_id);
CREATE INDEX IF NOT EXISTS idx_products_category ON products(category);
CREATE INDEX IF NOT EXISTS idx_products_active ON products(agent_id) WHERE is_active = true;

ALTER TABLE products ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Service full access products" ON products FOR ALL TO service_role USING (true);

-- ============================================
-- QUICK REPLIES TABLE
-- ============================================
CREATE TABLE IF NOT EXISTS quick_replies (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id UUID NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    shortcut TEXT,  -- e.g. "/gia" → triggers template
    category TEXT DEFAULT 'general',
    variables TEXT[] DEFAULT '{}',  -- ["customer_name", "product_name", "price"]
    use_count INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_quick_replies_agent ON quick_replies(agent_id);
CREATE INDEX IF NOT EXISTS idx_quick_replies_shortcut ON quick_replies(agent_id, shortcut);

ALTER TABLE quick_replies ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Service full access quick_replies" ON quick_replies FOR ALL TO service_role USING (true);

-- ============================================
-- PRE-BUILT QUICK REPLY TEMPLATES
-- ============================================
-- Note: These will be inserted when agent is created or can be added via API
-- Example templates for Vietnamese shops:
-- 1. /chao - Greeting
-- 2. /gia - Price inquiry
-- 3. /ship - Shipping info
-- 4. /doitra - Return policy
-- 5. /camonnhan - Order confirmation
-- 6. /ngoaigio - Out of office
