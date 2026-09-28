from jupiter_core.semantic import AnalysisClaim, fingerprint, validate_overlaps


def _claim(file_path, member_id, intent="editing", member="m", note=None):
    return AnalysisClaim(file_path=file_path, intent=intent, member=member, member_id=member_id, note=note)


def test_fingerprint_is_deterministic():
    claims = [_claim("a.py", 1), _claim("b.py", 2)]
    assert fingerprint(claims) == fingerprint(claims)


def test_fingerprint_order_independent():
    a = [_claim("a.py", 1), _claim("b.py", 2)]
    b = [_claim("b.py", 2), _claim("a.py", 1)]
    assert fingerprint(a) == fingerprint(b)


def test_fingerprint_differs_on_content_change():
    a = [_claim("a.py", 1)]
    b = [_claim("a.py", 2)]
    assert fingerprint(a) != fingerprint(b)


def test_fingerprint_length():
    assert len(fingerprint([_claim("a.py", 1)])) == 16


# --- validate_overlaps: the distrustful ladder ---

def _claims_ab():
    return [_claim("a.py", 1, member="alice"), _claim("b.py", 2, member="bob")]


def test_validate_overlaps_happy_path():
    claims = _claims_ab()
    reply = {"overlaps": [{"paths": ["a.py", "b.py"], "reason": "impl and test", "confidence": "high"}]}
    result = validate_overlaps(reply, claims)
    assert len(result) == 1
    assert result[0].paths == ["a.py", "b.py"]
    assert result[0].members == ["alice", "bob"]
    assert result[0].confidence == "high"


def test_validate_overlaps_drops_invented_path():
    claims = _claims_ab()
    reply = {"overlaps": [{"paths": ["a.py", "made_up.py"], "reason": "x", "confidence": "high"}]}
    # after dropping the invented path only one real path remains -> dropped
    assert validate_overlaps(reply, claims) == []


def test_validate_overlaps_requires_two_distinct_holders():
    claims = [_claim("a.py", 1, member="alice"), _claim("b.py", 1, member="alice")]
    reply = {"overlaps": [{"paths": ["a.py", "b.py"], "reason": "x", "confidence": "high"}]}
    assert validate_overlaps(reply, claims) == []


def test_validate_overlaps_requires_reason():
    claims = _claims_ab()
    reply = {"overlaps": [{"paths": ["a.py", "b.py"], "reason": "  ", "confidence": "high"}]}
    assert validate_overlaps(reply, claims) == []


def test_validate_overlaps_reason_truncated():
    claims = _claims_ab()
    long_reason = "x" * 500
    reply = {"overlaps": [{"paths": ["a.py", "b.py"], "reason": long_reason, "confidence": "high"}]}
    result = validate_overlaps(reply, claims)
    assert len(result[0].reason) == 240


def test_validate_overlaps_bad_confidence_defaults_medium():
    claims = _claims_ab()
    reply = {"overlaps": [{"paths": ["a.py", "b.py"], "reason": "x", "confidence": "nonsense"}]}
    result = validate_overlaps(reply, claims)
    assert result[0].confidence == "medium"


def test_validate_overlaps_dedupes_by_path_set():
    claims = _claims_ab()
    reply = {
        "overlaps": [
            {"paths": ["a.py", "b.py"], "reason": "first", "confidence": "high"},
            {"paths": ["b.py", "a.py"], "reason": "duplicate, different order", "confidence": "low"},
        ]
    }
    result = validate_overlaps(reply, claims)
    assert len(result) == 1
    assert result[0].reason == "first"


def test_validate_overlaps_caps_at_max():
    claims = [_claim(f"f{i}.py", i, member=f"m{i}") for i in range(20)]
    overlaps = [{"paths": [f"f{i}.py", f"f{i+1}.py"], "reason": "x", "confidence": "high"} for i in range(19)]
    reply = {"overlaps": overlaps}
    result = validate_overlaps(reply, claims)
    assert len(result) == 8


def test_validate_overlaps_ignores_non_list_overlaps():
    assert validate_overlaps({"overlaps": "not a list"}, _claims_ab()) == []


def test_validate_overlaps_ignores_missing_overlaps_key():
    assert validate_overlaps({}, _claims_ab()) == []


def test_validate_overlaps_same_person_group_dropped():
    """A group where every claim belongs to the same person is not a real overlap."""
    claims = [_claim("a.py", 1, member="alice"), _claim("b.py", 1, member="alice")]
    reply = {"overlaps": [{"paths": ["a.py", "b.py"], "reason": "same person", "confidence": "high"}]}
    assert validate_overlaps(reply, claims) == []


def test_validate_overlaps_single_path_dropped():
    claims = _claims_ab()
    reply = {"overlaps": [{"paths": ["a.py"], "reason": "x", "confidence": "high"}]}
    assert validate_overlaps(reply, claims) == []


def test_validate_overlaps_malformed_item_skipped():
    claims = _claims_ab()
    reply = {"overlaps": ["not a dict", {"paths": ["a.py", "b.py"], "reason": "x", "confidence": "high"}]}
    result = validate_overlaps(reply, claims)
    assert len(result) == 1
