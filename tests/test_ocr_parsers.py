"""Unit tests for TaxLens OCR parsers — 1099-DIV, 1099-NEC, 1098, 1099-B.

Run: PYTHONPATH=app pytest tests/test_ocr_parsers.py -v
"""

import json
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'app'))

import pytest
from tax_engine import (
    DividendIncome, BusinessIncome, CapitalTransaction,
    parse_1099div_from_ocr, parse_1099nec_from_ocr,
    parse_1098_from_ocr, parse_1099b_from_structured,
    _parse_money,
)

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


def load_fixture(name: str) -> dict | list:
    with open(os.path.join(FIXTURES, name)) as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# _parse_money helper
# ---------------------------------------------------------------------------
class TestParseMoney:
    def test_dollar_sign(self):
        assert _parse_money("$2,450.00") == 2450.00

    def test_plain_number(self):
        assert _parse_money("72500.00") == 72500.00

    def test_empty(self):
        assert _parse_money("") == 0.0

    def test_none_string(self):
        assert _parse_money("None") == 0.0

    def test_spaces(self):
        assert _parse_money(" $ 1,234.56 ") == 1234.56

    def test_zero(self):
        assert _parse_money("$0.00") == 0.0


# ---------------------------------------------------------------------------
# 1099-DIV parser
# ---------------------------------------------------------------------------
class TestParse1099DIV:
    def test_flat_fields(self):
        data = load_fixture("1099div_sample.json")
        div = parse_1099div_from_ocr(data["fields"])
        assert isinstance(div, DividendIncome)
        assert div.payer_name == "Vanguard Brokerage Services"
        assert div.ordinary_dividends == 3245.67
        assert div.qualified_dividends == 2100.00
        assert div.capital_gain_dist == 1500.00
        assert div.federal_withheld == 487.50
        assert div.section_199a == 850.00

    def test_array_format(self):
        data = load_fixture("1099div_array_format.json")
        div = parse_1099div_from_ocr(data["fields"])
        # Should aggregate both entries
        assert div.ordinary_dividends == 3700.00  # 1200 + 2500
        assert div.qualified_dividends == 2600.00  # 800 + 1800
        assert div.capital_gain_dist == 500.00     # 500 + 0
        assert div.federal_withheld == 555.00      # 180 + 375
        assert div.section_199a == 300.00          # 300 + 0
        # First payer name
        assert div.payer_name == "Fidelity Investments"

    def test_empty_fields(self):
        div = parse_1099div_from_ocr({})
        assert div.ordinary_dividends == 0.0
        assert div.qualified_dividends == 0.0
        assert div.payer_name == ""

    def test_missing_optional_boxes(self):
        fields = {
            "Box1a": {"type": "number", "value": "$500.00", "confidence": 0.95},
        }
        div = parse_1099div_from_ocr(fields)
        assert div.ordinary_dividends == 500.00
        assert div.qualified_dividends == 0.0
        assert div.capital_gain_dist == 0.0

    def test_payer_as_string(self):
        fields = {
            "Payer": {"type": "string", "value": "Simple Bank"},
            "Box1a": {"type": "number", "value": "100.00", "confidence": 0.9},
        }
        div = parse_1099div_from_ocr(fields)
        assert div.payer_name == "Simple Bank"


# ---------------------------------------------------------------------------
# 1099-NEC parser
# ---------------------------------------------------------------------------
class TestParse1099NEC:
    def test_basic(self):
        data = load_fixture("1099nec_sample.json")
        biz, withheld = parse_1099nec_from_ocr(data["fields"])
        assert isinstance(biz, BusinessIncome)
        assert biz.business_name == "TechConsult LLC"
        assert biz.gross_receipts == 45000.00
        assert withheld == 6750.00

    def test_no_payer_name(self):
        fields = {
            "Box1": {"type": "number", "value": "$10,000.00", "confidence": 0.95},
        }
        biz, withheld = parse_1099nec_from_ocr(fields)
        assert biz.business_name == "1099-NEC Income"
        assert biz.gross_receipts == 10000.00
        assert withheld == 0.0

    def test_empty(self):
        biz, withheld = parse_1099nec_from_ocr({})
        assert biz.gross_receipts == 0.0
        assert withheld == 0.0

    def test_payer_as_string(self):
        fields = {
            "Payer": {"type": "string", "value": "Uber Technologies"},
            "Box1": {"type": "number", "value": "5500", "confidence": 0.9},
        }
        biz, _ = parse_1099nec_from_ocr(fields)
        assert biz.business_name == "Uber Technologies"


# ---------------------------------------------------------------------------
# 1098 parser
# ---------------------------------------------------------------------------
class TestParse1098:
    def test_basic(self):
        data = load_fixture("1098_sample.json")
        interest = parse_1098_from_ocr(data["fields"])
        assert interest == 18750.00

    def test_empty(self):
        assert parse_1098_from_ocr({}) == 0.0

    def test_mortgage_interest_field(self):
        fields = {
            "MortgageInterest": {"type": "number", "value": "$12,345.67", "confidence": 0.95},
        }
        assert parse_1098_from_ocr(fields) == 12345.67

    def test_transactions_array(self):
        fields = {
            "Transactions": {
                "type": "array",
                "value": [
                    {
                        "type": "object",
                        "value": {
                            "Box1": {"type": "number", "value": "$9,500.00", "confidence": 0.95}
                        }
                    }
                ]
            }
        }
        assert parse_1098_from_ocr(fields) == 9500.00


