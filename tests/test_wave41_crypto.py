"""Wave 41 tests — Crypto & Digital Assets (Form 8949, wash sales, cost basis methods)."""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

import pytest
from tax_engine import (
    PersonInfo, W2Income, Deductions, AdditionalIncome, Payments,
    CryptoTransaction, CapitalTransaction,
    compute_tax,
)
from tax_config import SINGLE, MFJ


def _base_result(**kw):
    defaults = dict(
        filing_status=SINGLE,
        filer=PersonInfo(first_name="Test", last_name="User"),
        w2s=[W2Income(wages=80000, federal_withheld=12000,
                      ss_wages=80000, medicare_wages=80000)],
        additional=AdditionalIncome(),
        deductions=Deductions(),
        payments=Payments(),
    )
    defaults.update(kw)
    return compute_tax(**defaults)


# =========================================================================
# CryptoTransaction Dataclass
# =========================================================================
class TestCryptoTransaction:
    def test_gain_loss_property(self):
        ct = CryptoTransaction(proceeds=15000, cost_basis=10000)
        assert ct.gain_loss == 5000.0

    def test_loss(self):
        ct = CryptoTransaction(proceeds=5000, cost_basis=10000)
        assert ct.gain_loss == -5000.0

    def test_adjusted_gain_no_wash_sale(self):
        ct = CryptoTransaction(proceeds=5000, cost_basis=10000)
        assert ct.adjusted_gain_loss == -5000.0

    def test_adjusted_gain_with_wash_sale(self):
        """Wash sale disallows part of loss."""
        ct = CryptoTransaction(
            proceeds=5000, cost_basis=10000,
            wash_sale_loss_disallowed=3000,
        )
        # Raw loss: -5000, disallowed: 3000, adjusted: -2000
        assert ct.adjusted_gain_loss == -2000.0

    def test_wash_sale_full_disallow(self):
        """Full wash sale disallowance."""
        ct = CryptoTransaction(
            proceeds=8000, cost_basis=10000,
            wash_sale_loss_disallowed=2000,
        )
        # Raw loss: -2000, disallowed: 2000, adjusted: 0
        assert ct.adjusted_gain_loss == 0.0

    def test_to_capital_transaction(self):
        """Convert crypto to standard CapitalTransaction."""
        ct = CryptoTransaction(
            asset_name="BTC", exchange="Coinbase",
            proceeds=50000, cost_basis=30000, is_long_term=True,
        )
        cap = ct.to_capital_transaction()
        assert isinstance(cap, CapitalTransaction)
        assert cap.description == "BTC (Coinbase)"
        assert cap.proceeds == 50000
        assert cap.cost_basis == 30000
        assert cap.is_long_term is True

    def test_to_capital_transaction_wash_sale_adjusts_basis(self):
        """Wash sale loss disallowed added to basis."""
        ct = CryptoTransaction(
            asset_name="ETH", proceeds=8000, cost_basis=10000,
            wash_sale_loss_disallowed=2000,
        )
        cap = ct.to_capital_transaction()
        assert cap.cost_basis == 12000  # 10000 + 2000 wash sale

    def test_no_exchange_in_description(self):
        ct = CryptoTransaction(asset_name="SOL")
        cap = ct.to_capital_transaction()
        assert cap.description == "SOL"


