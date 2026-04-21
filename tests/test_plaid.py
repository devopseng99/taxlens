"""Unit tests for Plaid integration — parsers, routes helper, and tax data conversion.

Tests use mock Plaid responses (not live API calls).
Run: PYTHONPATH=app pytest tests/test_plaid.py -v
"""

import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'app'))

import pytest
from plaid_parsers import (
    plaid_investments_to_capital_transactions,
    plaid_dividends_to_dividend_income,
    plaid_to_tax_data,
)


# Load fixture
FIXTURES_DIR = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> dict:
    return json.loads((FIXTURES_DIR / name).read_text())


@pytest.fixture
def sandbox_data():
    return load_fixture("plaid_investments_sandbox.json")


# ---------------------------------------------------------------------------
# Plaid Parsers — Capital Transactions
# ---------------------------------------------------------------------------
class TestPlaidCapitalTransactions:
    def test_sells_only(self, sandbox_data):
        """Only sell transactions should become CapitalTransactions."""
        txns = plaid_investments_to_capital_transactions(
            sandbox_data["investment_transactions"],
            sandbox_data["securities"],
        )
        # Fixture has 2 sells (AAPL, TSLA) — buy + dividend + cap gain are excluded
        assert len(txns) == 2

    def test_aapl_proceeds(self, sandbox_data):
        txns = plaid_investments_to_capital_transactions(
            sandbox_data["investment_transactions"],
            sandbox_data["securities"],
        )
        aapl = [t for t in txns if "Apple" in t.description][0]
        assert aapl.proceeds == 8750.00
        assert aapl.cost_basis == 7500.00
        assert aapl.date_sold == "2025-03-15"

    def test_tsla_loss(self, sandbox_data):
        txns = plaid_investments_to_capital_transactions(
            sandbox_data["investment_transactions"],
            sandbox_data["securities"],
        )
        tsla = [t for t in txns if "Tesla" in t.description][0]
        assert tsla.proceeds == 2800.00
        assert tsla.cost_basis == 3200.00
        # Loss: proceeds < cost_basis

    def test_security_name_lookup(self, sandbox_data):
        txns = plaid_investments_to_capital_transactions(
            sandbox_data["investment_transactions"],
            sandbox_data["securities"],
        )
        names = [t.description for t in txns]
        assert any("Apple" in n for n in names)
        assert any("Tesla" in n for n in names)

    def test_no_securities_fallback(self, sandbox_data):
        """Without securities list, description should fallback."""
        txns = plaid_investments_to_capital_transactions(
            sandbox_data["investment_transactions"],
            securities=None,
        )
        assert len(txns) == 2
        assert all(t.description == "Security Sale" for t in txns)

    def test_empty_transactions(self):
        txns = plaid_investments_to_capital_transactions([], [])
        assert txns == []

    def test_no_cost_basis(self):
        """Transaction without cost_basis should default to 0."""
        txns = plaid_investments_to_capital_transactions([
            {"type": "sell", "subtype": "sell", "amount": -5000, "quantity": -10,
             "price": 500, "date": "2025-06-01", "security_id": "x"},
        ])
        assert len(txns) == 1
        assert txns[0].cost_basis == 0.0
        assert txns[0].proceeds == 5000.0


# ---------------------------------------------------------------------------
# Plaid Parsers — Dividend Income
# ---------------------------------------------------------------------------
class TestPlaidDividendIncome:
    def test_aggregate_dividends(self, sandbox_data):
        div = plaid_dividends_to_dividend_income(
            sandbox_data["investment_transactions"],
            sandbox_data["securities"],
        )
        # Ordinary: $1,245.67 (dividend) + $890.50 (qualified dividend) = $2,136.17
        assert div.ordinary_dividends == pytest.approx(2136.17, abs=0.01)
        # Qualified: $890.50
        assert div.qualified_dividends == pytest.approx(890.50, abs=0.01)

    def test_capital_gain_distributions(self, sandbox_data):
        div = plaid_dividends_to_dividend_income(
            sandbox_data["investment_transactions"],
            sandbox_data["securities"],
        )
        assert div.capital_gain_dist == pytest.approx(450.00, abs=0.01)

    def test_payer_name(self, sandbox_data):
        div = plaid_dividends_to_dividend_income(
            sandbox_data["investment_transactions"],
            sandbox_data["securities"],
        )
        assert "Vanguard" in div.payer_name

    def test_empty_dividends(self):
        div = plaid_dividends_to_dividend_income([])
        assert div.ordinary_dividends == 0
        assert div.qualified_dividends == 0
        assert div.payer_name == "Plaid Import"

    def test_sells_not_counted_as_dividends(self, sandbox_data):
        """Sell transactions should not appear in dividend totals."""
        div = plaid_dividends_to_dividend_income(
            sandbox_data["investment_transactions"],
        )
        # Total dividends should be ~$2,136.17, not including $8,750 + $2,800 from sells
        assert div.ordinary_dividends < 3000


