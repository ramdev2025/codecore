import pytest

from jupiter_core.errors import JupiterError
from jupiter_core.paths import normalize_path


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("src/payments.ts", "src/payments.ts"),
        ("src\\payments.ts", "src/payments.ts"),
        ("src//payments.ts", "src/payments.ts"),
        ("src/../src/payments.ts", "src/payments.ts"),
        ("./a.py", "a.py"),
        ("./src/a.py", "src/a.py"),
        ("src/a.py/", "src/a.py"),
        ("  src/a.py  ", "src/a.py"),
        ("/abs/path.py", "/abs/path.py"),
        ("/abs/../path.py", "/path.py"),
        ("/../escape.py", "/escape.py"),
        ("../above.py", "../above.py"),
        ("a/../../b.py", "../b.py"),
        ("src/App.py", "src/App.py"),  # case preserved
    ],
)
def test_normalize_path_examples(raw, expected):
    assert normalize_path(raw) == expected


def test_normalize_path_empty_raises():
    with pytest.raises(JupiterError) as exc:
        normalize_path("   ")
    assert exc.value.status_code == 422
    assert "must not be empty" in exc.value.message


def test_normalize_path_dot_only_raises():
    with pytest.raises(JupiterError):
        normalize_path(".")


def test_normalize_path_too_long_raises():
    with pytest.raises(JupiterError) as exc:
        normalize_path("a" * 1025)
    assert exc.value.status_code == 422


def test_normalize_path_control_chars_rejected():
    with pytest.raises(JupiterError) as exc:
        normalize_path("src/\x00payments.ts")
    assert exc.value.status_code == 422
    assert "control characters" in exc.value.message


def test_normalize_path_nfc_normalizes():
    # 'e' + combining acute (NFD) -> should equal precomposed 'é' (NFC) form.
    decomposed = "café.py"
    precomposed = "café.py"
    assert normalize_path(decomposed) == normalize_path(precomposed) == precomposed
