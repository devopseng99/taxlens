-- V004: Audit log table + triggers for business tables
-- Replaces Dolt's git-like versioning with explicit audit trail.

CREATE TABLE IF NOT EXISTS audit_log (
    id BIGSERIAL PRIMARY KEY,
    table_name VARCHAR(128) NOT NULL,
    operation VARCHAR(10) NOT NULL,  -- INSERT, UPDATE, DELETE
    row_id VARCHAR(255),
    old_data JSONB,
    new_data JSONB,
    committed_by VARCHAR(255) DEFAULT 'system',
    committed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    commit_message VARCHAR(512)
);

CREATE INDEX IF NOT EXISTS idx_audit_log_table ON audit_log(table_name, committed_at);
CREATE INDEX IF NOT EXISTS idx_audit_log_time ON audit_log(committed_at);

-- Generic audit trigger function.
-- TG_ARGV[0] = primary key column name (e.g. 'id', 'client_id', 'tenant_id')
CREATE OR REPLACE FUNCTION audit_trigger_fn() RETURNS TRIGGER
LANGUAGE plpgsql AS $$
DECLARE
    pk_col TEXT := TG_ARGV[0];
    pk_val TEXT;
    user_claim TEXT;
BEGIN
    -- Extract committer from JWT claims (PostgREST sets this)
    BEGIN
        user_claim := current_setting('request.jwt.claims', true)::json->>'user_id';
    EXCEPTION WHEN OTHERS THEN
        user_claim := 'system';
    END;

    IF TG_OP = 'DELETE' THEN
        EXECUTE format('SELECT ($1).%I::TEXT', pk_col) INTO pk_val USING OLD;
        INSERT INTO audit_log (table_name, operation, row_id, old_data, committed_by)
        VALUES (TG_TABLE_NAME, 'DELETE', pk_val, to_jsonb(OLD), COALESCE(user_claim, 'system'));
        RETURN OLD;
    ELSIF TG_OP = 'UPDATE' THEN
        EXECUTE format('SELECT ($1).%I::TEXT', pk_col) INTO pk_val USING NEW;
        INSERT INTO audit_log (table_name, operation, row_id, old_data, new_data, committed_by)
        VALUES (TG_TABLE_NAME, 'UPDATE', pk_val, to_jsonb(OLD), to_jsonb(NEW), COALESCE(user_claim, 'system'));
        RETURN NEW;
    ELSIF TG_OP = 'INSERT' THEN
        EXECUTE format('SELECT ($1).%I::TEXT', pk_col) INTO pk_val USING NEW;
        INSERT INTO audit_log (table_name, operation, row_id, new_data, committed_by)
        VALUES (TG_TABLE_NAME, 'INSERT', pk_val, to_jsonb(NEW), COALESCE(user_claim, 'system'));
        RETURN NEW;
    END IF;
    RETURN NULL;
END;
$$;

-- Apply audit triggers to business tables (skip high-volume usage_events, usage_daily)
CREATE TRIGGER audit_tenants AFTER INSERT OR UPDATE OR DELETE ON tenants
    FOR EACH ROW EXECUTE FUNCTION audit_trigger_fn('id');

CREATE TRIGGER audit_users AFTER INSERT OR UPDATE OR DELETE ON users
    FOR EACH ROW EXECUTE FUNCTION audit_trigger_fn('id');

CREATE TRIGGER audit_api_keys AFTER INSERT OR UPDATE OR DELETE ON api_keys
    FOR EACH ROW EXECUTE FUNCTION audit_trigger_fn('id');

CREATE TRIGGER audit_oauth_clients AFTER INSERT OR UPDATE OR DELETE ON oauth_clients
    FOR EACH ROW EXECUTE FUNCTION audit_trigger_fn('client_id');

CREATE TRIGGER audit_oauth_tokens AFTER INSERT OR UPDATE OR DELETE ON oauth_tokens
    FOR EACH ROW EXECUTE FUNCTION audit_trigger_fn('token_hash');

CREATE TRIGGER audit_tax_drafts AFTER INSERT OR UPDATE OR DELETE ON tax_drafts
    FOR EACH ROW EXECUTE FUNCTION audit_trigger_fn('id');

CREATE TRIGGER audit_documents AFTER INSERT OR UPDATE OR DELETE ON documents
    FOR EACH ROW EXECUTE FUNCTION audit_trigger_fn('proc_id');

CREATE TRIGGER audit_plaid_items AFTER INSERT OR UPDATE OR DELETE ON plaid_items
    FOR EACH ROW EXECUTE FUNCTION audit_trigger_fn('item_id');

CREATE TRIGGER audit_tenant_plans AFTER INSERT OR UPDATE OR DELETE ON tenant_plans
    FOR EACH ROW EXECUTE FUNCTION audit_trigger_fn('tenant_id');

CREATE TRIGGER audit_billing_customers AFTER INSERT OR UPDATE OR DELETE ON billing_customers
    FOR EACH ROW EXECUTE FUNCTION audit_trigger_fn('tenant_id');

-- Grant audit_log read access to admin
GRANT SELECT ON audit_log TO app_admin;
GRANT USAGE ON SEQUENCE audit_log_id_seq TO app_tenant, app_admin;
