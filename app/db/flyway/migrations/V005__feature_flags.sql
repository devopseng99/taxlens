-- V005: Per-tenant feature flags for free/paid tier gating.
-- Free tier: standard deduction + unlimited W-2s, login required.
-- All tiers get doc upload (NIST/IRS retention compliance).

CREATE TABLE IF NOT EXISTS tenant_features (
    tenant_id VARCHAR(36) PRIMARY KEY REFERENCES tenants(id),
    -- Core tool access (free tier: standard deduction + W-2 only)
    can_compute_tax BOOLEAN NOT NULL DEFAULT TRUE,
    can_upload_documents BOOLEAN NOT NULL DEFAULT TRUE,
    can_itemized_deductions BOOLEAN NOT NULL DEFAULT FALSE,
    can_schedule_c BOOLEAN NOT NULL DEFAULT FALSE,
    can_schedule_d BOOLEAN NOT NULL DEFAULT FALSE,
    can_1099_forms BOOLEAN NOT NULL DEFAULT FALSE,
    can_multi_state BOOLEAN NOT NULL DEFAULT FALSE,
    can_use_mcp BOOLEAN NOT NULL DEFAULT FALSE,
    can_use_plaid BOOLEAN NOT NULL DEFAULT FALSE,
    can_use_agent BOOLEAN NOT NULL DEFAULT FALSE,
    -- Quotas (NULL = unlimited)
    max_filings_per_year INTEGER DEFAULT 1,
    max_w2_uploads INTEGER,                    -- NULL = unlimited
    max_documents INTEGER DEFAULT 10,
    max_users INTEGER DEFAULT 1,
    -- Form type allowlist (free = W-2 only)
    allowed_form_types JSONB DEFAULT '["W-2"]'::jsonb,
    -- Early access
    early_access_enabled BOOLEAN NOT NULL DEFAULT FALSE,
    early_access_features JSONB DEFAULT '[]'::jsonb,
    -- Metadata
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- RLS: tenants see own features, admin sees all
ALTER TABLE tenant_features ENABLE ROW LEVEL SECURITY;

CREATE POLICY tenant_features_tenant ON tenant_features
    FOR SELECT TO app_tenant
    USING (tenant_id = current_setting('request.jwt.claims', true)::json->>'tenant_id');

CREATE POLICY tenant_features_admin ON tenant_features
    FOR ALL TO app_admin USING (true);

-- Audit trigger (reuse V004 function)
CREATE TRIGGER audit_tenant_features
    AFTER INSERT OR UPDATE OR DELETE ON tenant_features
    FOR EACH ROW EXECUTE FUNCTION audit_trigger_fn('tenant_id');

-- Grant access
GRANT SELECT ON tenant_features TO app_tenant;
GRANT ALL ON tenant_features TO app_admin;

-- RPC: upsert tenant features (called from onboarding + admin)
CREATE OR REPLACE FUNCTION upsert_tenant_features(
    p_tenant_id TEXT,
    p_can_compute_tax BOOLEAN DEFAULT TRUE,
    p_can_upload_documents BOOLEAN DEFAULT TRUE,
    p_can_itemized_deductions BOOLEAN DEFAULT FALSE,
    p_can_schedule_c BOOLEAN DEFAULT FALSE,
    p_can_schedule_d BOOLEAN DEFAULT FALSE,
    p_can_1099_forms BOOLEAN DEFAULT FALSE,
    p_can_multi_state BOOLEAN DEFAULT FALSE,
    p_can_use_mcp BOOLEAN DEFAULT FALSE,
    p_can_use_plaid BOOLEAN DEFAULT FALSE,
    p_can_use_agent BOOLEAN DEFAULT FALSE,
    p_max_filings_per_year INTEGER DEFAULT 1,
    p_max_w2_uploads INTEGER DEFAULT NULL,
    p_max_documents INTEGER DEFAULT 10,
    p_max_users INTEGER DEFAULT 1,
    p_allowed_form_types JSONB DEFAULT '["W-2"]'::jsonb,
    p_early_access_enabled BOOLEAN DEFAULT FALSE,
    p_early_access_features JSONB DEFAULT '[]'::jsonb
) RETURNS VOID
LANGUAGE plpgsql SECURITY DEFINER AS $$
BEGIN
    INSERT INTO tenant_features (
        tenant_id, can_compute_tax, can_upload_documents,
        can_itemized_deductions, can_schedule_c, can_schedule_d,
        can_1099_forms, can_multi_state, can_use_mcp, can_use_plaid, can_use_agent,
        max_filings_per_year, max_w2_uploads, max_documents, max_users,
        allowed_form_types, early_access_enabled, early_access_features, updated_at
    ) VALUES (
        p_tenant_id, p_can_compute_tax, p_can_upload_documents,
        p_can_itemized_deductions, p_can_schedule_c, p_can_schedule_d,
        p_can_1099_forms, p_can_multi_state, p_can_use_mcp, p_can_use_plaid, p_can_use_agent,
        p_max_filings_per_year, p_max_w2_uploads, p_max_documents, p_max_users,
        p_allowed_form_types, p_early_access_enabled, p_early_access_features, NOW()
    )
    ON CONFLICT (tenant_id) DO UPDATE SET
        can_compute_tax = EXCLUDED.can_compute_tax,
        can_upload_documents = EXCLUDED.can_upload_documents,
        can_itemized_deductions = EXCLUDED.can_itemized_deductions,
        can_schedule_c = EXCLUDED.can_schedule_c,
        can_schedule_d = EXCLUDED.can_schedule_d,
        can_1099_forms = EXCLUDED.can_1099_forms,
        can_multi_state = EXCLUDED.can_multi_state,
        can_use_mcp = EXCLUDED.can_use_mcp,
        can_use_plaid = EXCLUDED.can_use_plaid,
        can_use_agent = EXCLUDED.can_use_agent,
        max_filings_per_year = EXCLUDED.max_filings_per_year,
        max_w2_uploads = EXCLUDED.max_w2_uploads,
        max_documents = EXCLUDED.max_documents,
        max_users = EXCLUDED.max_users,
        allowed_form_types = EXCLUDED.allowed_form_types,
        early_access_enabled = EXCLUDED.early_access_enabled,
        early_access_features = EXCLUDED.early_access_features,
        updated_at = NOW();
END;
$$;

GRANT EXECUTE ON FUNCTION upsert_tenant_features TO app_admin;
