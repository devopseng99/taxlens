"""TaxLens MCP Server — expose tax computation engine as MCP tools.

Mounted on the FastAPI app at /mcp via StreamableHTTP.
Any MCP-capable client (Claude Desktop, Claude Code, custom agents)
can call these tools natively.
"""

import json
import os
from pathlib import Path

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

from tax_engine import (
    PersonInfo, W2Income, CapitalTransaction, BusinessIncome, Deductions,
    AdditionalIncome, DividendIncome, Payments, TaxResult,
    compute_tax,
)
from state_configs import get_state_config, NO_TAX_STATES

STORAGE_ROOT = Path(os.getenv("TAXLENS_STORAGE_ROOT", "/data/documents"))

# Initialize MCP server
mcp = FastMCP(
    name="TaxLens",
    instructions=(
        "TaxLens is a tax computation engine for US federal + state taxes (tax years 2024 and 2025). "
        "Use compute_tax to calculate taxes for any scenario. Use compare_scenarios to "
        "compare filing strategies side-by-side. Use list_states to see supported states. "
        "Set tax_year=2024 for prior year returns."
    ),
    stateless_http=True,
    streamable_http_path="/",
    transport_security=TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=[
            os.getenv("TAXLENS_API_URL", "https://dropit.istayintek.com/api").split("//")[1].split("/")[0],
            "localhost", "127.0.0.1",
        ],
        allowed_origins=[
            os.getenv("TAXLENS_API_URL", "https://dropit.istayintek.com/api").rsplit("/api", 1)[0],
            os.getenv("TAXLENS_LANDING_URL", "https://taxlens.istayintek.com"),
        ],
    ),
)


# ---------------------------------------------------------------------------
# Helper: build engine inputs from simplified MCP tool params
# ---------------------------------------------------------------------------
def _build_inputs(
    filing_status: str,
    wages: float = 0,
    federal_withheld: float = 0,
    interest: float = 0,
    ordinary_dividends: float = 0,
    qualified_dividends: float = 0,
    short_term_gains: float = 0,
    long_term_gains: float = 0,
    business_income: float = 0,
    business_expenses: float = 0,
    mortgage_interest: float = 0,
    property_tax: float = 0,
    state_tax_paid: float = 0,
    charitable: float = 0,
    student_loan_interest: float = 0,
    num_dependents: int = 0,
    residence_state: str = "IL",
    estimated_federal: float = 0,
    estimated_state: float = 0,
    tax_year: int = 2025,
) -> dict:
    """Convert simplified params to engine-ready inputs."""
    filer = PersonInfo(first_name="MCP", last_name="User")
    w2s = []
    if wages > 0:
        w2s.append(W2Income(wages=wages, federal_withheld=federal_withheld,
                            ss_wages=wages, medicare_wages=wages))

    cap_txns = []
    if short_term_gains != 0:
        cap_txns.append(CapitalTransaction(
            description="Short-term gains/losses",
            proceeds=max(short_term_gains, 0),
            cost_basis=max(-short_term_gains, 0),
            is_long_term=False,
        ))
    if long_term_gains != 0:
        cap_txns.append(CapitalTransaction(
            description="Long-term gains/losses",
            proceeds=max(long_term_gains, 0),
            cost_basis=max(-long_term_gains, 0),
            is_long_term=True,
        ))

    additional = AdditionalIncome(
        other_interest=interest,
        ordinary_dividends=ordinary_dividends,
        qualified_dividends=qualified_dividends,
        capital_transactions=cap_txns,
    )

    businesses = []
    if business_income > 0:
        businesses.append(BusinessIncome(
            business_name="Self-Employment",
            gross_receipts=business_income,
            other_expenses=business_expenses,
        ))

    deductions = Deductions(
        mortgage_interest=mortgage_interest,
        property_tax=property_tax,
        state_income_tax_paid=state_tax_paid,
        charitable_cash=charitable,
        student_loan_interest=student_loan_interest,
    )

    payments = Payments(
        estimated_federal=estimated_federal,
        estimated_state=estimated_state,
    )

    return dict(
        filing_status=filing_status,
        filer=filer,
        w2s=w2s,
        additional=additional,
        deductions=deductions,
        payments=payments,
        num_dependents=num_dependents,
        businesses=businesses,
        residence_state=residence_state,
        tax_year=tax_year,
    )


