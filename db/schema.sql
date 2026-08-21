-- AgentReady schema

CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS categories (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT UNIQUE NOT NULL
);

CREATE TABLE IF NOT EXISTS merchants (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    category_id UUID NOT NULL REFERENCES categories(id),
    declared_sla_days INT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS products (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    merchant_id UUID NOT NULL REFERENCES merchants(id) ON DELETE CASCADE,
    category_id UUID NOT NULL REFERENCES categories(id),
    name TEXT NOT NULL,
    description TEXT NOT NULL,
    price_paise BIGINT NOT NULL,
    embedding vector(768),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- One row per synthetic order/payment attempt (stands in for Razorpay Payments API data).
CREATE TABLE IF NOT EXISTS transactions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    merchant_id UUID NOT NULL REFERENCES merchants(id) ON DELETE CASCADE,
    product_id UUID REFERENCES products(id),
    razorpay_payment_id TEXT,
    amount_paise BIGINT NOT NULL,
    payment_method TEXT NOT NULL CHECK (payment_method IN ('card', 'upi', 'cod')),
    status TEXT NOT NULL CHECK (status IN ('captured', 'failed', 'refunded')),
    order_created_at TIMESTAMPTZ NOT NULL,
    -- For COD, the gap between order_created_at and payment_captured_at approximates
    -- delivery time, since capture only fires on delivery confirmation in that flow.
    payment_captured_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS refunds (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    transaction_id UUID NOT NULL REFERENCES transactions(id) ON DELETE CASCADE,
    reason_code TEXT NOT NULL,
    amount_paise BIGINT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('processed', 'pending', 'rejected')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS disputes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    transaction_id UUID NOT NULL REFERENCES transactions(id) ON DELETE CASCADE,
    reason_code TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('open', 'won', 'lost')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Synthetic in the demo — stands in for a review-platform signal in production.
CREATE TABLE IF NOT EXISTS reputation (
    merchant_id UUID PRIMARY KEY REFERENCES merchants(id) ON DELETE CASCADE,
    avg_rating NUMERIC(2,1) NOT NULL,
    review_count INT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Snapshots feed the Trust Mirror and Benchmark Agent; one row per scoring run.
CREATE TABLE IF NOT EXISTS trust_score_history (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    merchant_id UUID NOT NULL REFERENCES merchants(id) ON DELETE CASCADE,
    payment_trust NUMERIC(5,4) NOT NULL,
    promise_keeping NUMERIC(5,4) NOT NULL,
    price_fit NUMERIC(5,4) NOT NULL,
    reputation NUMERIC(5,4) NOT NULL,
    composite_score NUMERIC(5,4) NOT NULL,
    weights JSONB NOT NULL,
    computed_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_products_merchant ON products(merchant_id);
CREATE INDEX IF NOT EXISTS idx_transactions_merchant ON transactions(merchant_id);
CREATE INDEX IF NOT EXISTS idx_refunds_transaction ON refunds(transaction_id);
CREATE INDEX IF NOT EXISTS idx_disputes_transaction ON disputes(transaction_id);
CREATE INDEX IF NOT EXISTS idx_trust_score_history_merchant ON trust_score_history(merchant_id);
