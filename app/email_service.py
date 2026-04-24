"""Transactional email service via Resend API.

Uses httpx to call Resend's REST API directly (no SDK dependency).
Gracefully disabled when RESEND_API_KEY is not set.

Env vars:
  RESEND_API_KEY       — Resend API key (re_...)
  TAXLENS_FROM_EMAIL   — From address (default: noreply@taxlens.istayintek.com)
"""

import os
import logging
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

RESEND_API_KEY = os.getenv("RESEND_API_KEY", "")
FROM_EMAIL = os.getenv("TAXLENS_FROM_EMAIL", "TaxLens <noreply@taxlens.istayintek.com>")
EMAIL_ENABLED = bool(RESEND_API_KEY)

_RESEND_URL = "https://api.resend.com/emails"


async def send_email(
    to: str,
    subject: str,
    html: str,
    text: Optional[str] = None,
) -> dict:
    """Send a transactional email via Resend.

    Returns {"id": "...", "status": "sent"} on success.
    Returns {"status": "disabled"} if EMAIL_ENABLED is False.
    Raises on API error.
    """
    if not EMAIL_ENABLED:
        logger.debug("Email disabled (no RESEND_API_KEY) — skipping: %s → %s", subject, to)
        return {"status": "disabled", "to": to, "subject": subject}

    payload = {
        "from": FROM_EMAIL,
        "to": [to],
        "subject": subject,
        "html": html,
    }
    if text:
        payload["text"] = text

    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(
            _RESEND_URL,
            json=payload,
            headers={
                "Authorization": f"Bearer {RESEND_API_KEY}",
                "Content-Type": "application/json",
            },
        )

    if resp.status_code in (200, 201):
        data = resp.json()
        logger.info("Email sent: %s → %s (id=%s)", subject, to, data.get("id"))
        return {"status": "sent", "id": data.get("id"), "to": to}
    else:
        logger.error("Email failed: %s → %s (status=%d, body=%s)",
                     subject, to, resp.status_code, resp.text[:200])
        return {"status": "error", "code": resp.status_code, "detail": resp.text[:200]}


# ---------------------------------------------------------------------------
# Template functions
# ---------------------------------------------------------------------------

_PORTAL_URL = os.getenv("TAXLENS_PORTAL_URL", "https://taxlens-portal.istayintek.com")
_API_URL = os.getenv("TAXLENS_API_URL", "https://dropit.istayintek.com/api")


async def send_welcome_email(email: str, tenant_name: str, api_key: str) -> dict:
    """Send welcome email after signup with API key and portal link."""
    subject = f"Welcome to TaxLens — {tenant_name}"
    html = f"""
    <div style="font-family: -apple-system, sans-serif; max-width: 600px; margin: 0 auto;">
      <h2 style="color: #1a237e;">Welcome to TaxLens!</h2>
      <p>Your account <strong>{tenant_name}</strong> is ready.</p>

      <h3>Your API Key</h3>
      <p style="background: #f5f5f5; padding: 12px; border-radius: 4px; font-family: monospace; word-break: break-all;">
        {api_key}
      </p>
      <p style="color: #666; font-size: 13px;">Save this key securely — it won't be shown again.</p>

      <h3>Get Started</h3>
      <ul>
        <li><a href="{_PORTAL_URL}">Log in to the Portal</a></li>
        <li><a href="{_API_URL}/docs">API Documentation</a></li>
      </ul>

      <h3>MCP Server (for Claude Desktop)</h3>
      <p>Add this to your <code>claude_desktop_config.json</code>:</p>
      <pre style="background: #f5f5f5; padding: 12px; border-radius: 4px; font-size: 12px; overflow-x: auto;">{{
  "mcpServers": {{
    "taxlens": {{
      "url": "{_API_URL}/mcp",
      "headers": {{"X-API-Key": "{api_key}"}}
    }}
  }}
}}</pre>

      <hr style="margin: 24px 0; border: none; border-top: 1px solid #e0e0e0;">
      <p style="color: #999; font-size: 12px;">TaxLens — Agentic Tax Intelligence Platform</p>
    </div>
    """
    text = (f"Welcome to TaxLens!\n\nYour account '{tenant_name}' is ready.\n\n"
            f"API Key: {api_key}\n\nPortal: {_PORTAL_URL}\nDocs: {_API_URL}/docs\n")
    return await send_email(email, subject, html, text)


async def send_filing_reminder(email: str, tenant_name: str, deadline: str, days_left: int) -> dict:
    """Send tax filing deadline reminder."""
    urgency = "urgent" if days_left <= 7 else "upcoming"
    subject = f"Tax Filing Reminder: {days_left} days until {deadline}"
    html = f"""
    <div style="font-family: -apple-system, sans-serif; max-width: 600px; margin: 0 auto;">
      <h2 style="color: {'#c62828' if urgency == 'urgent' else '#1a237e'};">
        {'⚠️ ' if urgency == 'urgent' else ''}Tax Filing Deadline: {deadline}
      </h2>
      <p>Hi {tenant_name},</p>
      <p>You have <strong>{days_left} days</strong> until the federal tax filing deadline.</p>
      <p><a href="{_PORTAL_URL}" style="background: #1a237e; color: white; padding: 12px 24px; text-decoration: none; border-radius: 4px; display: inline-block;">
        Review Your Return
      </a></p>
      <hr style="margin: 24px 0; border: none; border-top: 1px solid #e0e0e0;">
      <p style="color: #999; font-size: 12px;">TaxLens — Agentic Tax Intelligence Platform</p>
    </div>
    """
    return await send_email(email, subject, html)


async def send_plan_upgrade_confirmation(email: str, tenant_name: str, new_plan: str) -> dict:
    """Confirm plan upgrade."""
    subject = f"TaxLens Plan Upgraded to {new_plan.title()}"
    html = f"""
    <div style="font-family: -apple-system, sans-serif; max-width: 600px; margin: 0 auto;">
      <h2 style="color: #1a237e;">Plan Upgraded!</h2>
      <p>Hi {tenant_name},</p>
      <p>Your TaxLens plan has been upgraded to <strong>{new_plan.title()}</strong>.</p>
      <p>Your new features are now active. <a href="{_PORTAL_URL}">Log in to explore</a>.</p>
      <hr style="margin: 24px 0; border: none; border-top: 1px solid #e0e0e0;">
      <p style="color: #999; font-size: 12px;">TaxLens — Agentic Tax Intelligence Platform</p>
    </div>
    """
    return await send_email(email, subject, html)