def _result_to_dict(result: TaxResult) -> dict:
    """Convert TaxResult to a clean dict for MCP response."""
    return result.to_summary()


# ---------------------------------------------------------------------------
# MCP Tools
# ---------------------------------------------------------------------------
@mcp.tool()
def compute_tax_scenario(
    filing_status: str,
    wages: float = 0,
    federal_withheld: float = 0,
    interest: float = 0,
    ordinary_dividends: float = 0,
    qualified_dividends: float = 0,
    short_term_gains: float = 0,
    long_term_gains: float = 0,
    business_income: float = 0,
    business_expenses: float = 0,
    mortgage_interest: float = 0,
    property_tax: float = 0,
    state_tax_paid: float = 0,
    charitable: float = 0,
    student_loan_interest: float = 0,
    num_dependents: int = 0,
    residence_state: str = "IL",
    estimated_federal: float = 0,
    estimated_state: float = 0,
    tax_year: int = 2025,
) -> str:
    """Compute federal + state taxes for a given scenario.

    Args:
        filing_status: "single", "mfj" (married filing jointly), "mfs" (married filing separately), or "hoh" (head of household)
        wages: Total W-2 wages
        federal_withheld: Federal income tax withheld from W-2
        interest: Taxable interest income (1099-INT)
        ordinary_dividends: Total ordinary dividends (1099-DIV Box 1a)
        qualified_dividends: Qualified dividends (1099-DIV Box 1b) — taxed at preferential rates
        short_term_gains: Net short-term capital gains (negative for losses)
        long_term_gains: Net long-term capital gains (negative for losses)
        business_income: Gross self-employment / 1099-NEC income
        business_expenses: Total business expenses (deducted from business_income)
        mortgage_interest: Mortgage interest paid (1098 Box 1)
        property_tax: Real estate property tax paid
        state_tax_paid: State income tax paid (for SALT deduction)
        charitable: Charitable contributions
        student_loan_interest: Student loan interest paid (above-the-line deduction)
        num_dependents: Number of qualifying children for Child Tax Credit
        residence_state: Two-letter state code (e.g., "CA", "TX", "IL")
        estimated_federal: Estimated federal tax payments made
        estimated_state: Estimated state tax payments made
        tax_year: Tax year (2024 or 2025, default 2025)

    Returns:
        JSON with full tax computation: income, AGI, deductions, federal tax, state tax, refund/owed
    """
    inputs = _build_inputs(
        filing_status=filing_status, wages=wages, federal_withheld=federal_withheld,
        interest=interest, ordinary_dividends=ordinary_dividends,
        qualified_dividends=qualified_dividends, short_term_gains=short_term_gains,
        long_term_gains=long_term_gains, business_income=business_income,
        business_expenses=business_expenses, mortgage_interest=mortgage_interest,
        property_tax=property_tax, state_tax_paid=state_tax_paid,
        charitable=charitable, student_loan_interest=student_loan_interest,
        num_dependents=num_dependents, residence_state=residence_state,
        estimated_federal=estimated_federal, estimated_state=estimated_state,
        tax_year=tax_year,
    )
    result = compute_tax(**inputs)
    return json.dumps(_result_to_dict(result), indent=2, default=str)