# ---------------------------------------------------------------------------
# Plaid combined parser
# ---------------------------------------------------------------------------
class TestPlaidToTaxData:
    def test_full_conversion(self, sandbox_data):
        result = plaid_to_tax_data(
            sandbox_data["investment_transactions"],
            sandbox_data["securities"],
        )
        assert len(result["capital_transactions"]) == 2
        assert result["dividend_income"].ordinary_dividends > 0
        assert result["summary"]["sell_transactions"] == 2
        assert result["summary"]["net_gain_loss"] == pytest.approx(
            (8750 - 7500) + (2800 - 3200), abs=0.01
        )  # AAPL gain + TSLA loss = 1250 + (-400) = 850

    def test_summary_totals(self, sandbox_data):
        result = plaid_to_tax_data(
            sandbox_data["investment_transactions"],
            sandbox_data["securities"],
        )
        s = result["summary"]
        assert s["total_proceeds"] == pytest.approx(8750 + 2800, abs=0.01)
        assert s["total_cost_basis"] == pytest.approx(7500 + 3200, abs=0.01)
        assert s["ordinary_dividends"] == pytest.approx(2136.17, abs=0.01)
        assert s["capital_gain_distributions"] == pytest.approx(450.0, abs=0.01)


# ---------------------------------------------------------------------------
# Plaid routes helper — load_plaid_tax_data
# ---------------------------------------------------------------------------
class TestLoadPlaidTaxData:
    def test_load_existing(self, tmp_path):
        """load_plaid_tax_data should read tax_data.json from the item dir."""
        # Create mock structure
        user_dir = tmp_path / "testuser" / "plaid" / "item_123"
        user_dir.mkdir(parents=True)
        tax_data = {
            "capital_transactions": [{"description": "AAPL", "proceeds": 5000, "cost_basis": 4000, "is_long_term": True}],
            "dividend_income": {"ordinary_dividends": 100, "qualified_dividends": 50, "capital_gain_dist": 0, "payer_name": "Test"},
        }
        (user_dir / "tax_data.json").write_text(json.dumps(tax_data))

        with patch("plaid_routes.STORAGE_ROOT", tmp_path):
            from plaid_routes import load_plaid_tax_data
            result = load_plaid_tax_data("testuser", "item_123")
            assert result is not None
            assert len(result["capital_transactions"]) == 1
            assert result["dividend_income"]["ordinary_dividends"] == 100

    def test_load_missing(self, tmp_path):
        """load_plaid_tax_data should return None for unsynced items."""
        with patch("plaid_routes.STORAGE_ROOT", tmp_path):
            from plaid_routes import load_plaid_tax_data
            result = load_plaid_tax_data("testuser", "item_nonexistent")
            assert result is None


# ---------------------------------------------------------------------------
# Plaid client — initialization guard
# ---------------------------------------------------------------------------
class TestPlaidClient:
    def test_missing_credentials_raises(self):
        """get_plaid_client should raise if credentials are not set."""
        with patch.dict(os.environ, {"PLAID_CLIENT_ID": "", "PLAID_SECRET": ""}, clear=False):
            # Re-import to pick up empty env vars
            import importlib
            import plaid_client
            importlib.reload(plaid_client)
            with pytest.raises(RuntimeError, match="Plaid credentials not configured"):
                plaid_client.get_plaid_client()


# ---------------------------------------------------------------------------
# Token encryption round-trip
# ---------------------------------------------------------------------------
class TestTokenEncryption:
    def test_fernet_round_trip(self):
        """Fernet encrypt/decrypt should round-trip an access token."""
        from cryptography.fernet import Fernet
        key = Fernet.generate_key()
        f = Fernet(key)
        token = "access-sandbox-abc123-test"
        encrypted = f.encrypt(token.encode())
        decrypted = f.decrypt(encrypted).decode()
        assert decrypted == token
