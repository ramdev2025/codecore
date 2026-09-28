import pytest

from jupiter_core.auth import (
    InvalidKey,
    extract_key,
    hash_key,
    mint_admin_key,
    mint_member_key,
    parse_key,
    verify_key,
)
from jupiter_core.errors import JupiterError


def test_mint_and_parse_member_key():
    key = mint_member_key(42)
    parsed = parse_key(key)
    assert parsed.kind == "member"
    assert parsed.record_id == 42


def test_mint_and_parse_admin_key():
    key = mint_admin_key(7)
    parsed = parse_key(key)
    assert parsed.kind == "admin"
    assert parsed.record_id == 7


def test_parse_key_splits_on_first_two_underscores_only():
    # The secret may itself contain underscores.
    key = "jpm_5_abc_def_ghi"
    parsed = parse_key(key)
    assert parsed.kind == "member"
    assert parsed.record_id == 5


@pytest.mark.parametrize(
    "bad_key",
    [
        "",
        "   ",
        "nounderscored",
        "onlyone_part",
        "jpx_1_secret",  # unknown prefix
        "jpm_abc_secret",  # non-digit id
        "jpm_1_",  # empty secret
        "jpm_-1_secret",  # negative id (fails digit regex)
        "a" * 600,  # too long
    ],
)
def test_parse_key_rejects_malformed(bad_key):
    with pytest.raises(InvalidKey):
        parse_key(bad_key)


def test_parse_key_rejects_out_of_range_id():
    with pytest.raises(InvalidKey):
        parse_key(f"jpm_{2**60}_secret")


def test_verify_key_roundtrip():
    key = mint_member_key(1)
    digest = hash_key(key)
    assert verify_key(key, digest) is True
    assert verify_key("jpm_1_wrongsecret", digest) is False


def test_verify_key_with_pepper():
    key = mint_member_key(1)
    digest = hash_key(key, pepper="s3cr3t")
    assert verify_key(key, digest, pepper="s3cr3t") is True
    # Wrong pepper must not verify.
    assert verify_key(key, digest, pepper="other") is False
    # No pepper at verify time when one was used to mint must not verify.
    assert verify_key(key, digest, pepper=None) is False


def test_verify_key_empty_hash_never_verifies():
    key = mint_member_key(1)
    assert verify_key(key, "") is False
    assert verify_key(key, None) is False


def test_verify_key_malformed_hash_never_verifies():
    key = mint_member_key(1)
    assert verify_key(key, "not-hex") is False
    assert verify_key(key, "ab" * 16) is False  # too short (32 hex chars, need 64)


def test_verify_key_always_computes_digest(monkeypatch):
    """Always hashes and always compares, even when the stored hash is
    missing - closes the member-id-enumeration-by-timing gap."""
    calls = []
    import jupiter_core.auth as auth_mod

    real_digest = auth_mod._digest

    def spy_digest(key, pepper=None):
        calls.append(key)
        return real_digest(key, pepper)

    monkeypatch.setattr(auth_mod, "_digest", spy_digest)

    auth_mod.verify_key("jpm_1_x", None)
    auth_mod.verify_key("jpm_1_x", "ab" * 32)
    assert len(calls) == 2


class _Headers(dict):
    def get(self, key, default=None):
        return super().get(key.lower(), default)


def _headers(**kwargs):
    return _Headers({k.lower(): v for k, v in kwargs.items()})


def test_extract_key_prefers_x_api_key():
    headers = _headers(**{"X-Api-Key": " jpm_1_a ", "Authorization": "Bearer jpm_2_b"})
    assert extract_key(headers) == "jpm_1_a"


def test_extract_key_bearer_scheme():
    headers = _headers(Authorization="Bearer jpm_1_a")
    assert extract_key(headers) == "jpm_1_a"


def test_extract_key_bearer_case_insensitive():
    headers = _headers(Authorization="bearer jpm_1_a")
    assert extract_key(headers) == "jpm_1_a"


def test_extract_key_bare_authorization_no_scheme():
    headers = _headers(Authorization="jpm_1_a")
    assert extract_key(headers) == "jpm_1_a"


def test_extract_key_missing_raises_401():
    with pytest.raises(JupiterError) as exc:
        extract_key(_headers())
    assert exc.value.status_code == 401