@mcp.tool()
def compare_scenarios(
    scenarios: list[dict],
) -> str:
    """Compare 2+ tax filing scenarios side-by-side.

    Each scenario dict should have the same parameters as compute_tax_scenario.
    Example: [{"filing_status": "single", "wages": 95000}, {"filing_status": "mfj", "wages": 95000}]

    Returns a comparison table with key differences highlighted.
    """
    results = []
    for i, scenario in enumerate(scenarios):
        label = scenario.pop("label", f"Scenario {i + 1}")
        inputs = _build_inputs(**scenario)
        result = compute_tax(**inputs)
        summary = _result_to_dict(result)
        summary["scenario_label"] = label
        results.append(summary)

    # Build comparison
    comparison = {
        "scenarios": results,
        "comparison": {},
    }

    if len(results) >= 2:
        keys = ["total_income", "agi", "deduction_type", "deduction_amount",
                "taxable_income", "federal_tax", "net_refund", "se_tax", "state_taxes"]
        for key in keys:
            vals = [r.get(key) for r in results]
            comparison["comparison"][key] = {
                r.get("scenario_label", f"S{i}"): v for i, (r, v) in enumerate(zip(results, vals))
            }

        # Highlight best option
        refunds = [(r.get("scenario_label"), r.get("net_refund", 0)) for r in results]
        best = max(refunds, key=lambda x: x[1])
        comparison["recommendation"] = f"{best[0]} saves the most (net refund: ${best[1]:,.2f})"

    return json.dumps(comparison, indent=2, default=str)


@mcp.tool()
def estimate_impact(
    base_scenario: dict,
    change_description: str,
    changes: dict,
) -> str:
    """Estimate the tax impact of a change (e.g., "What if I earn $10K more?").

    Args:
        base_scenario: Current tax situation (same params as compute_tax_scenario)
        change_description: Human-readable description of the change
        changes: Dict of param changes to apply on top of base (e.g., {"wages": 105000})

    Returns:
        Base result, modified result, and the delta between them.
    """
    base_inputs = _build_inputs(**base_scenario)
    base_result = compute_tax(**base_inputs)
    base_summary = _result_to_dict(base_result)

    modified_scenario = {**base_scenario, **changes}
    mod_inputs = _build_inputs(**modified_scenario)
    mod_result = compute_tax(**mod_inputs)
    mod_summary = _result_to_dict(mod_result)

    # Compute deltas
    delta_keys = ["total_income", "agi", "taxable_income", "federal_tax",
                  "net_refund", "se_tax", "niit", "additional_medicare_tax"]
    deltas = {}
    for key in delta_keys:
        base_val = base_summary.get(key, 0) or 0
        mod_val = mod_summary.get(key, 0) or 0
        deltas[key] = round(mod_val - base_val, 2)

    return json.dumps({
        "change": change_description,
        "base": base_summary,
        "modified": mod_summary,
        "deltas": deltas,
        "effective_marginal_rate": (
            round(deltas.get("federal_tax", 0) / max(deltas.get("total_income", 1), 1) * 100, 1)
        ),
    }, indent=2, default=str)


@mcp.tool()
def optimize_deductions(
    filing_status: str,
    wages: float = 0,
    federal_withheld: float = 0,
    interest: float = 0,
    ordinary_dividends: float = 0,
    qualified_dividends: float = 0,
    mortgage_interest: float = 0,
    property_tax: float = 0,
    state_tax_paid: float = 0,
    charitable: float = 0,
    student_loan_interest: float = 0,
    num_dependents: int = 0,
    residence_state: str = "IL",
) -> str:
    """Compare itemized vs standard deduction and recommend the better option.

    Returns both computation paths and the savings from the optimal choice.
    """
    # Compute with itemized (engine auto-picks best, but we want to show both)
    base = _build_inputs(
        filing_status=filing_status, wages=wages, federal_withheld=federal_withheld,
        interest=interest, ordinary_dividends=ordinary_dividends,
        qualified_dividends=qualified_dividends, mortgage_interest=mortgage_interest,
        property_tax=property_tax, state_tax_paid=state_tax_paid,
        charitable=charitable, student_loan_interest=student_loan_interest,
        num_dependents=num_dependents, residence_state=residence_state,
    )

    result = compute_tax(**base)
    summary = _result_to_dict(result)

    # Compute with zero itemized deductions to force standard
    no_itemized = _build_inputs(
        filing_status=filing_status, wages=wages, federal_withheld=federal_withheld,
        interest=interest, ordinary_dividends=ordinary_dividends,
        qualified_dividends=qualified_dividends,
        num_dependents=num_dependents, residence_state=residence_state,
    )
    std_result = compute_tax(**no_itemized)
    std_summary = _result_to_dict(std_result)

    itemized_total = mortgage_interest + min(property_tax + state_tax_paid, 10000) + charitable
    std_amount = std_summary["deduction_amount"]

    return json.dumps({
        "optimal_choice": summary["deduction_type"],
        "optimal_deduction": summary["deduction_amount"],
        "optimal_tax": summary["federal_tax"],
        "standard_deduction": std_amount,
        "itemized_total": round(itemized_total, 2),
        "itemized_breakdown": {
            "mortgage_interest": mortgage_interest,
            "salt_capped": min(property_tax + state_tax_paid, 10000),
            "salt_uncapped": round(property_tax + state_tax_paid, 2),
            "charitable": charitable,
        },
        "savings_from_optimal": round(abs(summary["federal_tax"] - std_summary["federal_tax"]), 2),
        "recommendation": (
            f"{'Itemize' if summary['deduction_type'] == 'itemized' else 'Take standard deduction'} "
            f"— saves ${abs(summary['federal_tax'] - std_summary['federal_tax']):,.2f} in federal tax"
        ),
    }, indent=2, default=str)


