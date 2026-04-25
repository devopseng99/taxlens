"""PII protection — SSN encryption, decryption, and masking.

Provides field-level encryption for Social Security Numbers using Fernet
(same pattern as Plaid token encryption). SSNs are:
  - Encrypted at rest (result.json, database JSONB)
  - Masked in API responses (show last 4 only)
  - Plaintext only during computation and PDF generation

Environment variable: PII_FERNET_KEY (base64-encoded 32-byte key)
Generate with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
"""

from __future__ import annotations

import os
import re
import logging

from cryptography.fernet import Fernet, InvalidToken

logger = logging.getLogger(__name__)

PII_FERNET_KEY = os.getenv("PII_FERNET_KEY", "")

# SSN regex: 9 digits with optional dashes
_SSN_PATTERN = re.compile(r"^\d{3}-?\d{2}-?\d{4}$")


def pii_enabled() -> bool:
    """Check if PII encryption is configured."""
    return bool(PII_FERNET_KEY)


def _get_fernet() -> Fernet:
    """Get Fernet instance for encrypting/decrypting SSNs."""
    if not PII_FERNET_KEY:
        raise RuntimeError("PII encryption key not configured (PII_FERNET_KEY)")
    return Fernet(PII_FERNET_KEY.encode())


def is_ssn(value: str) -> bool:
    """Check if a string looks like an SSN (not the default placeholder)."""
    if not value or value == "XXX-XX-XXXX":
        return False
    return bool(_SSN_PATTERN.match(value))


def mask_ssn(ssn: str) -> str:
    """Mask an SSN to show only last 4 digits.

    "123-45-6789" → "***-**-6789"
    "123456789"   → "*****6789"
    """
    if not ssn or ssn == "XXX-XX-XXXX":
        return ssn
    digits = ssn.replace("-", "")
    if len(digits) != 9:
        return ssn  # Not a valid SSN, return as-is
    if "-" in ssn:
        return f"***-**-{digits[-4:]}"
    return f"*****{digits[-4:]}"


def encrypt_ssn(ssn: str) -> str:
    """Encrypt an SSN using Fernet. Returns encrypted string.

    If PII_FERNET_KEY is not set, returns the masked SSN instead
    (graceful degradation — still protects the plaintext).
    """
    if not ssn or ssn == "XXX-XX-XXXX":
        return ssn
    if not pii_enabled():
        logger.debug("PII encryption not configured; masking SSN instead")
        return mask_ssn(ssn)
    try:
        f = _get_fernet()
        return f.encrypt(ssn.encode()).decode()
    except Exception:
        logger.warning("Failed to encrypt SSN; falling back to mask")
        return mask_ssn(ssn)


def decrypt_ssn(encrypted: str) -> str:
    """Decrypt an SSN encrypted with encrypt_ssn().

    Returns the original SSN, or the input unchanged if not encrypted
    (handles masked values and placeholders gracefully).
    """
    if not encrypted or encrypted == "XXX-XX-XXXX":
        return encrypted
    # Already masked (not encrypted) — can't decrypt
    if encrypted.startswith("***") or encrypted.startswith("*****"):
        return encrypted
    if not pii_enabled():
        return encrypted
    try:
        f = _get_fernet()
        return f.decrypt(encrypted.encode()).decode()
    except InvalidToken:
        # Not an encrypted value — return as-is
        return encrypted
    except Exception:
        logger.warning("Failed to decrypt SSN")
        return encrypted


def redact_person_dict(d: dict) -> dict:
    """Redact SSN in a person dict (from model_dump()).

    Replaces 'ssn' field with masked version.
    Returns a new dict (does not mutate input).
    """
    if not d:
        return d
    result = dict(d)
    if "ssn" in result and is_ssn(result["ssn"]):
        result["ssn"] = mask_ssn(result["ssn"])
    return result


def redact_input_block(input_block: dict) -> dict:
    """Redact all SSNs in the 'input' section of result.json.

    Handles filer, spouse, and dependents.
    Returns a new dict (does not mutate input).
    """
    if not input_block:
        return input_block
    result = dict(input_block)
    if "filer" in result and result["filer"]:
        result["filer"] = redact_person_dict(result["filer"])
    if "spouse" in result and result["spouse"]:
        result["spouse"] = redact_person_dict(result["spouse"])
    if "dependents" in result and result["dependents"]:
        result["dependents"] = [redact_person_dict(d) for d in result["dependents"]]
    return result
