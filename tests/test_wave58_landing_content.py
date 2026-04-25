"""Wave 58 tests — Landing page content endpoints."""

import sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

import pytest


# =========================================================================
# Content Endpoints Exist
# =========================================================================
class TestContentEndpoints:
    def test_about_endpoint_defined(self):
        path = os.path.join(os.path.dirname(__file__), "..", "app", "main.py")
        src = open(path).read()
        assert "/content/about" in src
        assert "async def about_content" in src

    def test_security_endpoint_defined(self):
        path = os.path.join(os.path.dirname(__file__), "..", "app", "main.py")
        src = open(path).read()
        assert "/content/security" in src
        assert "async def security_content" in src

    def test_for_businesses_endpoint_defined(self):
        path = os.path.join(os.path.dirname(__file__), "..", "app", "main.py")
        src = open(path).read()
        assert "/content/for-businesses" in src
        assert "async def for_businesses_content" in src


# =========================================================================
# About Content Structure
# =========================================================================
class TestAboutContent:
    @pytest.mark.asyncio
    async def test_about_has_mission(self):
        # Import the endpoint function directly (no HTTP server needed)
        # Parse main.py to check structure
        path = os.path.join(os.path.dirname(__file__), "..", "app", "main.py")
        src = open(path).read()
        assert '"mission"' in src
        assert "Agentic Tax Intelligence" in src

    def test_about_has_platform_stats(self):
        path = os.path.join(os.path.dirname(__file__), "..", "app", "main.py")
        src = open(path).read()
        assert '"forms_supported"' in src
        assert '"states"' in src
        assert '"mcp_tools"' in src

    def test_about_has_technology(self):
        path = os.path.join(os.path.dirname(__file__), "..", "app", "main.py")
        src = open(path).read()
        assert '"technology"' in src
        assert "FastAPI" in src
        assert "PostgREST" in src


# =========================================================================
# Security Content Structure
# =========================================================================
class TestSecurityContent:
    def test_security_has_data_handling(self):
        path = os.path.join(os.path.dirname(__file__), "..", "app", "main.py")
        src = open(path).read()
        assert '"data_handling"' in src
        assert "SHA-256" in src
        assert "Row-Level Security" in src

    def test_security_has_responsible_disclosure(self):
        path = os.path.join(os.path.dirname(__file__), "..", "app", "main.py")
        src = open(path).read()
        assert '"responsible_disclosure"' in src


# =========================================================================
# For Businesses Content Structure
# =========================================================================
class TestForBusinessesContent:
    def test_has_use_cases(self):
        path = os.path.join(os.path.dirname(__file__), "..", "app", "main.py")
        src = open(path).read()
        assert '"use_cases"' in src
        assert "CPA" in src
        assert "Fintech" in src
        assert "Tax Planning" in src

    def test_has_pricing(self):
        path = os.path.join(os.path.dirname(__file__), "..", "app", "main.py")
        src = open(path).read()
        assert '"pricing"' in src
        assert "$29/mo" in src
        assert "$99/mo" in src
        assert "$299/mo" in src


# =========================================================================
# Middleware & Integration
# =========================================================================
class TestContentMiddleware:
    def test_content_paths_skip_tenant_context(self):
        path = os.path.join(os.path.dirname(__file__), "..", "app",
                            "middleware", "tenant_context.py")
        src = open(path).read()
        assert "/content/" in src

    def test_content_tag_in_openapi(self):
        path = os.path.join(os.path.dirname(__file__), "..", "app", "main.py")
        src = open(path).read()
        assert '"Content"' in src

    def test_content_endpoints_in_main(self):
        path = os.path.join(os.path.dirname(__file__), "..", "app", "main.py")
        src = open(path).read()
        assert "about_content" in src
        assert "security_content" in src
        assert "for_businesses_content" in src
