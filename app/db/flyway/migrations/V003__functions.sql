-- V003: PostgreSQL functions for PostgREST RPC endpoints

-- validate_api_key: Called anonymously (no JWT needed) to authenticate API keys.
-- Returns tenant info if key is valid, empty result if not.
CREATE OR REPLACE FUNCTION validate_api_key(p_key_hash TEXT)
RETURNS TABLE(tenant_id TEXT, tenant_slug TEXT, user_id TEXT, key_id TEXT, username TEXT, role TEXT)
LANGUAGE sql SECURITY DEFINER AS $$
    -- Update last_used_at as side effect
    UPDATE api_keys SET last_used_at = NOW()
    WHERE key_hash = p_key_hash AND status = 'active';

    -- Return tenant + user info (LEFT JOIN: key may not be tied to a user)
    SELECT k.tenant_id::TEXT, t.slug::TEXT, k.user_id::TEXT, k.id::TEXT,
           u.username::TEXT, u.role::TEXT
    FROM api_keys k
    JOIN tenants t ON k.tenant_id = t.id
    LEFT JOIN users u ON k.user_id = u.id
    WHERE k.key_hash = p_key_hash
      AND k.status = 'active'
      AND t.status = 'active';
$$;

-- Grant anonymous access to validate_api_key (needed for auth flow)
GRANT EXECUTE ON FUNCTION validate_api_key(TEXT) TO app_anon;

-- get_tenant_stats: Admin function to get aggregate counts for a tenant.
CREATE OR REPLACE FUNCTION get_tenant_stats(p_tenant_id TEXT)
RETURNS JSON
LANGUAGE sql SECURITY DEFINER AS $$
    SELECT json_build_object(
        'users', (SELECT count(*) FROM users WHERE tenant_id = p_tenant_id),
        'drafts', (SELECT count(*) FROM tax_drafts WHERE tenant_id = p_tenant_id),
        'documents', (SELECT count(*) FROM documents WHERE tenant_id = p_tenant_id),
        'plaid_items', (SELECT count(*) FROM plaid_items WHERE tenant_id = p_tenant_id)
    );
$$;

GRANT EXECUTE ON FUNCTION get_tenant_stats(TEXT) TO app_admin;

-- upsert_tenant_plans: Atomic insert-or-update for plan limits (replaces MySQL REPLACE INTO).
CREATE OR REPLACE FUNCTION upsert_tenant_plans(
    p_tenant_id TEXT, p_plan_tier TEXT,
    p_api_calls_per_minute INTEGER, p_computations_per_day INTEGER,
    p_ocr_pages_per_month INTEGER, p_agent_messages_per_day INTEGER
) RETURNS VOID
LANGUAGE sql SECURITY DEFINER AS $$
    INSERT INTO tenant_plans
        (tenant_id, plan_tier, api_calls_per_minute, computations_per_day,
         ocr_pages_per_month, agent_messages_per_day, updated_at)
    VALUES (p_tenant_id, p_plan_tier, p_api_calls_per_minute, p_computations_per_day,
            p_ocr_pages_per_month, p_agent_messages_per_day, NOW())
    ON CONFLICT (tenant_id) DO UPDATE SET
        plan_tier = EXCLUDED.plan_tier,
        api_calls_per_minute = EXCLUDED.api_calls_per_minute,
        computations_per_day = EXCLUDED.computations_per_day,
        ocr_pages_per_month = EXCLUDED.ocr_pages_per_month,
        agent_messages_per_day = EXCLUDED.agent_messages_per_day,
        updated_at = NOW();
$$;

GRANT EXECUTE ON FUNCTION upsert_tenant_plans(TEXT, TEXT, INTEGER, INTEGER, INTEGER, INTEGER) TO app_admin;

-- upsert_billing_customer: Atomic insert-or-update for billing customers.
CREATE OR REPLACE FUNCTION upsert_billing_customer(
    p_tenant_id TEXT, p_stripe_customer_id TEXT,
    p_stripe_subscription_id TEXT, p_plan_tier TEXT
) RETURNS VOID
LANGUAGE sql SECURITY DEFINER AS $$
    INSERT INTO billing_customers
        (tenant_id, stripe_customer_id, stripe_subscription_id, plan_tier,
         subscription_status, created_at, updated_at)
    VALUES (p_tenant_id, p_stripe_customer_id, p_stripe_subscription_id, p_plan_tier,
            'active', NOW(), NOW())
    ON CONFLICT (tenant_id) DO UPDATE SET
        stripe_customer_id = EXCLUDED.stripe_customer_id,
        stripe_subscription_id = EXCLUDED.stripe_subscription_id,
        plan_tier = EXCLUDED.plan_tier,
        updated_at = NOW();
$$;

GRANT EXECUTE ON FUNCTION upsert_billing_customer(TEXT, TEXT, TEXT, TEXT) TO app_admin;
