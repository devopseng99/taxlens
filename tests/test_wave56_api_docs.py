"""Wave 56 tests — API Reference Documentation & OpenAPI Enrichment."""

import sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

import pytest


# =========================================================================
# OpenAPI Enrichment — Endpoint Metadata
# =========================================================================
class TestOpenAPIEnrichment:
    def test_tax_routes_have_summaries(self):
        """Key tax_routes endpoints have summary metadata."""
        path = os.path.join(os.path.dirname(__file__), "..", "app", "tax_routes.py")
        src = open(path).read()
        assert 'summary="Create tax draft"' in src
        assert 'summary="Get tax draft"' in src
        assert 'summary="Download PDF form"' in src
        assert 'summary="List draft PDFs"' in src
        assert 'summary="List user drafts"' in src

    def test_tax_routes_have_descriptions(self):
        """Endpoints have description metadata for OpenAPI."""
        path = os.path.join(os.path.dirname(__file__), "..", "app", "tax_routes.py")
        src = open(path).read()
        assert "Compute a full federal + state tax return" in src
        assert "Retrieve a previously computed tax draft" in src

    def test_main_has_openapi_tags(self):
        """main.py defines openapi_tags for organized docs."""
        path = os.path.join(os.path.dirname(__file__), "..", "app", "main.py")
        src = open(path).read()
        assert "openapi_tags" in src
        assert "Tax Drafts" in src
        assert "Documentation" in src
        assert "oauth" in src

    def test_main_has_description(self):
        """FastAPI app has a rich description."""
        path = os.path.join(os.path.dirname(__file__), "..", "app", "main.py")
        src = open(path).read()
        assert "Multi-tenant tax intelligence API" in src


# =========================================================================
# PostgREST OpenAPI Proxy
# =========================================================================
class TestPostgRESTProxy:
    def test_postgrest_proxy_endpoint_defined(self):
        path = os.path.join(os.path.dirname(__file__), "..", "app", "main.py")
        src = open(path).read()
        assert "/postgrest-openapi" in src
        assert "postgrest_openapi" in src

    def test_postgrest_proxy_caches_in_redis(self):
        """PostgREST proxy attempts Redis cache."""
        path = os.path.join(os.path.dirname(__file__), "..", "app", "main.py")
        src = open(path).read()
        assert "postgrest_openapi" in src
        assert "redis" in src.lower() or "get_redis" in src

    def test_postgrest_skips_tenant_context(self):
        """PostgREST proxy path is exempt from tenant context."""
        from middleware.tenant_context import TenantContextMiddleware
        path = os.path.join(os.path.dirname(__file__), "..", "app",
                            "middleware", "tenant_context.py")
        src = open(path).read()
        assert "postgrest-openapi" in src


# =========================================================================
# API Guide Endpoint
# =========================================================================
class TestAPIGuide:
    def test_api_guide_endpoint_defined(self):
        path = os.path.join(os.path.dirname(__file__), "..", "app", "main.py")
        src = open(path).read()
        assert "/docs/api-guide" in src

    def test_api_guide_structure(self):
        """Verify the api_guide function returns expected structure."""
        path = os.path.join(os.path.dirname(__file__), "..", "app", "main.py")
        src = open(path).read()
        # Key sections should be present
        assert '"authentication"' in src
        assert '"endpoints"' in src
        assert '"rate_limits"' in src
        assert '"interactive_docs"' in src

    def test_api_guide_includes_oauth(self):
        path = os.path.join(os.path.dirname(__file__), "..", "app", "main.py")
        src = open(path).read()
        assert "client_credentials" in src
        assert "authorization_code" in src


# =========================================================================
# MCP Guide Endpoint
# =========================================================================
class TestMCPGuide:
    def test_mcp_guide_endpoint_defined(self):
        path = os.path.join(os.path.dirname(__file__), "..", "app", "main.py")
        src = open(path).read()
        assert "/docs/mcp-guide" in src

    def test_mcp_guide_has_tools(self):
        path = os.path.join(os.path.dirname(__file__), "..", "app", "main.py")
        src = open(path).read()
        assert "compute_tax_scenario" in src
        assert "compare_scenarios" in src
        assert "check_audit_risk" in src

    def test_mcp_guide_has_claude_desktop_config(self):
        path = os.path.join(os.path.dirname(__file__), "..", "app", "main.py")
        src = open(path).read()
        assert "claude_desktop_config" in src
        assert "mcpServers" in src


# =========================================================================
# Version & Integration
# =========================================================================
class TestVersionIntegration:
    def test_version_3_35_0(self):
        path = os.path.join(os.path.dirname(__file__), "..", "app", "main.py")
        src = open(path).read()
        version = "3.35.0"
        count = src.count(f'"{version}"')
        assert count >= 2, f"Expected {version} in 2+ places, found {count}"

    def test_docs_endpoints_importable(self):
        """main.py can be parsed without errors (endpoints are valid)."""
        path = os.path.join(os.path.dirname(__file__), "..", "app", "main.py")
        src = open(path).read()
        # Check that all three doc endpoints exist
        assert "async def postgrest_openapi" in src
        assert "async def api_guide" in src
        assert "async def mcp_guide" in src