# ---------------------------------------------------------------------------
# 1099-B structured import
# ---------------------------------------------------------------------------
class TestParse1099B:
    def test_fixture(self):
        data = load_fixture("1099b_sample.json")
        txns = parse_1099b_from_structured(data)
        assert len(txns) == 4

        # AAPL — long-term gain
        assert txns[0].description == "AAPL - Apple Inc"
        assert txns[0].proceeds == 15000.00
        assert txns[0].cost_basis == 10000.00
        assert txns[0].is_long_term is True
        assert txns[0].gain_loss == 5000.00

        # TSLA — short-term loss
        assert txns[1].is_long_term is False
        assert txns[1].gain_loss == -1500.00

        # MSFT — "long" string → True
        assert txns[2].is_long_term is True
        assert txns[2].gain_loss == 7000.00

        # BTC — "short" string → False
        assert txns[3].is_long_term is False
        assert txns[3].gain_loss == -2000.00

    def test_empty(self):
        assert parse_1099b_from_structured([]) == []

    def test_bool_string_variants(self):
        data = [
            {"proceeds": 100, "cost_basis": 50, "is_long_term": "true"},
            {"proceeds": 100, "cost_basis": 50, "is_long_term": "yes"},
            {"proceeds": 100, "cost_basis": 50, "is_long_term": "1"},
            {"proceeds": 100, "cost_basis": 50, "is_long_term": "l"},
            {"proceeds": 100, "cost_basis": 50, "is_long_term": "no"},
        ]
        txns = parse_1099b_from_structured(data)
        assert txns[0].is_long_term is True
        assert txns[1].is_long_term is True
        assert txns[2].is_long_term is True
        assert txns[3].is_long_term is True
        assert txns[4].is_long_term is False

    def test_defaults(self):
        txns = parse_1099b_from_structured([{"proceeds": 5000, "cost_basis": 3000}])
        assert len(txns) == 1
        assert txns[0].description == "Security Sale"
        assert txns[0].date_acquired == "Various"
        assert txns[0].is_long_term is False


# ---------------------------------------------------------------------------
# E2E: 1099-DIV → compute → verify Schedule B/D impact
# ---------------------------------------------------------------------------
class TestDivE2E:
    def test_dividends_flow_to_schedule_b(self):
        """1099-DIV ordinary dividends should appear in AGI."""
        from tax_engine import (
            PersonInfo, W2Income, Deductions, AdditionalIncome, Payments,
            compute_tax,
        )
        filer = PersonInfo(first_name="Div", last_name="Test", ssn="111-22-3333",
                           address_city="Chicago", address_state="IL", address_zip="60601")
        # Simulate what the route does: OCR-parsed 1099-DIV → additional income
        additional = AdditionalIncome(
            ordinary_dividends=3245.67,
            qualified_dividends=2100.00,
        )
        result = compute_tax(
            filing_status="single",
            filer=filer,
            w2s=[W2Income(wages=50000, federal_withheld=6000)],
            additional=additional,
            deductions=Deductions(),
            payments=Payments(),
        )
        # Dividends should be in total income
        assert result.line_3b_ordinary_dividends == 3245.67
        assert result.line_3a_qualified_dividends == 2100.00
        # AGI includes wages + dividends
        assert result.line_11_agi > 53000

    def test_1099b_capital_gains_in_schedule_d(self):
        """Structured 1099-B transactions → Schedule D gains/losses."""
        from tax_engine import (
            PersonInfo, W2Income, Deductions, AdditionalIncome, Payments,
            compute_tax,
        )
        txns = parse_1099b_from_structured([
            {"description": "AAPL", "proceeds": 15000, "cost_basis": 10000, "is_long_term": True},
            {"description": "TSLA", "proceeds": 8000, "cost_basis": 9500, "is_long_term": False},
        ])
        filer = PersonInfo(first_name="Cap", last_name="Test", ssn="222-33-4444",
                           address_city="Chicago", address_state="IL", address_zip="60601")
        additional = AdditionalIncome(capital_transactions=txns)
        result = compute_tax(
            filing_status="single",
            filer=filer,
            w2s=[W2Income(wages=60000, federal_withheld=8000)],
            additional=additional,
            deductions=Deductions(),
            payments=Payments(),
        )
        # Net gain: 5000 LTCG - 1500 STCL = 3500 net
        assert result.sched_d_net_gain == 3500.00

    def test_additional_withholding(self):
        """1099-DIV + 1099-NEC withholding should reduce tax owed."""
        from tax_engine import (
            PersonInfo, W2Income, Deductions, AdditionalIncome, Payments,
            compute_tax,
        )
        filer = PersonInfo(first_name="With", last_name="Test", ssn="333-44-5555",
                           address_city="Chicago", address_state="IL", address_zip="60601")
        result = compute_tax(
            filing_status="single",
            filer=filer,
            w2s=[W2Income(wages=50000, federal_withheld=6000)],
            additional=AdditionalIncome(),
            deductions=Deductions(),
            payments=Payments(),
            additional_withholding=2000.00,
        )
        # Total withholding should include additional
        assert result.line_25_federal_withheld == 8000.00  # 6000 W-2 + 2000 additional