@mcp.tool()
def get_draft(username: str, draft_id: str) -> str:
    """Retrieve a previously computed tax draft.

    Args:
        username: TaxLens username
        draft_id: Draft ID from a prior computation
    """
    safe_user = username.replace("/", "_").replace("..", "_")
    draft_dir = STORAGE_ROOT / safe_user / "drafts" / draft_id
    result_file = draft_dir / "result.json"
    if not result_file.exists():
        return json.dumps({"error": f"Draft {draft_id} not found for user {username}"})
    return result_file.read_text()


@mcp.tool()
def list_user_drafts(username: str) -> str:
    """List all tax drafts for a user.

    Args:
        username: TaxLens username
    """
    safe_user = username.replace("/", "_").replace("..", "_")
    drafts_dir = STORAGE_ROOT / safe_user / "drafts"
    if not drafts_dir.exists():
        return json.dumps({"drafts": []})

    drafts = []
    for d in sorted(drafts_dir.iterdir()):
        result_file = d / "result.json"
        if result_file.exists():
            data = json.loads(result_file.read_text())
            drafts.append({
                "draft_id": data.get("draft_id"),
                "filing_status": data.get("filing_status"),
                "filer_name": data.get("filer_name"),
                "total_income": data.get("total_income"),
                "net_refund": data.get("net_refund"),
            })
    return json.dumps({"drafts": drafts}, indent=2)


@mcp.tool()
def list_states() -> str:
    """List all supported states with their tax models and rates."""
    # No-tax state names for display
    _NO_TAX_NAMES = {"TX": "Texas", "FL": "Florida"}

    states_info = []
    for code in ["IL", "CA", "NY", "NJ", "PA", "NC", "GA", "OH", "TX", "FL"]:
        config = get_state_config(code)
        if config:
            info = {
                "code": config.abbreviation,
                "name": config.name,
                "tax_type": config.tax_type,
            }
            if config.tax_type == "flat":
                info["rate"] = f"{config.rate * 100:.2f}%"
            elif config.tax_type == "graduated":
                single_brackets = config.brackets.get("single", [])
                if single_brackets:
                    info["top_rate"] = f"{single_brackets[-1][1] * 100:.1f}%"
                    info["brackets"] = len(single_brackets)
            if config.reciprocal_states:
                info["reciprocal_with"] = sorted(config.reciprocal_states)
            states_info.append(info)
        elif code in NO_TAX_STATES:
            states_info.append({
                "code": code,
                "name": _NO_TAX_NAMES.get(code, code),
                "tax_type": "none",
            })
    return json.dumps({"supported_states": states_info, "count": len(states_info)}, indent=2)


# ---------------------------------------------------------------------------
# MCP Resources
# ---------------------------------------------------------------------------
@mcp.resource("taxlens://states")
def resource_states() -> str:
    """Supported states and their tax configurations."""
    return list_states()


@mcp.resource("taxlens://drafts/{username}")
def resource_user_drafts(username: str) -> str:
    """List all tax drafts for a user."""
    return list_user_drafts(username)