# =========================================================================
# Crypto Integration with Tax Engine
# =========================================================================
class TestCryptoTaxEngine:
    def test_crypto_short_term_gain(self):
        r = _base_result(crypto_transactions=[
            CryptoTransaction(asset_name="BTC", proceeds=50000, cost_basis=30000, is_long_term=False),
        ])
        assert r.crypto_short_term_gain == 20000.0
        assert r.crypto_long_term_gain == 0.0
        assert r.crypto_transactions_count == 1

    def test_crypto_long_term_gain(self):
        r = _base_result(crypto_transactions=[
            CryptoTransaction(asset_name="BTC", proceeds=100000, cost_basis=20000, is_long_term=True),
        ])
        assert r.crypto_long_term_gain == 80000.0
        assert r.crypto_short_term_gain == 0.0

    def test_crypto_flows_to_schedule_d(self):
        """Crypto gains flow to Schedule D via CapitalTransaction."""
        r = _base_result(crypto_transactions=[
            CryptoTransaction(proceeds=15000, cost_basis=10000, is_long_term=True),
        ])
        assert r.sched_d_long_term_gain == 5000.0
        assert r.line_7_capital_gain_loss == 5000.0

    def test_crypto_multiple_transactions(self):
        r = _base_result(crypto_transactions=[
            CryptoTransaction(asset_name="BTC", proceeds=50000, cost_basis=30000, is_long_term=True),
            CryptoTransaction(asset_name="ETH", proceeds=5000, cost_basis=8000, is_long_term=False),
            CryptoTransaction(asset_name="SOL", proceeds=2000, cost_basis=1000, is_long_term=False),
        ])
        assert r.crypto_transactions_count == 3
        assert r.crypto_long_term_gain == 20000.0   # BTC: 50K-30K
        assert r.crypto_short_term_gain == -2000.0   # ETH: -3K + SOL: +1K
        assert r.crypto_total_proceeds == 57000.0
        assert r.crypto_total_basis == 39000.0

    def test_crypto_loss(self):
        """Crypto losses reduce capital gains."""
        r = _base_result(crypto_transactions=[
            CryptoTransaction(proceeds=2000, cost_basis=10000, is_long_term=False),
        ])
        assert r.crypto_short_term_gain == -8000.0
        assert r.sched_d_net_gain == -8000.0

    def test_crypto_wash_sale_reduces_loss(self):
        """Wash sale disallows part of crypto loss."""
        r = _base_result(crypto_transactions=[
            CryptoTransaction(
                asset_name="BTC", proceeds=5000, cost_basis=10000,
                is_long_term=False, wash_sale_loss_disallowed=3000,
            ),
        ])
        assert r.crypto_wash_sale_disallowed == 3000.0
        # Adjusted loss: -5000 + 3000 = -2000
        assert r.crypto_short_term_gain == -2000.0

    def test_crypto_with_regular_capital_gains(self):
        """Crypto and regular stock transactions aggregate."""
        r = _base_result(
            additional=AdditionalIncome(capital_transactions=[
                CapitalTransaction(proceeds=20000, cost_basis=15000, is_long_term=True),
            ]),
            crypto_transactions=[
                CryptoTransaction(proceeds=10000, cost_basis=5000, is_long_term=True),
            ],
        )
        assert r.sched_d_long_term_gain == 10000.0  # 5K stock + 5K crypto
        assert r.crypto_long_term_gain == 5000.0

    def test_crypto_summary_output(self):
        r = _base_result(crypto_transactions=[
            CryptoTransaction(asset_name="BTC", proceeds=50000, cost_basis=30000, is_long_term=True),
        ])
        s = r.to_summary()
        assert s["crypto"] is not None
        assert s["crypto"]["long_term_gain"] == 20000.0
        assert s["crypto"]["transactions"] == 1

    def test_no_crypto_summary_null(self):
        r = _base_result()
        s = r.to_summary()
        assert s["crypto"] is None

    def test_form_8949_in_forms(self):
        r = _base_result(crypto_transactions=[
            CryptoTransaction(proceeds=10000, cost_basis=5000),
        ])
        assert "Form 8949" in r.forms_generated

    def test_form_8949_not_in_forms_when_none(self):
        r = _base_result()
        assert "Form 8949" not in r.forms_generated

    def test_crypto_increases_total_income(self):
        r_base = _base_result()
        r_crypto = _base_result(crypto_transactions=[
            CryptoTransaction(proceeds=50000, cost_basis=20000, is_long_term=True),
        ])
        assert r_crypto.line_9_total_income > r_base.line_9_total_income

    def test_crypto_basis_methods_stored(self):
        ct = CryptoTransaction(basis_method="hifo")
        assert ct.basis_method == "hifo"

    def test_crypto_backward_compat(self):
        """No crypto = no impact."""
        r = _base_result()
        assert r.crypto_transactions_count == 0
        assert r.crypto_total_proceeds == 0.0
