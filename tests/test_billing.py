"""PayPal capture verification and billing config — pure functions, offline."""

from __future__ import annotations

import pytest

from jupiter_core.paypal import (
    PayPalError,
    describe_paypal,
    parse_capture,
    paypal_config,
)


def capture_payload(status="COMPLETED", currency="USD", value="50.00") -> dict:
    """A minimal, realistic PayPal capture reply."""
    return {
        "id": "8XA12345AB1234567",
        "status": status,
        "purchase_units": [
            {
                "reference_id": "default",
                "payments": {
                    "captures": [
                        {
                            "id": "92C12345AB1234567",
                            "status": status,
                            "amount": {"currency_code": currency, "value": value},
                        }
                    ]
                },
            }
        ],
    }


# --------------------------------------------------------------------------
# parse_capture — the happy paths
# --------------------------------------------------------------------------


def test_happy_path_credits_the_full_amount():
    assert parse_capture(capture_payload(), 50) == 50


def test_amount_arrives_as_a_decimal_string():
    # PayPal sends "300.00", never 300.
    assert parse_capture(capture_payload(value="300.00"), 300) == 300


def test_a_one_dollar_topup():
    assert parse_capture(capture_payload(value="1.00"), 1) == 1


# --------------------------------------------------------------------------
# parse_capture — every way a capture can be wrong
# --------------------------------------------------------------------------


def test_non_completed_status_is_rejected():
    with pytest.raises(PayPalError, match="not COMPLETED"):
        parse_capture(capture_payload(status="DECLINED"), 50)


def test_wrong_currency_is_rejected():
    with pytest.raises(PayPalError, match="not USD"):
        parse_capture(capture_payload(currency="EUR"), 50)


def test_amount_mismatch_with_our_order_is_rejected():
    # The client paid 5; our order row says 50.
    with pytest.raises(PayPalError, match="does not match"):
        parse_capture(capture_payload(value="5.00"), 50)


def test_fractional_amount_is_rejected():
    # A fraction of a dollar is not a whole point; never round silently.
    with pytest.raises(PayPalError, match="whole number"):
        parse_capture(capture_payload(value="50.50"), 50)


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"purchase_units": []},
        {"purchase_units": [{}]},
        {"purchase_units": [{"payments": {}}]},
        {"purchase_units": [{"payments": {"captures": []}}]},
        {"purchase_units": [{"payments": {"captures": ["junk"]}}]},
        {"purchase_units": [{"payments": {"captures": [{"status": "COMPLETED"}]}}]},
        {
            "purchase_units": [
                {"payments": {"captures": [{"status": "COMPLETED", "amount": {"currency_code": "USD"}}]}}
            ]
        },
        {
            "purchase_units": [
                {"payments": {"captures": [{"status": "COMPLETED", "amount": {"currency_code": "USD", "value": None}}]}}
            ]
        },
    ],
)
def test_malformed_payloads_are_rejected(payload):
    with pytest.raises(PayPalError):
        parse_capture(payload, 50)


def test_a_null_payload_is_rejected_not_crashed():
    with pytest.raises(PayPalError):
        parse_capture(None, 50)


# --------------------------------------------------------------------------
# paypal_config / describe_paypal — the disabled state
# --------------------------------------------------------------------------


def _with_env(monkeypatch, **values):
    for name in ("PAYPAL_CLIENT_ID", "PAYPAL_CLIENT_SECRET", "PAYPAL_ENV", "PAYPAL_BASE_URL"):
        monkeypatch.delenv(name, raising=False)
    for name, value in values.items():
        monkeypatch.setenv(name, value)


def test_unconfigured_reports_disabled_with_a_reason(monkeypatch):
    _with_env(monkeypatch)
    status = describe_paypal()
    assert status.enabled is False
    assert status.client_id is None
    assert "PAYPAL_CLIENT_ID" in status.reason


def test_configured_reports_enabled(monkeypatch):
    _with_env(monkeypatch, PAYPAL_CLIENT_ID="cid", PAYPAL_CLIENT_SECRET="sec")
    status = describe_paypal()
    assert status.enabled is True
    assert status.reason is None
    assert status.client_id == "cid"


def test_partial_credentials_still_report_disabled(monkeypatch):
    _with_env(monkeypatch, PAYPAL_CLIENT_ID="cid")
    assert describe_paypal().enabled is False


def test_env_defaults_to_sandbox(monkeypatch):
    _with_env(monkeypatch, PAYPAL_CLIENT_ID="cid", PAYPAL_CLIENT_SECRET="sec")
    assert paypal_config().base_url == "https://api-m.sandbox.paypal.com"
    assert paypal_config().env == "sandbox"


def test_live_env_selects_the_live_base_url(monkeypatch):
    _with_env(monkeypatch, PAYPAL_CLIENT_ID="cid", PAYPAL_CLIENT_SECRET="sec", PAYPAL_ENV="live")
    assert paypal_config().base_url == "https://api-m.paypal.com"


def test_an_unknown_env_is_sandbox_never_live(monkeypatch):
    # A typo must never silently point billing at real money.
    _with_env(monkeypatch, PAYPAL_CLIENT_ID="cid", PAYPAL_CLIENT_SECRET="sec", PAYPAL_ENV="production")
    assert paypal_config().base_url == "https://api-m.sandbox.paypal.com"


def test_base_url_override_wins(monkeypatch):
    _with_env(
        monkeypatch,
        PAYPAL_CLIENT_ID="cid",
        PAYPAL_CLIENT_SECRET="sec",
        PAYPAL_ENV="live",
        PAYPAL_BASE_URL="https://example.test/api",
    )
    assert paypal_config().base_url == "https://example.test/api"
