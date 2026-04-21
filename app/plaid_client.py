"""Plaid API client wrapper — manages connection to Plaid for financial data import.

Requires environment variables:
- PLAID_CLIENT_ID
- PLAID_SECRET
- PLAID_ENV (sandbox | production, default: sandbox)
"""

import os
from datetime import date, timedelta

import plaid
from plaid.api import plaid_api
from plaid.model.country_code import CountryCode
from plaid.model.products import Products
from plaid.model.link_token_create_request import LinkTokenCreateRequest
from plaid.model.link_token_create_request_user import LinkTokenCreateRequestUser
from plaid.model.item_public_token_exchange_request import ItemPublicTokenExchangeRequest
from plaid.model.item_remove_request import ItemRemoveRequest
from plaid.model.investments_transactions_get_request import InvestmentsTransactionsGetRequest
from plaid.model.investments_transactions_get_request_options import InvestmentsTransactionsGetRequestOptions
from plaid.model.investments_holdings_get_request import InvestmentsHoldingsGetRequest

PLAID_CLIENT_ID = os.getenv("PLAID_CLIENT_ID", "")
PLAID_SECRET = os.getenv("PLAID_SECRET", "")
PLAID_ENV = os.getenv("PLAID_ENV", "sandbox")

_ENVIRONMENTS = {
    "sandbox": plaid.Environment.Sandbox,
    "production": plaid.Environment.Production,
}


def get_plaid_client() -> plaid_api.PlaidApi:
    """Create and return a configured Plaid API client."""
    if not PLAID_CLIENT_ID or not PLAID_SECRET:
        raise RuntimeError("Plaid credentials not configured. Set PLAID_CLIENT_ID and PLAID_SECRET.")

    configuration = plaid.Configuration(
        host=_ENVIRONMENTS.get(PLAID_ENV, plaid.Environment.Sandbox),
        api_key={
            "clientId": PLAID_CLIENT_ID,
            "secret": PLAID_SECRET,
        },
    )
    api_client = plaid.ApiClient(configuration)
    return plaid_api.PlaidApi(api_client)


def create_link_token(client: plaid_api.PlaidApi, user_id: str) -> dict:
    """Create a Plaid Link token for frontend initialization.

    Args:
        client: Plaid API client
        user_id: Unique identifier for the user (e.g., TaxLens username)

    Returns:
        dict with link_token, expiration, request_id
    """
    request = LinkTokenCreateRequest(
        products=[Products("investments")],
        client_name="TaxLens",
        country_codes=[CountryCode("US")],
        language="en",
        user=LinkTokenCreateRequestUser(client_user_id=user_id),
    )
    response = client.link_token_create(request)
    return response.to_dict()


def exchange_public_token(client: plaid_api.PlaidApi, public_token: str) -> dict:
    """Exchange a public_token from Plaid Link for a persistent access_token.

    Args:
        client: Plaid API client
        public_token: Token from Plaid Link onSuccess callback

    Returns:
        dict with access_token, item_id, request_id
    """
    request = ItemPublicTokenExchangeRequest(public_token=public_token)
    response = client.item_public_token_exchange(request)
    return response.to_dict()


def get_investment_transactions(
    client: plaid_api.PlaidApi,
    access_token: str,
    start_date: date | None = None,
    end_date: date | None = None,
) -> dict:
    """Fetch investment transactions for an account.

    Args:
        client: Plaid API client
        access_token: Persistent access token for the connected account
        start_date: Start of date range (default: Jan 1 of tax year)
        end_date: End of date range (default: Dec 31 of tax year)

    Returns:
        dict with investment_transactions, accounts, securities, holdings
    """
    if start_date is None:
        start_date = date(2025, 1, 1)
    if end_date is None:
        end_date = date(2025, 12, 31)

    all_transactions = []
    offset = 0
    total = None

    while total is None or offset < total:
        request = InvestmentsTransactionsGetRequest(
            access_token=access_token,
            start_date=start_date,
            end_date=end_date,
            options=InvestmentsTransactionsGetRequestOptions(
                count=100,
                offset=offset,
            ),
        )
        response = client.investments_transactions_get(request)
        data = response.to_dict()
        all_transactions.extend(data.get("investment_transactions", []))
        total = data.get("total_investment_transactions", len(all_transactions))
        offset += len(data.get("investment_transactions", []))

        if not data.get("investment_transactions"):
            break

    return {
        "investment_transactions": all_transactions,
        "accounts": data.get("accounts", []),
        "securities": data.get("securities", []),
        "total_investment_transactions": total,
    }


def get_holdings(client: plaid_api.PlaidApi, access_token: str) -> dict:
    """Fetch current investment holdings.

    Returns:
        dict with holdings, accounts, securities
    """
    request = InvestmentsHoldingsGetRequest(access_token=access_token)
    response = client.investments_holdings_get(request)
    return response.to_dict()


def remove_item(client: plaid_api.PlaidApi, access_token: str) -> dict:
    """Remove a connected Plaid item (disconnect institution).

    Returns:
        dict with request_id
    """
    request = ItemRemoveRequest(access_token=access_token)
    response = client.item_remove(request)
    return response.to_dict()
