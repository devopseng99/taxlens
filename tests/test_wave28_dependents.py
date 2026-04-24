"""Unit tests for Wave 28 — Structured Dependent Data Model.

Tests age-based credit eligibility: CTC (under 17), EITC (under 19/24/disabled),
CDCC (under 13/disabled), and backward compatibility with num_dependents integer.

Run: PYTHONPATH=app pytest tests/test_wave28_dependents.py -v
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'app'))

import pytest
from tax_engine import (
    PersonInfo, W2Income, Deductions, AdditionalIncome, Payments,
    Dependent, DependentCareExpense, compute_tax,
)
from tax_config import *


def make_filer(**kw):
    defaults = dict(first_name="Test", last_name="User", ssn="123-45-6789",
                    address_city="Chicago", address_state="IL", address_zip="60601")
    defaults.update(kw)
    return PersonInfo(**defaults)


def compute(dependents=None, num_dependents=0, wages=50000, filing_status="single", **kw):
    """Helper with structured dependents support."""
    w2s = [W2Income(wages=wages, federal_withheld=wages * 0.15,
                    ss_wages=wages, medicare_wages=wages)]
    return compute_tax(
        filing_status=filing_status,
        filer=make_filer(),
        w2s=w2s,
        additional=AdditionalIncome(),
        deductions=Deductions(),
        payments=Payments(),
        dependents=dependents,
        num_dependents=num_dependents,
        **kw,
    )


# ---------------------------------------------------------------------------
# Dependent dataclass — age calculation
# ---------------------------------------------------------------------------
class TestDependentAge:
    def test_age_at_year_end(self):
        d = Dependent(first_name="Child", date_of_birth="2015-06-15")
        assert d.age_at_year_end(2025) == 10

    def test_age_born_jan_1(self):
        """Born Jan 1 2009 — age 16 at end of 2025."""
        d = Dependent(first_name="Child", date_of_birth="2009-01-01")
        assert d.age_at_year_end(2025) == 16

    def test_age_no_dob(self):
        d = Dependent(first_name="Child")
        assert d.age_at_year_end(2025) == -1

    def test_age_invalid_dob(self):
        d = Dependent(first_name="Child", date_of_birth="bad-date")
        assert d.age_at_year_end(2025) == -1


# ---------------------------------------------------------------------------
# CTC qualification — under 17
# ---------------------------------------------------------------------------
class TestCTCQualification:
    def test_child_under_17_qualifies(self):
        d = Dependent(first_name="Child", date_of_birth="2015-03-01")
        assert d.qualifies_ctc(2025) is True  # age 10

    def test_child_exactly_17_does_not_qualify(self):
        d = Dependent(first_name="Teen", date_of_birth="2008-06-01")
        assert d.qualifies_ctc(2025) is False  # age 17

    def test_child_16_qualifies(self):
        d = Dependent(first_name="Teen", date_of_birth="2009-06-01")
        assert d.qualifies_ctc(2025) is True  # age 16

    def test_no_dob_assumes_qualifies(self):
        d = Dependent(first_name="Child")
        assert d.qualifies_ctc(2025) is True

    def test_ctc_uses_structured_dependents(self):
        """2 children: one under 17, one over 17. Only 1 gets CTC."""
        deps = [
            Dependent(first_name="Young", date_of_birth="2015-01-01"),   # age 10 — CTC
            Dependent(first_name="Old", date_of_birth="2005-01-01"),     # age 20 — no CTC
        ]
        r = compute(dependents=deps, wages=80000)
        assert r.num_dependents == 2
        assert r.num_ctc_children == 1
        assert r.line_27_ctc == CTC_PER_CHILD  # $2,000 for 1 child

    def test_ctc_all_under_17(self):
        deps = [
            Dependent(first_name="A", date_of_birth="2015-01-01"),
            Dependent(first_name="B", date_of_birth="2018-06-01"),
        ]
        r = compute(dependents=deps, wages=80000)
        assert r.num_ctc_children == 2
        assert r.line_27_ctc == 2 * CTC_PER_CHILD


# ---------------------------------------------------------------------------
# EITC qualification — under 19 (or 24 student, or disabled)
# ---------------------------------------------------------------------------
class TestEITCQualification:
    def test_child_under_19_qualifies(self):
        d = Dependent(first_name="Teen", date_of_birth="2010-01-01")
        assert d.qualifies_eitc(2025) is True  # age 15

    def test_child_19_does_not_qualify(self):
        d = Dependent(first_name="Adult", date_of_birth="2006-01-01")
        assert d.qualifies_eitc(2025) is False  # age 19

    def test_student_under_24_qualifies(self):
        d = Dependent(first_name="Student", date_of_birth="2004-01-01", is_student=True)
        assert d.qualifies_eitc(2025) is True  # age 21, student

    def test_student_24_does_not_qualify(self):
        d = Dependent(first_name="Grad", date_of_birth="2001-01-01", is_student=True)
        assert d.qualifies_eitc(2025) is False  # age 24, student but too old

    def test_disabled_any_age_qualifies(self):
        d = Dependent(first_name="Adult", date_of_birth="1990-01-01", is_disabled=True)
        assert d.qualifies_eitc(2025) is True  # age 35, disabled

    def test_eitc_structured_dependents(self):
        """Low income with 1 EITC-qualifying child and 1 adult non-qualifying."""
        deps = [
            Dependent(first_name="Child", date_of_birth="2015-01-01"),   # age 10 — EITC
            Dependent(first_name="Adult", date_of_birth="2000-01-01"),   # age 25 — no EITC
        ]
        r = compute(dependents=deps, wages=20000)
        assert r.num_eitc_children == 1
        assert r.eitc > 0


# ---------------------------------------------------------------------------
# CDCC qualification — under 13 or disabled
# ---------------------------------------------------------------------------
class TestCDCCQualification:
    def test_child_under_13_qualifies(self):
        d = Dependent(first_name="Child", date_of_birth="2018-01-01")
        assert d.qualifies_cdcc(2025) is True  # age 7

    def test_child_13_does_not_qualify(self):
        d = Dependent(first_name="Teen", date_of_birth="2012-01-01")
        assert d.qualifies_cdcc(2025) is False  # age 13

    def test_disabled_any_age_qualifies_cdcc(self):
        d = Dependent(first_name="Adult", date_of_birth="1990-01-01", is_disabled=True)
        assert d.qualifies_cdcc(2025) is True


# ---------------------------------------------------------------------------
# Backward compatibility — num_dependents integer
# ---------------------------------------------------------------------------
class TestBackwardCompat:
    def test_num_dependents_still_works(self):
        """When no structured dependents, num_dependents is used for all credits."""
        r = compute(num_dependents=2, wages=80000)
        assert r.num_dependents == 2
        assert r.num_ctc_children == 2  # Backward compat assumes all qualify
        assert r.num_eitc_children == 2
        assert r.line_27_ctc > 0

    def test_structured_overrides_count(self):
        """Structured dependents override num_dependents."""
        deps = [Dependent(first_name="A", date_of_birth="2015-01-01")]
        r = compute(dependents=deps, num_dependents=5)
        # num_dependents should be recalculated from structured list
        assert r.num_dependents == 1

    def test_empty_dependents_uses_count(self):
        """Empty dependents list falls back to num_dependents."""
        r = compute(dependents=[], num_dependents=3, wages=80000)
        assert r.num_dependents == 3
        assert r.num_ctc_children == 3


# ---------------------------------------------------------------------------
# Mixed scenarios — different ages for different credits
# ---------------------------------------------------------------------------
class TestMixedAgeScenarios:
    def test_teen_gets_eitc_not_ctc(self):
        """17-year-old: qualifies for EITC (under 19) but not CTC (not under 17)."""
        deps = [Dependent(first_name="Teen", date_of_birth="2008-06-01")]  # age 17
        r = compute(dependents=deps, wages=20000)
        assert r.num_ctc_children == 0
        assert r.num_eitc_children == 1
        assert r.line_27_ctc == 0
        assert r.eitc > 0  # Gets EITC with 1 child

    def test_13_year_old_gets_ctc_eitc_not_cdcc(self):
        """13-year-old: CTC (under 17), EITC (under 19), but NOT CDCC (not under 13)."""
        deps = [Dependent(first_name="Teen", date_of_birth="2012-01-01")]  # age 13
        r = compute(dependents=deps, wages=20000)
        assert r.num_ctc_children == 1
        assert r.num_eitc_children == 1
        assert r.num_cdcc_dependents == 0

    def test_family_with_varied_ages(self):
        """3 kids: age 5 (all credits), age 14 (CTC+EITC), age 20 (none)."""
        deps = [
            Dependent(first_name="Baby", date_of_birth="2020-03-15"),     # age 5
            Dependent(first_name="Teen", date_of_birth="2011-08-20"),     # age 14
            Dependent(first_name="College", date_of_birth="2005-01-10"),  # age 20
        ]
        r = compute(dependents=deps, wages=60000)
        assert r.num_dependents == 3
        assert r.num_ctc_children == 2   # Baby (5) + Teen (14)
        assert r.num_eitc_children == 2  # Baby (5) + Teen (14), College is 20 (not student)
        assert r.num_cdcc_dependents == 1  # Only Baby (5) is under 13

    def test_disabled_adult_counts_for_eitc_cdcc_not_ctc(self):
        """Disabled adult: EITC + CDCC (any age if disabled), but NOT CTC (requires under 17).

        IRS rule: CTC is strictly under 17. Disabled adults over 17 get ODC ($500),
        not the full CTC ($2,000). We don't yet implement ODC, so CTC count = 0.
        """
        deps = [Dependent(first_name="Alex", date_of_birth="1990-01-01", is_disabled=True)]
        r = compute(dependents=deps, wages=30000)
        assert r.num_ctc_children == 0   # CTC requires under 17 (disabled doesn't override)
        assert r.num_eitc_children == 1  # EITC: disabled = any age
        assert r.num_cdcc_dependents == 1  # CDCC: disabled = any age

    def test_college_student_eitc_only(self):
        """22-year-old student: EITC (under 24 student) but not CTC (not under 17)."""
        deps = [Dependent(first_name="Grad", date_of_birth="2003-06-01", is_student=True)]
        r = compute(dependents=deps, wages=20000)
        assert r.num_ctc_children == 0
        assert r.num_eitc_children == 1
        assert r.eitc > 0


# ---------------------------------------------------------------------------
# Summary includes dependent details
# ---------------------------------------------------------------------------
class TestSummaryDependents:
    def test_summary_has_dependent_info(self):
        deps = [
            Dependent(first_name="Alice", last_name="Smith", date_of_birth="2015-01-01"),
            Dependent(first_name="Bob", last_name="Smith", date_of_birth="2018-06-01"),
        ]
        r = compute(dependents=deps, wages=80000)
        s = r.to_summary()
        assert s["num_dependents"] == 2
        assert s["num_ctc_children"] == 2
        assert len(s["dependents"]) == 2
        assert s["dependents"][0]["name"] == "Alice Smith"
        assert s["dependents"][0]["ctc"] is True
        assert s["dependents"][1]["name"] == "Bob Smith"

    def test_summary_no_dependents(self):
        r = compute(wages=50000)
        s = r.to_summary()
        assert s["num_dependents"] == 0
        assert s["dependents"] == []
