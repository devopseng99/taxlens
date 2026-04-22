-- V001: TaxLens Multi-Tenant Schema (PostgreSQL)
-- Converted from Dolt MySQL syntax. All tables scoped by tenant_id.

CREATE TABLE IF NOT EXISTS tenants (
    id VARCHAR(36) PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    slug VARCHAR(64) NOT NULL UNIQUE,
    plan_tier VARCHAR(32) NOT NULL DEFAULT 'starter',
    status VARCHAR(16) NOT NULL DEFAULT 'active',
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS users (
    id VARCHAR(36) PRIMARY KEY,
    tenant_id VARCHAR(36) NOT NULL REFERENCES tenants(id),
    username VARCHAR(255) NOT NULL,
    email VARCHAR(255),
    role VARCHAR(32) NOT NULL DEFAULT 'member',
    created_at TIMESTAMPTZ NOT NULL,
    UNIQUE (tenant_id, username)
);

CREATE TABLE IF NOT EXISTS api_keys (
    id VARCHAR(36) PRIMARY KEY,
    tenant_id VARCHAR(36) NOT NULL REFERENCES tenants(id),
    user_id VARCHAR(36) REFERENCES users(id),
    key_hash VARCHAR(64) NOT NULL,
    key_prefix VARCHAR(12) NOT NULL,
    name VARCHAR(255),
    scopes JSONB,
    status VARCHAR(16) NOT NULL DEFAULT 'active',
    created_at TIMESTAMPTZ NOT NULL,
    last_used_at TIMESTAMPTZ,
    expires_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS oauth_clients (
    client_id VARCHAR(255) PRIMARY KEY,
    tenant_id VARCHAR(36) NOT NULL REFERENCES tenants(id),
    client_secret_hash VARCHAR(64) NOT NULL,
    client_name VARCHAR(255),
    redirect_uris JSONB NOT NULL,
    grant_types JSONB NOT NULL,
    scopes JSONB,
    status VARCHAR(16) NOT NULL DEFAULT 'active',
    created_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS oauth_tokens (
    token_hash VARCHAR(64) PRIMARY KEY,
    client_id VARCHAR(255) NOT NULL REFERENCES oauth_clients(client_id),
    tenant_id VARCHAR(36) NOT NULL REFERENCES tenants(id),
    user_id VARCHAR(36),
    token_type VARCHAR(16) NOT NULL,
    scopes JSONB,
    expires_at BIGINT,
    code_challenge VARCHAR(255),
    code_challenge_method VARCHAR(10),
    redirect_uri TEXT,
    created_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS tax_drafts (
    id VARCHAR(36) PRIMARY KEY,
    tenant_id VARCHAR(36) NOT NULL REFERENCES tenants(id),
    username VARCHAR(255) NOT NULL,
    filing_status VARCHAR(8) NOT NULL,
    filer_name VARCHAR(255),
    residence_state VARCHAR(2),
    total_income NUMERIC(15,2),
    agi NUMERIC(15,2),
    federal_tax NUMERIC(15,2),
    net_refund NUMERIC(15,2),
    result_json JSONB,
    input_json JSONB,
    pdf_forms JSONB,
    storage_path VARCHAR(512),
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_tax_drafts_tenant_user ON tax_drafts(tenant_id, username);

CREATE TABLE IF NOT EXISTS documents (
    proc_id VARCHAR(36) PRIMARY KEY,
    tenant_id VARCHAR(36) NOT NULL REFERENCES tenants(id),
    username VARCHAR(255) NOT NULL,
    filename VARCHAR(512) NOT NULL,
    content_type VARCHAR(128),
    size_bytes BIGINT,
    sha256 VARCHAR(64),
    form_type VARCHAR(32),
    has_ocr BOOLEAN DEFAULT FALSE,
    storage_path VARCHAR(512) NOT NULL,
    uploaded_at TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_documents_tenant_user ON documents(tenant_id, username);

CREATE TABLE IF NOT EXISTS plaid_items (
    item_id VARCHAR(255) PRIMARY KEY,
    tenant_id VARCHAR(36) NOT NULL REFERENCES tenants(id),
    username VARCHAR(255) NOT NULL,
    institution_name VARCHAR(255),
    encrypted_token TEXT NOT NULL,
    environment VARCHAR(16),
    has_sync BOOLEAN DEFAULT FALSE,
    connected_at TIMESTAMPTZ NOT NULL,
    last_synced_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_plaid_items_tenant_user ON plaid_items(tenant_id, username);

CREATE TABLE IF NOT EXISTS tenant_plans (
    tenant_id VARCHAR(36) PRIMARY KEY REFERENCES tenants(id),
    plan_tier VARCHAR(32) NOT NULL DEFAULT 'starter',
    api_calls_per_minute INTEGER NOT NULL DEFAULT 30,
    computations_per_day INTEGER NOT NULL DEFAULT 50,
    ocr_pages_per_month INTEGER NOT NULL DEFAULT 100,
    agent_messages_per_day INTEGER NOT NULL DEFAULT 100,
    updated_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS usage_events (
    id VARCHAR(36) PRIMARY KEY,
    tenant_id VARCHAR(36) NOT NULL REFERENCES tenants(id),
    event_type VARCHAR(32) NOT NULL,
    endpoint VARCHAR(255),
    metadata_json JSONB,
    created_at TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_usage_events_tenant_type_date
    ON usage_events(tenant_id, event_type, created_at);

CREATE TABLE IF NOT EXISTS usage_daily (
    id VARCHAR(36) PRIMARY KEY,
    tenant_id VARCHAR(36) NOT NULL REFERENCES tenants(id),
    event_type VARCHAR(32) NOT NULL,
    event_date DATE NOT NULL,
    event_count INTEGER NOT NULL DEFAULT 0,
    updated_at TIMESTAMPTZ NOT NULL,
    UNIQUE (tenant_id, event_type, event_date)
);

CREATE TABLE IF NOT EXISTS billing_customers (
    tenant_id VARCHAR(36) PRIMARY KEY REFERENCES tenants(id),
    stripe_customer_id VARCHAR(255) NOT NULL UNIQUE,
    stripe_subscription_id VARCHAR(255),
    plan_tier VARCHAR(32) NOT NULL DEFAULT 'starter',
    subscription_status VARCHAR(32) NOT NULL DEFAULT 'active',
    current_period_end TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL
);
