-- AgentReady schema

CREATE EXTENSION IF NOT EXISTS pgcrypto;

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
    -- 768-dim Gemini embedding (gemini-embedding-001), stored as a JSON
    -- float array rather than a real `vector(768)` column: this project's
    -- dev Postgres has no pgvector extension available to install (not an
    -- oversight -- confirmed absent from pg_available_extensions, and the
    -- install directory isn't writable from this environment either). A
    -- deployment with pgvector available should switch this to
    -- `vector(768)` + an ivfflat/hnsw index and do the similarity search in
    -- SQL; here it's computed in Python (see app/semantic_search.py) over a
    -- category-scoped row set, which is fine at this dataset's scale.
    embedding JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- One row per order/payment attempt. Most rows are synthetic (seeded history
-- standing in for Razorpay Payments API data); `source` distinguishes those
-- from rows a real Razorpay webhook delivery wrote (app/webhooks.py) — the
-- Trust Engine's fetch_* functions aggregate over both identically, so a
-- live event simply adds to what's already there, no separate code path.
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
    source TEXT NOT NULL DEFAULT 'synthetic' CHECK (source IN ('synthetic', 'razorpay_live')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS refunds (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    transaction_id UUID NOT NULL REFERENCES transactions(id) ON DELETE CASCADE,
    reason_code TEXT NOT NULL,
    amount_paise BIGINT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('processed', 'pending', 'rejected')),
    source TEXT NOT NULL DEFAULT 'synthetic' CHECK (source IN ('synthetic', 'razorpay_live')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS disputes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    transaction_id UUID NOT NULL REFERENCES transactions(id) ON DELETE CASCADE,
    reason_code TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('open', 'won', 'lost')),
    source TEXT NOT NULL DEFAULT 'synthetic' CHECK (source IN ('synthetic', 'razorpay_live')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Raw Razorpay webhook deliveries (app/webhooks.py), every event received,
-- signature-verified, regardless of whether it was acted on. Separate from
-- audit_trail, which is scoped to mandates/buyer decisions, not payment
-- infrastructure events.
CREATE TABLE IF NOT EXISTS razorpay_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event_type TEXT NOT NULL,
    payload JSONB NOT NULL,
    received_at TIMESTAMPTZ NOT NULL DEFAULT now()
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

-- Issued by the Intent Agent; mandate_hash is an HMAC over the mandate's core
-- fields, standing in for AP2's cryptographic signature.
CREATE TABLE IF NOT EXISTS mandates (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    consumer_id TEXT NOT NULL,
    category_id UUID NOT NULL REFERENCES categories(id),
    budget_cap_paise BIGINT NOT NULL,
    deadline_days INT NOT NULL,
    goal_text TEXT NOT NULL,
    mandate_hash TEXT NOT NULL,
    issued_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at TIMESTAMPTZ NOT NULL,
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'expired', 'fulfilled', 'cancelled'))
);

-- One row per Buyer Agent decision-layer output (or checkout attempt) for a mandate.
-- `seq` is the authoritative ordering column: a single request logs several rows
-- inside one transaction, and Postgres's now() returns the same transaction-start
-- timestamp for all of them, so created_at alone can't be trusted to order rows
-- from the same request — seq (a plain auto-incrementing counter) can.
CREATE TABLE IF NOT EXISTS audit_trail (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    seq BIGSERIAL,
    mandate_id UUID NOT NULL REFERENCES mandates(id) ON DELETE CASCADE,
    layer TEXT NOT NULL,
    payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_products_merchant ON products(merchant_id);
CREATE INDEX IF NOT EXISTS idx_transactions_merchant ON transactions(merchant_id);
CREATE INDEX IF NOT EXISTS idx_refunds_transaction ON refunds(transaction_id);
CREATE INDEX IF NOT EXISTS idx_disputes_transaction ON disputes(transaction_id);
CREATE INDEX IF NOT EXISTS idx_trust_score_history_merchant ON trust_score_history(merchant_id);
CREATE INDEX IF NOT EXISTS idx_audit_trail_mandate ON audit_trail(mandate_id);
