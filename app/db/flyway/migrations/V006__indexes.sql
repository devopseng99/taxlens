-- V006: Add missing indexes for performance
-- Critical: api_keys(key_hash) is queried on EVERY authenticated request

-- Auth lookups (every request)
CREATE INDEX IF NOT EXISTS idx_api_keys_key_hash ON api_keys(key_hash);
CREATE INDEX IF NOT EXISTS idx_api_keys_status ON api_keys(status) WHERE status = 'active';

-- OAuth token lookups
CREATE INDEX IF NOT EXISTS idx_oauth_tokens_token_hash ON oauth_tokens(token_hash);

-- Usage analytics queries
CREATE INDEX IF NOT EXISTS idx_usage_events_tenant_type_time
    ON usage_events(tenant_id, event_type, created_at DESC);

-- Billing customer lookups
CREATE INDEX IF NOT EXISTS idx_billing_customers_tenant
    ON billing_customers(tenant_id);
CREATE INDEX IF NOT EXISTS idx_billing_customers_stripe
    ON billing_customers(stripe_customer_id);

-- Feature flag lookups (every gated request)
CREATE INDEX IF NOT EXISTS idx_tenant_features_tenant
    ON tenant_features(tenant_id);
