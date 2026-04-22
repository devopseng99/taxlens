-- V002: PostgreSQL roles + Row-Level Security (RLS) for multi-tenancy
-- PostgREST uses JWT claims to set role + tenant_id per request.

-- Roles (idempotent — skip if they exist)
DO $$ BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'app_anon') THEN
        CREATE ROLE app_anon NOLOGIN;
    END IF;
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'app_tenant') THEN
        CREATE ROLE app_tenant NOLOGIN;
    END IF;
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'app_admin') THEN
        CREATE ROLE app_admin NOLOGIN;
    END IF;
END $$;

-- Authenticator role (PostgREST login role) — can switch to other roles
DO $$ BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'authenticator') THEN
        CREATE ROLE authenticator NOINHERIT LOGIN;
    END IF;
END $$;

GRANT app_anon TO authenticator;
GRANT app_tenant TO authenticator;
GRANT app_admin TO authenticator;

-- Schema usage for all roles
GRANT USAGE ON SCHEMA public TO app_anon, app_tenant, app_admin;

-- app_anon: minimal access (only RPC functions, no direct table access)
-- (Grants for validate_api_key RPC are in V003)

-- app_tenant: full CRUD on all tenant-scoped tables (RLS enforces isolation)
GRANT SELECT, INSERT, UPDATE, DELETE ON
    tenants, users, api_keys, oauth_clients, oauth_tokens,
    tax_drafts, documents, plaid_items,
    tenant_plans, usage_events, usage_daily, billing_customers
TO app_tenant;

-- app_admin: full access, bypasses RLS
GRANT ALL ON ALL TABLES IN SCHEMA public TO app_admin;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO app_admin;

-- Helper function: enable tenant RLS on a table (reusable convention)
CREATE OR REPLACE FUNCTION enable_tenant_rls(p_table TEXT) RETURNS VOID AS $$
BEGIN
    EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', p_table);
    EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY', p_table);
    -- Tenant policy: see only own rows
    EXECUTE format(
        'CREATE POLICY tenant_isolation ON %I FOR ALL TO app_tenant '
        'USING (tenant_id = current_setting(''request.jwt.claims'', true)::json->>''tenant_id'')',
        p_table
    );
    -- Admin policy: see all rows
    EXECUTE format(
        'CREATE POLICY admin_full_access ON %I FOR ALL TO app_admin USING (true)',
        p_table
    );
END;
$$ LANGUAGE plpgsql;

-- Enable RLS on all tenant-scoped tables
SELECT enable_tenant_rls('users');
SELECT enable_tenant_rls('api_keys');
SELECT enable_tenant_rls('oauth_clients');
SELECT enable_tenant_rls('oauth_tokens');
SELECT enable_tenant_rls('tax_drafts');
SELECT enable_tenant_rls('documents');
SELECT enable_tenant_rls('plaid_items');
SELECT enable_tenant_rls('tenant_plans');
SELECT enable_tenant_rls('usage_events');
SELECT enable_tenant_rls('usage_daily');
SELECT enable_tenant_rls('billing_customers');

-- Tenants table: special RLS (tenant can see own tenant row only)
ALTER TABLE tenants ENABLE ROW LEVEL SECURITY;
ALTER TABLE tenants FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_self ON tenants FOR ALL TO app_tenant
    USING (id = current_setting('request.jwt.claims', true)::json->>'tenant_id');
CREATE POLICY admin_tenants ON tenants FOR ALL TO app_admin USING (true);

-- Grant sequence usage for any SERIAL columns
GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO app_tenant, app_admin;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE ON SEQUENCES TO app_tenant, app_admin;
