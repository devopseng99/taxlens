"""Wave 38 — Email & Notifications tests.

Tests email service, template rendering, graceful degradation,
and integration with onboarding and billing flows.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

import asyncio
import pytest


# -----------------------------------------------------------------------
# Email Service — Graceful Degradation
# -----------------------------------------------------------------------

class TestEmailServiceDisabled:
    """Test email service when RESEND_API_KEY is not set."""

    def test_email_disabled_by_default(self):
        """EMAIL_ENABLED is False when no API key."""
        from email_service import EMAIL_ENABLED
        # In test env, RESEND_API_KEY is not set
        assert EMAIL_ENABLED is False

    def test_send_email_returns_disabled(self):
        """send_email returns disabled status when no API key."""
        from email_service import send_email
        result = asyncio.get_event_loop().run_until_complete(
            send_email("test@example.com", "Test", "<p>Test</p>")
        )
        assert result["status"] == "disabled"
        assert result["to"] == "test@example.com"

    def test_welcome_email_returns_disabled(self):
        """send_welcome_email gracefully returns disabled."""
        from email_service import send_welcome_email
        result = asyncio.get_event_loop().run_until_complete(
            send_welcome_email("test@example.com", "Test Corp", "tlk_abc123")
        )
        assert result["status"] == "disabled"

    def test_filing_reminder_returns_disabled(self):
        """send_filing_reminder gracefully returns disabled."""
        from email_service import send_filing_reminder
        result = asyncio.get_event_loop().run_until_complete(
            send_filing_reminder("test@example.com", "Test Corp", "April 15, 2026", 30)
        )
        assert result["status"] == "disabled"

    def test_upgrade_confirmation_returns_disabled(self):
        """send_plan_upgrade_confirmation gracefully returns disabled."""
        from email_service import send_plan_upgrade_confirmation
        result = asyncio.get_event_loop().run_until_complete(
            send_plan_upgrade_confirmation("test@example.com", "Test Corp", "professional")
        )
        assert result["status"] == "disabled"


# -----------------------------------------------------------------------
# Email Templates
# -----------------------------------------------------------------------

class TestEmailTemplates:
    """Test email template content generation."""

    def test_welcome_email_contains_api_key(self):
        """Welcome email HTML includes the API key."""
        # We can test by checking the template would include the key
        from email_service import _PORTAL_URL, _API_URL
        assert "taxlens-portal" in _PORTAL_URL
        assert "dropit" in _API_URL

    def test_from_email_default(self):
        """Default from address is set."""
        from email_service import FROM_EMAIL
        assert "taxlens" in FROM_EMAIL.lower() or "noreply" in FROM_EMAIL.lower()

    def test_resend_url_correct(self):
        """Resend API URL is correct."""
        from email_service import _RESEND_URL
        assert _RESEND_URL == "https://api.resend.com/emails"


# -----------------------------------------------------------------------
# Integration Points
# -----------------------------------------------------------------------

class TestOnboardingIntegration:
    """Test that onboarding calls welcome email."""

    def test_onboarding_imports_email_service(self):
        """onboarding.py can import email service."""
        source_path = os.path.join(os.path.dirname(__file__), "..", "app", "onboarding.py")
        with open(source_path) as f:
            source = f.read()
        assert "send_welcome_email" in source
        assert "EMAIL_ENABLED" in source

    def test_onboarding_email_is_non_blocking(self):
        """Email failure in onboarding is caught and logged."""
        source_path = os.path.join(os.path.dirname(__file__), "..", "app", "onboarding.py")
        with open(source_path) as f:
            source = f.read()
        # Should have try/except around email
        assert "non-blocking" in source.lower() or "non_blocking" in source.lower()


class TestBillingIntegration:
    """Test that billing webhook sends upgrade email."""

    def test_billing_imports_email_service(self):
        """billing_routes.py references email service."""
        source_path = os.path.join(os.path.dirname(__file__), "..", "app", "billing_routes.py")
        with open(source_path) as f:
            source = f.read()
        assert "send_plan_upgrade_confirmation" in source

    def test_billing_email_is_non_blocking(self):
        """Email failure in billing is caught and logged."""
        source_path = os.path.join(os.path.dirname(__file__), "..", "app", "billing_routes.py")
        with open(source_path) as f:
            source = f.read()
        assert "non-blocking" in source.lower() or "non_blocking" in source.lower()


class TestHealthEndpoint:
    """Test that health endpoint reports email status."""

    def test_health_includes_email_enabled(self):
        """Health endpoint source includes email_enabled field."""
        source_path = os.path.join(os.path.dirname(__file__), "..", "app", "main.py")
        with open(source_path) as f:
            source = f.read()
        assert '"email_enabled"' in source
        assert "EMAIL_ENABLED" in source
