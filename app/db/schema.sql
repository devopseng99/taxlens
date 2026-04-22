-- TaxLens Multi-Tenant Schema for Dolt
-- All tables scoped by tenant_id for data isolation.
-- Dolt provides git-like version control: every write is auto-committed.

CREATE TABLE IF NOT EXISTS tenants (
    id VARCHAR(36) PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    slug VARCHAR(64) NOT NULL UNIQUE,
    plan_tier VARCHAR(32) NOT NULL DEFAULT 'starter',
    status VARCHAR(16) NOT NULL DEFAULT 'active',
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL
);

CREATE TABLE IF NOT EXISTS users (
    id VARCHAR(36) PRIMARY KEY,
    tenant_id VARCHAR(36) NOT NULL,
    username VARCHAR(255) NOT NULL,
    email VARCHAR(255),
    role VARCHAR(32) NOT NULL DEFAULT 'member',
    created_at DATETIME NOT NULL,
    UNIQUE KEY uq_tenant_user (tenant_id, username),
    FOREIGN KEY (tenant_id) REFERENCES tenants(id)
);

CREATE TABLE IF NOT EXISTS api_keys (
    id VARCHAR(36) PRIMARY KEY,
    tenant_id VARCHAR(36) NOT NULL,
    user_id VARCHAR(36),
    key_hash VARCHAR(64) NOT NULL,
    key_prefix VARCHAR(12) NOT NULL,
    name VARCHAR(255),
    scopes JSON,
    status VARCHAR(16) NOT NULL DEFAULT 'active',
    created_at DATETIME NOT NULL,
    last_used_at DATETIME,
    expires_at DATETIME,
    FOREIGN KEY (tenant_id) REFERENCES tenants(id),
    FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS oauth_clients (
    client_id VARCHAR(255) PRIMARY KEY,
    tenant_id VARCHAR(36) NOT NULL,
    client_secret_hash VARCHAR(64) NOT NULL,
    client_name VARCHAR(255),
    redirect_uris JSON NOT NULL,
    grant_types JSON NOT NULL,
    scopes JSON,
    status VARCHAR(16) NOT NULL DEFAULT 'active',
    created_at DATETIME NOT NULL,
    FOREIGN KEY (tenant_id) REFERENCES tenants(id)
);

CREATE TABLE IF NOT EXISTS oauth_tokens (
    token_hash VARCHAR(64) PRIMARY KEY,
    client_id VARCHAR(255) NOT NULL,
    tenant_id VARCHAR(36) NOT NULL,
    user_id VARCHAR(36),
    token_type VARCHAR(16) NOT NULL,
    scopes JSON,
    expires_at BIGINT,
    code_challenge VARCHAR(255),
    code_challenge_method VARCHAR(10),
    redirect_uri TEXT,
    created_at DATETIME NOT NULL,
    FOREIGN KEY (client_id) REFERENCES oauth_clients(client_id),
    FOREIGN KEY (tenant_id) REFERENCES tenants(id)
);

CREATE TABLE IF NOT EXISTS tax_drafts (
    id VARCHAR(36) PRIMARY KEY,
    tenant_id VARCHAR(36) NOT NULL,
    username VARCHAR(255) NOT NULL,
    filing_status VARCHAR(8) NOT NULL,
    filer_name VARCHAR(255),
    residence_state VARCHAR(2),
    total_income DECIMAL(15,2),
    agi DECIMAL(15,2),
    federal_tax DECIMAL(15,2),
    net_refund DECIMAL(15,2),
    result_json JSON,
    input_json JSON,
    pdf_forms JSON,
    storage_path VARCHAR(512),
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    INDEX idx_tenant_user (tenant_id, username),
    FOREIGN KEY (tenant_id) REFERENCES tenants(id)
);

CREATE TABLE IF NOT EXISTS documents (
    proc_id VARCHAR(36) PRIMARY KEY,
    tenant_id VARCHAR(36) NOT NULL,
    username VARCHAR(255) NOT NULL,
    filename VARCHAR(512) NOT NULL,
    content_type VARCHAR(128),
    size_bytes BIGINT,
    sha256 VARCHAR(64),
    form_type VARCHAR(32),
    has_ocr TINYINT(1) DEFAULT 0,
    storage_path VARCHAR(512) NOT NULL,
    uploaded_at DATETIME NOT NULL,
    INDEX idx_tenant_user (tenant_id, username),
    FOREIGN KEY (tenant_id) REFERENCES tenants(id)
);

CREATE TABLE IF NOT EXISTS plaid_items (
    item_id VARCHAR(255) PRIMARY KEY,
    tenant_id VARCHAR(36) NOT NULL,
    username VARCHAR(255) NOT NULL,
    institution_name VARCHAR(255),
    encrypted_token TEXT NOT NULL,
    environment VARCHAR(16),
    has_sync TINYINT(1) DEFAULT 0,
    connected_at DATETIME NOT NULL,
    last_synced_at DATETIME,
    INDEX idx_tenant_user (tenant_id, username),
    FOREIGN KEY (tenant_id) REFERENCES tenants(id)
);

CREATE TABLE IF NOT EXISTS tenant_plans (
    tenant_id VARCHAR(36) PRIMARY KEY,
    plan_tier VARCHAR(32) NOT NULL DEFAULT 'starter',
    api_calls_per_minute INT NOT NULL DEFAULT 30,
    computations_per_day INT NOT NULL DEFAULT 50,
    ocr_pages_per_month INT NOT NULL DEFAULT 100,
    agent_messages_per_day INT NOT NULL DEFAULT 100,
    updated_at DATETIME NOT NULL,
    FOREIGN KEY (tenant_id) REFERENCES tenants(id)
);

CREATE TABLE IF NOT EXISTS usage_events (
    id VARCHAR(36) PRIMARY KEY,
    tenant_id VARCHAR(36) NOT NULL,
    event_type VARCHAR(32) NOT NULL,
    endpoint VARCHAR(255),
    metadata_json JSON,
    created_at DATETIME NOT NULL,
    INDEX idx_tenant_type_date (tenant_id, event_type, created_at),
    FOREIGN KEY (tenant_id) REFERENCES tenants(id)
);

CREATE TABLE IF NOT EXISTS usage_daily (
    id VARCHAR(36) PRIMARY KEY,
    tenant_id VARCHAR(36) NOT NULL,
    event_type VARCHAR(32) NOT NULL,
    event_date DATE NOT NULL,
    event_count INT NOT NULL DEFAULT 0,
    updated_at DATETIME NOT NULL,
    UNIQUE KEY uq_tenant_type_date (tenant_id, event_type, event_date),
    FOREIGN KEY (tenant_id) REFERENCES tenants(id)
);

CREATE TABLE IF NOT EXISTS billing_customers (
    tenant_id VARCHAR(36) PRIMARY KEY,
    stripe_customer_id VARCHAR(255) NOT NULL UNIQUE,
    stripe_subscription_id VARCHAR(255),
    plan_tier VARCHAR(32) NOT NULL DEFAULT 'starter',
    subscription_status VARCHAR(32) NOT NULL DEFAULT 'active',
    current_period_end DATETIME,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    FOREIGN KEY (tenant_id) REFERENCES tenants(id)
);
