"""Wave 77 tests — PII encryption: SSN masking, encryption, redaction."""

import sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

import pytest
from pii import (
    mask_ssn, is_ssn, encrypt_ssn, decrypt_ssn, pii_enabled,
    redact_person_dict, redact_input_block,
)


# =========================================================================
# SSN Masking
# =========================================================================
class TestMaskSSN:
    def test_mask_dashed(self):
        assert mask_ssn("123-45-6789") == "***-**-6789"

    def test_mask_undashed(self):
        assert mask_ssn("123456789") == "*****6789"

    def test_mask_placeholder(self):
        assert mask_ssn("XXX-XX-XXXX") == "XXX-XX-XXXX"

    def test_mask_empty(self):
        assert mask_ssn("") == ""

    def test_mask_none(self):
        assert mask_ssn(None) is None

    def test_mask_preserves_last_four(self):
        masked = mask_ssn("999-88-7654")
        assert masked.endswith("7654")
        assert "999" not in masked
        assert "88" not in masked


class TestIsSSN:
    def test_valid_dashed(self):
        assert is_ssn("123-45-6789") is True

    def test_valid_undashed(self):
        assert is_ssn("123456789") is True

    def test_placeholder_not_ssn(self):
        assert is_ssn("XXX-XX-XXXX") is False

    def test_empty_not_ssn(self):
        assert is_ssn("") is False

    def test_short_not_ssn(self):
        assert is_ssn("12345") is False

    def test_letters_not_ssn(self):
        assert is_ssn("abc-de-fghi") is False


# =========================================================================
# Encrypt / Decrypt (without PII_FERNET_KEY — graceful degradation)
# =========================================================================
class TestEncryptWithoutKey:
    def test_encrypt_without_key_masks(self):
        """Without PII_FERNET_KEY, encrypt_ssn should mask instead."""
        # pii_enabled() should be False (no env var set in tests)
        result = encrypt_ssn("123-45-6789")
        assert result == "***-**-6789"

    def test_encrypt_placeholder_passthrough(self):
        assert encrypt_ssn("XXX-XX-XXXX") == "XXX-XX-XXXX"

    def test_encrypt_empty_passthrough(self):
        assert encrypt_ssn("") == ""

    def test_decrypt_masked_passthrough(self):
        """Can't decrypt a masked value — returns as-is."""
        assert decrypt_ssn("***-**-6789") == "***-**-6789"

    def test_decrypt_placeholder_passthrough(self):
        assert decrypt_ssn("XXX-XX-XXXX") == "XXX-XX-XXXX"


# =========================================================================
# Encrypt / Decrypt (with key)
# =========================================================================
class TestEncryptWithKey:
    @pytest.fixture(autouse=True)
    def set_key(self, monkeypatch):
        from cryptography.fernet import Fernet
        key = Fernet.generate_key().decode()
        monkeypatch.setattr("pii.PII_FERNET_KEY", key)

    def test_roundtrip(self):
        ssn = "123-45-6789"
        encrypted = encrypt_ssn(ssn)
        assert encrypted != ssn
        assert "6789" not in encrypted  # Not just masked
        decrypted = decrypt_ssn(encrypted)
        assert decrypted == ssn

    def test_encrypt_different_each_time(self):
        """Fernet produces different ciphertext each call (timestamp + IV)."""
        e1 = encrypt_ssn("123-45-6789")
        e2 = encrypt_ssn("123-45-6789")
        assert e1 != e2  # Different ciphertext

    def test_decrypt_wrong_value(self):
        """Non-encrypted string returns as-is (not an error)."""
        result = decrypt_ssn("not-encrypted-at-all")
        assert result == "not-encrypted-at-all"

    def test_placeholder_not_encrypted(self):
        """Placeholder SSN is not encrypted."""
        assert encrypt_ssn("XXX-XX-XXXX") == "XXX-XX-XXXX"


