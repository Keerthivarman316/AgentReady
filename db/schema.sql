-- AgentReady initial schema
-- Stage 0: just proves pgvector wiring; real merchant/catalog/trust tables land in Stage 1.

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS merchants (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    category TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
