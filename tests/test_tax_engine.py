"""Unit tests for TaxLens tax computation engine.

Run: cd app && python -m pytest ../tests/test_tax_engine.py -v
Or:  PYTHONPATH=app pytest tests/test_tax_engine.py -v
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'app'))

import pytest
from tax_engine import (
    PersonInfo, W2Income, CapitalTransaction, BusinessIncome,
    Deductions, AdditionalIncome, Payments,
    compute_tax, compute_bracket_tax, compute_ltcg_tax,
    parse_w2_from_ocr, parse_1099int_from_ocr,
)
from tax_config import *


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def make_filer(**kw):
    defaults = dict(first_name="Test", last_name="User", ssn="123-45-6789",
                    address_city="Chicago", address_state="IL", address_zip="60601")
    defaults.update(kw)
    return PersonInfo(**defaults)


def simple_compute(filing_status="single", wages=0, interest=0, dividends=0,
                   qual_div=0, cap_txns=None, other_income=0, businesses=None,
                   deductions=None, payments=None, num_dependents=0, spouse=None,
                   w2_federal_withheld=0, w2_ss_wages=None, w2_medicare_wages=None,
                   w2_state_withheld=0):
    """Shortcut to compute_tax with minimal boilerplate."""
    w2 = W2Income(
        wages=wages, federal_withheld=w2_federal_withheld,
        ss_wages=w2_ss_wages if w2_ss_wages is not None else wages,
        medicare_wages=w2_medicare_wages if w2_medicare_wages is not None else wages,
        state_withheld=w2_state_withheld,
    )
    w2s = [w2] if wages > 0 else []
    add = AdditionalIncome(
        other_interest=interest,
        ordinary_dividends=dividends,
        qualified_dividends=qual_div,
        capital_transactions=cap_txns or [],
        other_income=other_income,
    )
    return compute_tax(
        filing_status=filing_status,
        filer=make_filer(),
        w2s=w2s,
        additional=add,
        deductions=deductions or Deductions(),
        payments=payments or Payments(),
        spouse=spouse,
        num_dependents=num_dependents,
        businesses=businesses or [],
    )


# ---------------------------------------------------------------------------
# Bracket computation
# ---------------------------------------------------------------------------
class TestBracketComputation:
    def test_zero_income(self):
        assert compute_bracket_tax(0, FEDERAL_BRACKETS[SINGLE]) == 0.0

    def test_10_percent_bracket(self):
        tax = compute_bracket_tax(10000, FEDERAL_BRACKETS[SINGLE])
        assert tax == pytest.approx(1000.0)  # 10% of 10000

    def test_12_percent_bracket(self):
        # $11,925 at 10% + remainder at 12%
        tax = compute_bracket_tax(20000, FEDERAL_BRACKETS[SINGLE])
        expected = 11925 * 0.10 + (20000 - 11925) * 0.12
        assert tax == pytest.approx(expected)

    def test_mfj_wider_brackets(self):
        # MFJ 10% bracket goes to $23,850 vs $11,925 single
        tax_single = compute_bracket_tax(20000, FEDERAL_BRACKETS[SINGLE])
        tax_mfj = compute_bracket_tax(20000, FEDERAL_BRACKETS[MFJ])
        assert tax_mfj < tax_single  # MFJ should pay less (all at 10%)
        assert tax_mfj == pytest.approx(2000.0)  # 10% of 20000


class TestLTCGTax:
    def test_zero_ltcg(self):
        assert compute_ltcg_tax(50000, 0, LTCG_BRACKETS[SINGLE]) == 0.0

    def test_ltcg_in_zero_bracket(self):
        # $40K ordinary + $5K LTCG → total $45K, all LTCG in 0% bracket (up to $48,350)
        tax = compute_ltcg_tax(45000, 5000, LTCG_BRACKETS[SINGLE])
        assert tax == pytest.approx(0.0)

    def test_ltcg_in_15_bracket(self):
        # $50K ordinary + $10K LTCG → $60K total, LTCG starts above $48,350
        tax = compute_ltcg_tax(60000, 10000, LTCG_BRACKETS[SINGLE])
        # All $10K is above ordinary ($50K), within 15% bracket
        assert tax == pytest.approx(10000 * 0.15)


# ---------------------------------------------------------------------------
# Standard deduction vs itemized
# ---------------------------------------------------------------------------
class TestDeductionChoice:
    def test_standard_wins(self):
        r = simple_compute(wages=50000, deductions=Deductions(charitable_cash=1000))
        assert r.deduction_type == "standard"
        assert r.line_13_deduction == STANDARD_DEDUCTION[SINGLE]

    def test_itemized_wins(self):
        d = Deductions(mortgage_interest=15000, property_tax=8000, charitable_cash=5000)
        r = simple_compute(wages=100000, deductions=d)
        assert r.deduction_type == "itemized"
        assert r.line_13_deduction > STANDARD_DEDUCTION[SINGLE]

    def test_salt_cap(self):
        d = Deductions(property_tax=8000, state_income_tax_paid=5000)
        r = simple_compute(wages=100000, deductions=d)
        # SALT capped at $10K even though raw is $13K
        assert r.sched_a_salt == SALT_CAP

    def test_salt_cap_mfs(self):
        d = Deductions(property_tax=4000, state_income_tax_paid=3000)
        r = simple_compute(filing_status="mfs", wages=100000, deductions=d)
        assert r.sched_a_salt == SALT_CAP_MFS

    def test_medical_agi_floor(self):
        d = Deductions(medical_expenses=10000)
        r = simple_compute(wages=100000, deductions=d)
        # Medical deduction = expenses - 7.5% of AGI
        expected = max(0, 10000 - 100000 * 0.075)
        assert r.sched_a_medical == pytest.approx(expected)


# ---------------------------------------------------------------------------
# Self-employment tax
# ---------------------------------------------------------------------------
class TestSelfEmploymentTax:
    def test_se_tax_basic(self):
        biz = BusinessIncome(gross_receipts=80000, business_name="Consulting")
        r = simple_compute(businesses=[biz])
        assert r.se_tax > 0
        assert r.sched_se_taxable == pytest.approx(80000 * SE_INCOME_FACTOR)
        # 50% deductible
        assert r.se_tax_deduction == pytest.approx(r.se_tax * 0.5)

    def test_se_ss_cap(self):
        # W-2 SS wages at $150K + SE income → should cap SS portion
        biz = BusinessIncome(gross_receipts=50000, business_name="Side gig")
        r = simple_compute(wages=150000, w2_ss_wages=150000, businesses=[biz])
        se_taxable = 50000 * SE_INCOME_FACTOR
        ss_room = max(0, SS_WAGE_BASE - 150000)
        expected_ss = min(se_taxable, ss_room) * SE_SS_RATE
        assert r.sched_se_ss_tax == pytest.approx(expected_ss)

    def test_qbi_deduction(self):
        biz = BusinessIncome(gross_receipts=60000, business_name="Freelance")
        r = simple_compute(businesses=[biz])
        assert r.qbi_deduction == pytest.approx(60000 * QBI_DEDUCTION_RATE)


# ---------------------------------------------------------------------------
# NIIT and Additional Medicare Tax
# ---------------------------------------------------------------------------
class TestSurtaxes:
    def test_niit_below_threshold(self):
        r = simple_compute(wages=150000, interest=5000)
        assert r.niit == 0.0  # AGI $155K < $200K threshold

    def test_niit_above_threshold(self):
        r = simple_compute(wages=200000, interest=20000, dividends=10000)
        assert r.niit > 0
        # NII = interest(20K) + dividends(10K) = 30K
        # AGI excess = 230K - 200K = 30K
        # NIIT = min(30K, 30K) * 3.8% = 1140
        assert r.niit == pytest.approx(30000 * NIIT_RATE)

    def test_niit_lesser_of_rule(self):
        # AGI excess smaller than NII → use AGI excess
        r = simple_compute(wages=195000, interest=20000)
        # AGI = 215K, excess = 15K, NII = 20K → use 15K
        assert r.niit == pytest.approx(15000 * NIIT_RATE)

    def test_niit_mfj_threshold(self):
        r = simple_compute(filing_status="mfj", wages=240000, interest=5000,
                          spouse=make_filer(first_name="Spouse"))
        # AGI = 245K < 250K MFJ threshold
        assert r.niit == 0.0

    def test_additional_medicare_below_threshold(self):
        r = simple_compute(wages=180000)
        assert r.additional_medicare_tax == 0.0

    def test_additional_medicare_above_threshold(self):
        r = simple_compute(wages=250000)
        # Excess = 250K - 200K = 50K, tax = 50K * 0.9% = 450
        assert r.additional_medicare_tax == pytest.approx(50000 * ADDITIONAL_MEDICARE_RATE)

    def test_additional_medicare_mfs_lower_threshold(self):
        r = simple_compute(filing_status="mfs", wages=150000)
        # MFS threshold = $125K, excess = $25K
        assert r.additional_medicare_tax == pytest.approx(25000 * ADDITIONAL_MEDICARE_RATE)

    def test_additional_medicare_with_se(self):
        # W-2 wages + SE income combined for Medicare threshold
        biz = BusinessIncome(gross_receipts=100000, business_name="Consulting")
        r = simple_compute(wages=150000, businesses=[biz])
        se_taxable = 100000 * SE_INCOME_FACTOR
        total_medicare = 150000 + se_taxable
        excess = max(0, total_medicare - 200000)
        assert r.additional_medicare_tax == pytest.approx(excess * ADDITIONAL_MEDICARE_RATE)


# ---------------------------------------------------------------------------
# Capital gains
# ---------------------------------------------------------------------------
class TestCapitalGains:
    def test_short_term_as_ordinary(self):
        txn = CapitalTransaction(description="Stock", proceeds=10000, cost_basis=8000, is_long_term=False)
        r = simple_compute(wages=50000, cap_txns=[txn])
        assert r.sched_d_short_term_gain == 2000
        assert r.line_7_capital_gain_loss == 2000

    def test_long_term_preferential(self):
        # $150K wages + $50K LTCG pushes LTCG well into 15% bracket
        txn = CapitalTransaction(description="Stock", proceeds=80000, cost_basis=30000, is_long_term=True)
        r = simple_compute(wages=150000, cap_txns=[txn])
        assert r.sched_d_long_term_gain == 50000
        assert r.capital_gains_tax > 0  # Should be taxed at 15%

    def test_capital_loss(self):
        txn = CapitalTransaction(description="Crypto", proceeds=5000, cost_basis=15000, is_long_term=False)
        r = simple_compute(wages=50000, cap_txns=[txn])
        assert r.sched_d_short_term_gain == -10000
        assert r.line_7_capital_gain_loss == -10000

    def test_mixed_short_long(self):
        txns = [
            CapitalTransaction(description="A", proceeds=10000, cost_basis=12000, is_long_term=False),
            CapitalTransaction(description="B", proceeds=20000, cost_basis=10000, is_long_term=True),
        ]
        r = simple_compute(wages=50000, cap_txns=txns)
        assert r.sched_d_short_term_gain == -2000
        assert r.sched_d_long_term_gain == 10000
        assert r.sched_d_net_gain == 8000


# ---------------------------------------------------------------------------
# Child Tax Credit
# ---------------------------------------------------------------------------
class TestChildTaxCredit:
    def test_ctc_basic(self):
        r = simple_compute(wages=60000, num_dependents=2)
        assert r.line_27_ctc > 0
        assert r.line_27_ctc <= 2 * CTC_PER_CHILD

    def test_ctc_zero_dependents(self):
        r = simple_compute(wages=60000, num_dependents=0)
        assert r.line_27_ctc == 0

    def test_ctc_phaseout(self):
        # Single filer at $300K AGI → phaseout starts at $200K
        r = simple_compute(wages=300000, num_dependents=1, w2_federal_withheld=60000)
        # Reduction: ($300K - $200K) / $1000 * $50 = $5000 → CTC = max(0, 2000 - 5000) = 0
        assert r.line_27_ctc == 0


# ---------------------------------------------------------------------------
# Illinois IL-1040
# ---------------------------------------------------------------------------
class TestIllinois:
    def test_il_flat_rate(self):
        r = simple_compute(wages=100000)
        expected_base = r.line_11_agi  # Federal AGI = IL base income
        exemption = 1 * IL_PERSONAL_EXEMPTION
        il_taxable = max(0, expected_base - exemption)
        assert r.il_line_11_tax == pytest.approx(round(il_taxable * IL_FLAT_RATE, 2))

    def test_il_mfj_exemptions(self):
        r = simple_compute(filing_status="mfj", wages=100000, num_dependents=3,
                          spouse=make_filer(first_name="Spouse"))
        # 2 (filer + spouse) + 3 dependents = 5 exemptions
        assert r.il_line_9_exemptions == 5 * IL_PERSONAL_EXEMPTION

    def test_il_withholding(self):
        r = simple_compute(wages=50000, w2_state_withheld=2475)
        assert r.il_line_18_withheld == 2475


# ---------------------------------------------------------------------------
# OCR parsing
# ---------------------------------------------------------------------------
class TestOCRParsing:
    def test_parse_w2_basic(self):
        fields = {
            "Employer": {"type": "object", "value": {
                "Name": {"type": "string", "value": "Acme Corp"},
                "IdNumber": {"type": "string", "value": "36-1234567"},
            }},
            "WagesTipsAndOtherCompensation": {"type": "number", "value": "72500.00"},
            "FederalIncomeTaxWithheld": {"type": "number", "value": "10875.00"},
            "SocialSecurityWages": {"type": "number", "value": "72500.00"},
            "SocialSecurityTaxWithheld": {"type": "number", "value": "4495.00"},
            "MedicareWagesAndTips": {"type": "number", "value": "72500.00"},
            "MedicareTaxWithheld": {"type": "number", "value": "1051.25"},
            "StateTaxInfos": {"type": "array", "value": [
                {"type": "object", "value": {
                    "StateWages": {"type": "number", "value": "72500.00"},
                    "StateIncomeTax": {"type": "number", "value": "3588.75"},
                }}
            ]},
            "LocalTaxInfos": {"type": "array", "value": []},
        }
        w2 = parse_w2_from_ocr(fields)
        assert w2.employer_name == "Acme Corp"
        assert w2.wages == 72500.0
        assert w2.federal_withheld == 10875.0
        assert w2.state_withheld == pytest.approx(3588.75)

    def test_parse_w2_dollar_signs(self):
        fields = {
            "WagesTipsAndOtherCompensation": {"type": "number", "value": "$85,000.00"},
            "FederalIncomeTaxWithheld": {"type": "number", "value": "$12,750"},
            "StateTaxInfos": {"type": "array", "value": []},
            "LocalTaxInfos": {"type": "array", "value": []},
        }
        w2 = parse_w2_from_ocr(fields)
        assert w2.wages == 85000.0
        assert w2.federal_withheld == 12750.0

    def test_parse_1099int(self):
        fields = {
            "Transactions": {
                "type": "array",
                "value": [
                    {"type": "object", "value": {
                        "Box1": {"type": "number", "value": "$2,450.00"},
                    }}
                ]
            }
        }
        interest = parse_1099int_from_ocr(fields)
        assert interest == pytest.approx(2450.0)

    def test_parse_1099int_flat(self):
        fields = {"Box1": {"value": "1500.00"}}
        interest = parse_1099int_from_ocr(fields)
        assert interest == pytest.approx(1500.0)


# ---------------------------------------------------------------------------
# Filing status validation
# ---------------------------------------------------------------------------
class TestFilingStatus:
    def test_invalid_status(self):
        with pytest.raises(ValueError, match="Invalid filing status"):
            simple_compute(filing_status="invalid")

    def test_all_statuses(self):
        for status in ["single", "mfj", "hoh", "mfs"]:
            spouse = make_filer(first_name="Spouse") if status == "mfj" else None
            r = simple_compute(filing_status=status, wages=50000, spouse=spouse)
            assert r.filing_status == status
            assert r.draft_id  # should generate an ID


# ---------------------------------------------------------------------------
# End-to-end integration
# ---------------------------------------------------------------------------
class TestEndToEnd:
    def test_single_simple(self):
        r = simple_compute(wages=60000, w2_federal_withheld=9000, w2_state_withheld=2970)
        assert r.line_1a_wages == 60000
        assert r.line_11_agi == 60000
        assert r.line_15_taxable_income == 60000 - STANDARD_DEDUCTION[SINGLE]
        assert r.line_24_total_tax > 0
        assert r.line_33_total_payments > 0

    def test_mfj_with_everything(self):
        biz = BusinessIncome(gross_receipts=50000, advertising=2000, supplies=1000,
                            business_name="Consulting")
        txns = [
            CapitalTransaction(description="AAPL", proceeds=20000, cost_basis=15000, is_long_term=True),
            CapitalTransaction(description="BTC", proceeds=5000, cost_basis=8000, is_long_term=False),
        ]
        d = Deductions(mortgage_interest=15000, property_tax=6000, charitable_cash=4000,
                      student_loan_interest=2500)
        p = Payments(estimated_federal=5000, estimated_state=2000)
        r = simple_compute(
            filing_status="mfj", wages=120000, interest=3000, dividends=5000,
            qual_div=4000, cap_txns=txns, businesses=[biz],
            deductions=d, payments=p, num_dependents=2,
            spouse=make_filer(first_name="Spouse"),
            w2_federal_withheld=20000, w2_state_withheld=5940,
        )
        # Verify key fields populated
        assert r.line_1a_wages == 120000
        assert r.line_2b_taxable_interest == 3000
        assert r.sched_c_total_profit == 47000  # 50K - 2K - 1K
        assert r.se_tax > 0
        assert r.qbi_deduction > 0
        assert r.sched_d_long_term_gain == 5000
        assert r.sched_d_short_term_gain == -3000
        assert r.line_27_ctc > 0
        assert r.il_line_11_tax > 0
        assert len(r.forms_generated) >= 4  # At least 1040, Sch C, SE, IL-1040


# ---------------------------------------------------------------------------
# Refund vs owed
# ---------------------------------------------------------------------------
class TestRefundOrOwed:
    def test_refund(self):
        r = simple_compute(wages=50000, w2_federal_withheld=10000)
        # $50K income, std deduction $15K, taxable $35K → tax ~$3,980
        # Withheld $10K → should get refund
        assert r.line_34_overpaid > 0
        assert r.line_37_owed == 0

    def test_owed(self):
        r = simple_compute(wages=100000, w2_federal_withheld=5000)
        # Underpaid → should owe
        assert r.line_37_owed > 0
        assert r.line_34_overpaid == 0


# ---------------------------------------------------------------------------
# Schedule 2 / Form 8959 / Form 8960 form generation
# ---------------------------------------------------------------------------
class TestSchedule2Forms:
    """Verify Schedule 2, Form 8959, Form 8960 appear in forms_generated."""

    def test_no_sched2_low_income(self):
        """Low-income filer: no SE, no surtaxes → no Schedule 2."""
        r = simple_compute(wages=50000)
        assert "Schedule 2" not in r.forms_generated
        assert "Form 8959" not in r.forms_generated
        assert "Form 8960" not in r.forms_generated

    def test_sched2_from_se_only(self):
        """SE filer below surtax thresholds → Schedule 2 only (no 8959/8960)."""
        biz = BusinessIncome(business_name="Freelance", gross_receipts=60000)
        r = simple_compute(businesses=[biz])
        assert r.se_tax > 0
        assert "Schedule 2" in r.forms_generated
        assert "Form 8959" not in r.forms_generated
        assert "Form 8960" not in r.forms_generated

    def test_sched2_with_8959(self):
        """High W-2 earner → Additional Medicare Tax → Schedule 2 + Form 8959."""
        r = simple_compute(wages=285000)
        assert r.additional_medicare_tax > 0
        assert "Schedule 2" in r.forms_generated
        assert "Form 8959" in r.forms_generated

    def test_sched2_with_8960(self):
        """High AGI + investment income → NIIT → Schedule 2 + Form 8960."""
        cap = [CapitalTransaction(description="Stock", proceeds=50000, cost_basis=20000, is_long_term=True)]
        r = simple_compute(wages=220000, interest=5000, dividends=3000, cap_txns=cap)
        assert r.niit > 0
        assert "Schedule 2" in r.forms_generated
        assert "Form 8960" in r.forms_generated

    def test_all_three_forms(self):
        """High earner with SE + investments → all three forms."""
        biz = BusinessIncome(business_name="Consulting", gross_receipts=100000)
        cap = [CapitalTransaction(description="AAPL", proceeds=30000, cost_basis=15000, is_long_term=True)]
        r = simple_compute(wages=250000, interest=5000, dividends=5000, cap_txns=cap, businesses=[biz])
        assert r.se_tax > 0
        assert r.niit > 0
        assert r.additional_medicare_tax > 0
        assert "Schedule 2" in r.forms_generated
        assert "Form 8959" in r.forms_generated
        assert "Form 8960" in r.forms_generated

    def test_pdf_generation_schedule2(self):
        """Verify PDF files are actually generated for Schedule 2 forms."""
        import tempfile
        from pdf_generator import generate_all_pdfs
        cap = [CapitalTransaction(description="ETF", proceeds=40000, cost_basis=25000, is_long_term=True)]
        r = simple_compute(wages=260000, interest=8000, dividends=4000, cap_txns=cap)
        tmpdir = tempfile.mkdtemp()
        paths = generate_all_pdfs(r, tmpdir)
        assert "schedule_2" in paths
        assert "form_8959" in paths
        assert "form_8960" in paths
        # Verify files exist and have reasonable size
        import os
        for key in ["schedule_2", "form_8959", "form_8960"]:
            assert os.path.exists(paths[key])
            assert os.path.getsize(paths[key]) > 50000  # > 50KB (filled IRS PDF)