# =========================================================================
# Redaction Helpers
# =========================================================================
class TestRedactPersonDict:
    def test_redacts_ssn(self):
        d = {"first_name": "John", "last_name": "Doe", "ssn": "123-45-6789"}
        result = redact_person_dict(d)
        assert result["ssn"] == "***-**-6789"
        assert result["first_name"] == "John"

    def test_does_not_mutate_input(self):
        d = {"ssn": "123-45-6789"}
        _ = redact_person_dict(d)
        assert d["ssn"] == "123-45-6789"  # Original unchanged

    def test_placeholder_unchanged(self):
        d = {"ssn": "XXX-XX-XXXX"}
        result = redact_person_dict(d)
        assert result["ssn"] == "XXX-XX-XXXX"

    def test_no_ssn_key(self):
        d = {"first_name": "Test"}
        result = redact_person_dict(d)
        assert result == d

    def test_empty_dict(self):
        assert redact_person_dict({}) == {}

    def test_none_input(self):
        assert redact_person_dict(None) is None


class TestRedactInputBlock:
    def test_redacts_filer_and_spouse(self):
        block = {
            "filing_status": "mfj",
            "filer": {"first_name": "John", "ssn": "111-22-3333"},
            "spouse": {"first_name": "Jane", "ssn": "444-55-6666"},
        }
        result = redact_input_block(block)
        assert result["filer"]["ssn"] == "***-**-3333"
        assert result["spouse"]["ssn"] == "***-**-6666"
        assert result["filing_status"] == "mfj"

    def test_no_spouse(self):
        block = {
            "filer": {"ssn": "111-22-3333"},
            "spouse": None,
        }
        result = redact_input_block(block)
        assert result["filer"]["ssn"] == "***-**-3333"
        assert result["spouse"] is None

    def test_redacts_dependents(self):
        block = {
            "filer": {"ssn": "XXX-XX-XXXX"},
            "dependents": [
                {"first_name": "Kid1", "ssn": "777-88-9999"},
                {"first_name": "Kid2", "ssn": "XXX-XX-XXXX"},
            ],
        }
        result = redact_input_block(block)
        assert result["dependents"][0]["ssn"] == "***-**-9999"
        assert result["dependents"][1]["ssn"] == "XXX-XX-XXXX"

    def test_does_not_mutate_input(self):
        block = {"filer": {"ssn": "111-22-3333"}}
        _ = redact_input_block(block)
        assert block["filer"]["ssn"] == "111-22-3333"

    def test_empty_block(self):
        assert redact_input_block({}) == {}

    def test_none_block(self):
        assert redact_input_block(None) is None


# =========================================================================
# Integration — Tax Engine Roundtrip
# =========================================================================
class TestIntegration:
    def test_compute_tax_with_ssn_then_redact(self):
        """End-to-end: compute tax with real SSN, then redact in output."""
        from tax_engine import (
            compute_tax, PersonInfo, W2Income, Deductions,
            AdditionalIncome, Payments,
        )
        result = compute_tax(
            filing_status="single",
            filer=PersonInfo(
                first_name="Test", last_name="PII",
                ssn="123-45-6789",
            ),
            w2s=[W2Income(wages=80_000, federal_withheld=10_000,
                          ss_wages=80_000, medicare_wages=80_000)],
            additional=AdditionalIncome(),
            deductions=Deductions(),
            payments=Payments(),
        )
        # to_summary() should NOT expose SSN
        summary = result.to_summary()
        import json
        summary_str = json.dumps(summary)
        assert "123-45-6789" not in summary_str
        assert "6789" not in summary_str or "filer_name" in summary_str

    def test_input_block_redaction(self):
        """Simulate result.json input block redaction."""
        raw_input = {
            "filing_status": "single",
            "filer": {
                "first_name": "Test",
                "last_name": "User",
                "ssn": "999-88-7777",
                "address_street": "123 Main St",
            },
            "spouse": None,
        }
        redacted = redact_input_block(raw_input)
        assert redacted["filer"]["ssn"] == "***-**-7777"
        assert redacted["filer"]["first_name"] == "Test"
        assert redacted["filer"]["address_street"] == "123 Main St"
