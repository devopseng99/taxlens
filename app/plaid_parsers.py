"""Plaid data → TaxLens tax engine objects.

Converts Plaid investment transactions and holdings into
CapitalTransaction and DividendIncome dataclasses for tax computation.
"""

from datetime import date, datetime

from tax_engine import CapitalTransaction, DividendIncome


# Plaid investment transaction types and subtypes
# https://plaid.com/docs/api/products/investments/#investmentstransactionsget
_SELL_TYPES = {"sell"}
_DIVIDEND_SUBTYPES = {"dividend", "qualified dividend", "non-qualified dividend"}
_CAP_GAIN_SUBTYPES = {"capital gain (long term)", "capital gain (short term)"}


def _parse_date(val) -> str:
    """Convert Plaid date to string."""
    if isinstance(val, (date, datetime)):
        return val.strftime("%Y-%m-%d")
    return str(val) if val else "Various"


def _is_long_term(date_acquired: str | None, date_sold: str | None) -> bool:
    """Determine if a transaction is long-term based on holding period (>1 year)."""
    if not date_acquired or not date_sold:
        return False
    try:
        acquired = datetime.strptime(str(date_acquired), "%Y-%m-%d").date()
        sold = datetime.strptime(str(date_sold), "%Y-%m-%d").date()
        return (sold - acquired).days > 365
    except (ValueError, TypeError):
        return False


def plaid_investments_to_capital_transactions(
    transactions: list[dict],
    securities: list[dict] | None = None,
) -> list[CapitalTransaction]:
    """Convert Plaid sell transactions to CapitalTransaction list.

    Args:
        transactions: Plaid investment_transactions array
        securities: Plaid securities array (for security names)

    Returns:
        List of CapitalTransaction for Schedule D
    """
    # Build security lookup
    sec_map = {}
    if securities:
        for sec in securities:
            sid = sec.get("security_id")
            if sid:
                sec_map[sid] = sec.get("name") or sec.get("ticker_symbol") or "Unknown Security"

    results = []
    for txn in transactions:
        txn_type = (txn.get("type") or "").lower()
        txn_subtype = (txn.get("subtype") or "").lower()

        # Only process sell transactions
        if txn_type not in _SELL_TYPES:
            continue

        # Plaid: amount is negative for sells (outflow from investment account)
        amount = abs(txn.get("amount", 0))
        quantity = abs(txn.get("quantity", 0))
        price = txn.get("price", 0)

        # Cost basis from Plaid (if available)
        cost_basis = txn.get("cost_basis")
        if cost_basis is None:
            cost_basis = 0.0
        cost_basis = abs(cost_basis)

        # If no cost_basis from Plaid, proceeds = amount (best we can do)
        proceeds = amount if amount > 0 else quantity * price

        security_name = sec_map.get(txn.get("security_id"), "Security Sale")
        txn_date = _parse_date(txn.get("date"))

        results.append(CapitalTransaction(
            description=security_name,
            date_acquired="Various",  # Plaid doesn't provide acquisition date on sells
            date_sold=txn_date,
            proceeds=round(proceeds, 2),
            cost_basis=round(cost_basis, 2),
            is_long_term="long" in txn_subtype,
        ))

    return results


def plaid_dividends_to_dividend_income(
    transactions: list[dict],
    securities: list[dict] | None = None,
) -> DividendIncome:
    """Aggregate Plaid dividend transactions into a single DividendIncome.

    Args:
        transactions: Plaid investment_transactions array
        securities: Plaid securities array (for payer names)

    Returns:
        DividendIncome with aggregated totals
    """
    sec_map = {}
    if securities:
        for sec in securities:
            sid = sec.get("security_id")
            if sid:
                sec_map[sid] = sec.get("name") or sec.get("ticker_symbol") or ""

    ordinary = 0.0
    qualified = 0.0
    cap_gain_lt = 0.0
    cap_gain_st = 0.0
    payers = set()

    for txn in transactions:
        txn_subtype = (txn.get("subtype") or "").lower()
        # Plaid: dividend amounts are positive (cash inflow)
        amount = abs(txn.get("amount", 0))

        if txn_subtype in _DIVIDEND_SUBTYPES or txn_subtype == "dividend":
            ordinary += amount
            if txn_subtype == "qualified dividend":
                qualified += amount
            # Track payer
            sec_name = sec_map.get(txn.get("security_id"))
            if sec_name:
                payers.add(sec_name)

        elif "capital gain" in txn_subtype:
            if "long" in txn_subtype:
                cap_gain_lt += amount
            else:
                cap_gain_st += amount

    return DividendIncome(
        payer_name=", ".join(sorted(payers)[:3]) if payers else "Plaid Import",
        ordinary_dividends=round(ordinary, 2),
        qualified_dividends=round(qualified, 2),
        capital_gain_dist=round(cap_gain_lt + cap_gain_st, 2),
    )


def plaid_to_tax_data(
    transactions: list[dict],
    securities: list[dict] | None = None,
) -> dict:
    """Convert all Plaid investment data to tax-ready objects.

    Returns:
        {
            "capital_transactions": list[CapitalTransaction],
            "dividend_income": DividendIncome,
            "summary": { counts and totals }
        }
    """
    cap_txns = plaid_investments_to_capital_transactions(transactions, securities)
    div_income = plaid_dividends_to_dividend_income(transactions, securities)

    total_proceeds = sum(t.proceeds for t in cap_txns)
    total_basis = sum(t.cost_basis for t in cap_txns)

    return {
        "capital_transactions": cap_txns,
        "dividend_income": div_income,
        "summary": {
            "sell_transactions": len(cap_txns),
            "total_proceeds": round(total_proceeds, 2),
            "total_cost_basis": round(total_basis, 2),
            "net_gain_loss": round(total_proceeds - total_basis, 2),
            "ordinary_dividends": div_income.ordinary_dividends,
            "qualified_dividends": div_income.qualified_dividends,
            "capital_gain_distributions": div_income.capital_gain_dist,
        },
    }
