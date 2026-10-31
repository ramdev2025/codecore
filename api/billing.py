"""Billing routes: Moon Points, PayPal orders, plans, and developer teams.

Same contract as ``routes.py``: handlers stay thin — parse, authenticate,
call ``jupiter_core``, serialize. Unconfigured PayPal is reported, not
raised (the semantic.py pattern), so the dashboard can always render the
Billing page.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from fastapi import APIRouter, Body, Depends

from jupiter_core.billing_repo import (
    billing_overview,
    order_amount,
    record_order_created,
    record_topup,
    redeem_plan,
    settle_billing,
)
from jupiter_core.errors import JupiterError, bad_request, unprocessable
from jupiter_core.paypal import (
    PayPalError,
    capture_order,
    create_order,
    describe_paypal,
    parse_capture,
    paypal_config,
)
from jupiter_core.teams_repo import (
    add_team_member,
    create_team,
    delete_team,
    list_teams,
    remove_team_member,
)

from .deps import current_member, current_principal, db_conn

router = APIRouter(prefix="/api")

MIN_TOPUP_USD = 1
MAX_TOPUP_USD = 10_000


def _dump(value: Any) -> Any:
    return asdict(value) if hasattr(value, "__dataclass_fields__") else value


def _require_int(body: dict, field: str) -> int:
    value = body.get(field)
    if isinstance(value, bool) or not isinstance(value, int):
        # Accept a numeric string, but never silently coerce junk.
        if isinstance(value, str) and value.strip().lstrip("-").isdigit():
            return int(value.strip())
        raise unprocessable(f"{field} must be an integer")
    return value


@router.get("/billing")
async def get_billing(principal=Depends(current_principal), aconn=Depends(db_conn)) -> dict:
    """Wallet, plan, cycle, and the pricing catalog.

    HTTP 200 even when PayPal is unconfigured — ``paypal.reason`` carries
    why, and the top-up card renders as the disabled state.
    """
    return _dump(await billing_overview(aconn, principal.org_id))


@router.post("/billing/orders", status_code=201)
async def post_billing_orders(
    body: dict = Body(default_factory=dict),
    principal=Depends(current_member),
    aconn=Depends(db_conn),
) -> dict:
    """Create a PayPal order for a whole-dollar top-up (1 USD = 1 Moon Point)."""
    config = paypal_config()
    if not config.enabled:
        raise JupiterError(409, f"billing is not configured: {_disabled_reason()}")

    amount = _require_int(body, "amount_usd")
    if amount < MIN_TOPUP_USD or amount > MAX_TOPUP_USD:
        raise unprocessable(f"amount_usd must be between {MIN_TOPUP_USD} and {MAX_TOPUP_USD}")

    try:
        order_id = await create_order(amount)
    except PayPalError as error:
        raise JupiterError(502, f"PayPal order creation failed: {error}") from error

    await record_order_created(aconn, principal.org_id, order_id, amount)
    return {"paypal_order_id": order_id, "amount_usd": amount}


@router.post("/billing/orders/{order_id}/capture")
async def post_billing_capture(
    order_id: str,
    principal=Depends(current_member),
    aconn=Depends(db_conn),
) -> dict:
    """Capture an approved order and credit the points, idempotently.

    The amount is verified against our own ``billing_orders`` row — the
    client's say-so is never trusted. Credits before settling billing, so
    a top-up arriving just after a lapse funds the renewal.
    """
    config = paypal_config()
    if not config.enabled:
        raise JupiterError(409, f"billing is not configured: {_disabled_reason()}")

    expected = await order_amount(aconn, principal.org_id, order_id)
    if expected is None:
        # Unknown here means never-created-by-us or another org's order;
        # both read as absent.
        raise bad_request(f"unknown order: {order_id}")

    try:
        reply = await capture_order(order_id)
        points = parse_capture(reply, expected)
    except PayPalError as error:
        raise JupiterError(502, f"PayPal capture failed: {error}") from error

    async with aconn.transaction():
        # record_topup claims the order row (UPDATE ... WHERE status='created'),
        # the exactly-once gate; settle_billing then takes the org-row FOR
        # UPDATE. Credit first so a renewal settling just after a lapse sees
        # the money — the deliberate exception to settle-then-read.
        result = await record_topup(aconn, principal.org_id, order_id, points)
        await settle_billing(aconn, principal.org_id)

    return _dump(result)


@router.post("/billing/redeem")
async def post_billing_redeem(
    body: dict = Body(default_factory=dict),
    principal=Depends(current_member),
    aconn=Depends(db_conn),
) -> dict:
    """Redeem points for a plan cycle. 422 unknown plan; 402 short balance."""
    raw_plan = body.get("plan")
    if not isinstance(raw_plan, str) or not raw_plan.strip():
        raise unprocessable("plan must not be empty")
    return _dump(await redeem_plan(aconn, principal, raw_plan.strip()))


# --------------------------------------------------------------------------
# Developer teams
# --------------------------------------------------------------------------


@router.get("/teams")
async def get_teams(principal=Depends(current_principal), aconn=Depends(db_conn)) -> dict:
    return {"teams": [_dump(t) for t in await list_teams(aconn, principal.org_id)]}


@router.post("/teams", status_code=201)
async def post_teams(
    body: dict = Body(default_factory=dict),
    principal=Depends(current_member),
    aconn=Depends(db_conn),
) -> dict:
    name = body.get("name")
    if not isinstance(name, str) or not name.strip():
        raise unprocessable("name must not be empty")
    return _dump(await create_team(aconn, principal, name))


@router.delete("/teams/{team_id}")
async def delete_team_route(
    team_id: int,
    principal=Depends(current_member),
    aconn=Depends(db_conn),
) -> dict:
    return _dump(await delete_team(aconn, principal.org_id, team_id))


@router.post("/teams/{team_id}/members", status_code=201)
async def post_team_member(
    team_id: int,
    body: dict = Body(default_factory=dict),
    principal=Depends(current_member),
    aconn=Depends(db_conn),
) -> dict:
    member_id = _require_int(body, "member_id")
    return _dump(await add_team_member(aconn, principal.org_id, team_id, member_id))


@router.delete("/teams/{team_id}/members/{member_id}")
async def delete_team_member(
    team_id: int,
    member_id: int,
    principal=Depends(current_member),
    aconn=Depends(db_conn),
) -> dict:
    return _dump(await remove_team_member(aconn, principal.org_id, team_id, member_id))


def _disabled_reason() -> str:
    reason = describe_paypal().reason
    return reason or "PayPal is not configured"
