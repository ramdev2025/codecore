"""The PayPal Orders v2 client — the only billing module that talks to the network.

Follows ``semantic.py chat_json()``'s shape: a per-call ``httpx.AsyncClient``
with a timeout, narrow exception mapping, manual status checks, defensive
JSON parsing. Never raises anything but :class:`PayPalError` to its caller.

``parse_capture`` is pure and fully unit-tested; everything else is a thin
authenticated POST around it. Amounts are always verified against the
``billing_orders`` row we wrote when the order was created — never against
what the client claims it paid.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass

import httpx

DEFAULT_TIMEOUT_SECONDS = 20.0

SANDBOX_BASE_URL = "https://api-m.sandbox.paypal.com"
LIVE_BASE_URL = "https://api-m.paypal.com"


class PayPalError(Exception):
    pass


# --------------------------------------------------------------------------
# Config
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class PayPalConfig:
    enabled: bool
    client_id: str | None
    client_secret: str | None
    base_url: str
    env: str


def _env_value() -> tuple[str, str]:
    raw = (os.environ.get("PAYPAL_ENV") or "").strip().lower()
    return (raw or "sandbox", raw)


def paypal_config() -> PayPalConfig:
    """The PayPal connection, from the environment.

    ``PAYPAL_ENV`` defaults to sandbox; anything other than ``live`` is
    treated as sandbox, so a typo cannot silently point billing at real
    money. ``PAYPAL_BASE_URL`` overrides both (for tests).
    """
    env, _ = _env_value()
    client_id = (os.environ.get("PAYPAL_CLIENT_ID") or "").strip() or None
    client_secret = (os.environ.get("PAYPAL_CLIENT_SECRET") or "").strip() or None

    base_url = (os.environ.get("PAYPAL_BASE_URL") or "").strip() or (
        LIVE_BASE_URL if env == "live" else SANDBOX_BASE_URL
    )

    return PayPalConfig(
        enabled=bool(client_id and client_secret),
        client_id=client_id,
        client_secret=client_secret,
        base_url=base_url.rstrip("/"),
        env=env,
    )


@dataclass(frozen=True)
class PayPalStatus:
    enabled: bool
    client_id: str | None
    env: str | None
    reason: str | None


def describe_paypal(config: PayPalConfig | None = None) -> PayPalStatus:
    """The status block for GET /api/billing — the describe_llm pattern.

    Unconfigured is a state to report, never an error: the endpoint stays
    HTTP 200 and the dashboard shows the reason instead of the top-up UI.
    """
    config = config or paypal_config()
    reason = None
    if not config.enabled:
        reason = (
            "no PayPal credentials configured (set PAYPAL_CLIENT_ID and PAYPAL_CLIENT_SECRET)"
        )
    return PayPalStatus(
        enabled=config.enabled,
        client_id=config.client_id,
        env=config.env,
        reason=reason,
    )


# --------------------------------------------------------------------------
# The API calls
# --------------------------------------------------------------------------

_token_cache: dict[str, tuple[str, float]] = {}


async def _token(config: PayPalConfig) -> str:
    """An OAuth2 client-credentials token, cached in-process with expiry.

    Tokens are cached per base_url so a sandbox/live flip in tests cannot
    leak one across environments.
    """
    cached = _token_cache.get(config.base_url)
    if cached and cached[1] > time.monotonic() + 30:
        return cached[0]

    try:
        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT_SECONDS) as client:
            response = await client.post(
                f"{config.base_url}/v1/oauth2/token",
                headers={"content-type": "application/x-www-form-urlencoded"},
                data="grant_type=client_credentials",
                auth=(config.client_id, config.client_secret),
            )
    except httpx.HTTPError as error:
        raise PayPalError(f"cannot reach PayPal ({type(error).__name__})") from error

    if response.status_code != 200:
        raise PayPalError(f"PayPal auth failed ({response.status_code}): {response.text[:200]}")

    try:
        token = response.json().get("access_token")
        expires_in = int(response.json().get("expires_in", 3000))
    except Exception as error:
        raise PayPalError("unexpected response shape from PayPal auth") from error
    if not isinstance(token, str) or not token:
        raise PayPalError("no access_token in PayPal auth reply")

    _token_cache[config.base_url] = (token, time.monotonic() + expires_in)
    return token


async def _post(config: PayPalConfig, path: str, body: dict) -> dict:
    token = await _token(config)
    try:
        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT_SECONDS) as client:
            response = await client.post(
                f"{config.base_url}{path}",
                headers={"authorization": f"Bearer {token}", "content-type": "application/json"},
                json=body,
            )
    except httpx.HTTPError as error:
        raise PayPalError(f"cannot reach PayPal ({type(error).__name__})") from error

    if response.status_code >= 400:
        raise PayPalError(f"PayPal returned {response.status_code}: {response.text[:200]}")

    try:
        parsed = response.json()
    except Exception as error:
        raise PayPalError("unexpected response shape from PayPal") from error
    if not isinstance(parsed, dict):
        raise PayPalError("unexpected response shape from PayPal")
    return parsed


async def create_order(amount_usd: int) -> str:
    """Create a CAPTURE-intent order for ``amount_usd`` whole dollars.

    Returns PayPal's order id. 1 USD == 1 Moon Point, so the point amount
    is the dollar amount — capture re-verifies it against our own record.
    """
    config = paypal_config()
    if not config.enabled:
        raise PayPalError("PayPal is not configured (set PAYPAL_CLIENT_ID and PAYPAL_CLIENT_SECRET)")

    payload = {
        "intent": "CAPTURE",
        "purchase_units": [
            {
                "amount": {"currency_code": "USD", "value": f"{amount_usd:d}.00"},
                "description": f"{amount_usd} Moon Points",
            }
        ],
    }
    reply = await _post(config, "/v2/checkout/orders", payload)
    order_id = reply.get("id")
    if not isinstance(order_id, str) or not order_id:
        raise PayPalError("no order id in PayPal reply")
    return order_id


async def capture_order(order_id: str) -> dict:
    """Capture an approved order. The caller verifies the amount via ``parse_capture``."""
    config = paypal_config()
    if not config.enabled:
        raise PayPalError("PayPal is not configured (set PAYPAL_CLIENT_ID and PAYPAL_CLIENT_SECRET)")
    return await _post(config, f"/v2/checkout/orders/{order_id}/capture", {})


# --------------------------------------------------------------------------
# The pure half
# --------------------------------------------------------------------------


def parse_capture(payload: dict, expected_amount_usd: int) -> int:
    """Verify a PayPal capture reply against the amount WE asked for.

    Returns the points to credit — the verified dollar amount, 1:1.
    Raises :class:`PayPalError` for anything that does not check out: a
    non-COMPLETED status, a non-USD currency, an amount mismatch, or a
    malformed payload. Every value is treated as untrusted input.

    PayPal sends amounts as strings like ``"50.00"``, so compare
    ``int(float(value))`` — a fraction of a dollar is not a whole point
    and must never round silently.
    """
    try:
        units = payload.get("purchase_units")
        if not isinstance(units, list) or not units:
            raise PayPalError("capture reply had no purchase units")
        payments = units[0].get("payments")
        if not isinstance(payments, dict):
            raise PayPalError("capture reply had no payments block")
        captures = payments.get("captures")
        if not isinstance(captures, list) or not captures:
            raise PayPalError("capture reply had no captures")
        capture = captures[0]
        if not isinstance(capture, dict):
            raise PayPalError("malformed capture entry")
        if capture.get("status") != "COMPLETED":
            raise PayPalError(f"capture status was {capture.get('status')!r}, not COMPLETED")

        amount = capture.get("amount")
        if not isinstance(amount, dict):
            raise PayPalError("capture had no amount block")
        if amount.get("currency_code") != "USD":
            raise PayPalError(f"capture currency was {amount.get('currency_code')!r}, not USD")

        raw_value = amount.get("value")
        if not isinstance(raw_value, str) or not raw_value:
            raise PayPalError("capture amount was missing")
        try:
            credited = int(float(raw_value))
        except ValueError as error:
            raise PayPalError(f"capture amount was unparseable: {raw_value!r}") from error
        if float(raw_value) != credited:
            raise PayPalError(f"capture amount {raw_value} is not a whole number of points")

        if credited != expected_amount_usd:
            raise PayPalError(
                f"capture amount {credited} does not match order amount {expected_amount_usd}"
            )
        return credited
    except PayPalError:
        raise
    except (AttributeError, KeyError, TypeError, IndexError) as error:
        raise PayPalError("malformed capture reply from PayPal") from error
