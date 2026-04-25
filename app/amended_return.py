"""Amended return engine — Form 1040-X computation.

Computes line-by-line differences between an original and amended return,
generating columns A (original), B (change), and C (corrected).
"""

from dataclasses import dataclass, field
from typing import Optional

from tax_engine import TaxResult


@dataclass
class AmendedLine:
    """A single line in the 1040-X comparison."""
    line: str = ""
    description: str = ""
    column_a: float = 0.0  # Original amount
    column_b: float = 0.0  # Net change (increase or decrease)
    column_c: float = 0.0  # Corrected amount


@dataclass
class AmendedReturn:
    """Complete Form 1040-X comparison."""
    original_draft_id: str = ""
    amended_draft_id: str = ""
    tax_year: int = 2025
    filing_status: str = "single"
    lines: list[AmendedLine] = field(default_factory=list)
    explanation: str = ""
    refund_change: float = 0.0  # Positive = additional refund, negative = amount owed
    total_tax_change: float = 0.0


def compute_amended_return(
    original: TaxResult,
    amended: TaxResult,
    explanation: str = "",
    original_draft_id: str = "",
    amended_draft_id: str = "",
) -> AmendedReturn:
    """Compute Form 1040-X differences between original and amended returns.

    Args:
        original: TaxResult from the original return
        amended: TaxResult from the amended return
        explanation: Part III explanation of changes

    Returns:
        AmendedReturn with line-by-line A/B/C columns
    """
    lines = []

    # Line-by-line comparison following 1040-X structure
    _comparisons = [
        ("1", "Adjusted gross income", "line_11_agi"),
        ("2", "Itemized deductions or standard deduction", "line_12_deductions"),
        ("3", "Exemptions (not applicable 2018+)", None),
        ("4", "Taxable income", "line_15_taxable_income"),
        ("5", "Tax", "line_16_tax"),
        ("6", "Credits", "line_21_total_credits"),
        ("7", "Subtract line 6 from line 5", None),  # Computed
        ("8", "Other taxes", None),
        ("9", "Total tax", "line_24_total_tax"),
        ("10", "Total payments", "line_33_total_payments"),
        ("11", "Overpayment on original", "line_34_overpaid"),
        ("12", "Amount owed on original", "line_37_owed"),
        # Income breakdown
        ("I-1", "Wages, salaries, tips", "line_1a_wages"),
        ("I-2b", "Taxable interest", "line_2b_taxable_interest"),
        ("I-3b", "Ordinary dividends", "line_3b_ordinary_dividends"),
        ("I-8", "Other income (Schedule 1)", "sched_1_other_income"),
        ("I-9", "Total income", "line_9_total_income"),
    ]

    for line_num, desc, attr in _comparisons:
        if attr is None:
            # Computed or N/A lines
            if line_num == "7":
                orig_val = getattr(original, "line_16_tax", 0) - getattr(original, "line_21_total_credits", 0)
                amend_val = getattr(amended, "line_16_tax", 0) - getattr(amended, "line_21_total_credits", 0)
            else:
                orig_val = 0
                amend_val = 0
        else:
            orig_val = getattr(original, attr, 0)
            amend_val = getattr(amended, attr, 0)

        change = amend_val - orig_val
        lines.append(AmendedLine(
            line=line_num,
            description=desc,
            column_a=round(orig_val, 2),
            column_b=round(change, 2),
            column_c=round(amend_val, 2),
        ))

    # Compute overall change
    tax_change = amended.line_24_total_tax - original.line_24_total_tax
    orig_net = original.line_34_overpaid - original.line_37_owed
    amend_net = amended.line_34_overpaid - amended.line_37_owed
    refund_change = amend_net - orig_net

    # Auto-generate explanation if not provided
    if not explanation:
        changes = []
        for line in lines:
            if abs(line.column_b) > 0.01:
                direction = "increased" if line.column_b > 0 else "decreased"
                changes.append(f"{line.description} {direction} by ${abs(line.column_b):,.2f}")
        explanation = "; ".join(changes[:5])
        if len(changes) > 5:
            explanation += f" (and {len(changes) - 5} more changes)"

    return AmendedReturn(
        original_draft_id=original_draft_id,
        amended_draft_id=amended_draft_id,
        tax_year=original.tax_year,
        filing_status=original.filing_status,
        lines=lines,
        explanation=explanation,
        refund_change=round(refund_change, 2),
        total_tax_change=round(tax_change, 2),
    )
