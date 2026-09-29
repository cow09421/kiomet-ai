import json

import pytest

from kiomet_ai.reason_taxonomy import (
    REASON_CODES,
    REASON_METADATA,
    SCHEMA_VERSION,
    UNKNOWN,
    build_reason_record,
    classify_no_action_reason,
    serialize_reason_record,
)


def test_declared_taxonomy_has_all_canonical_reasons_and_metadata():
    assert REASON_CODES == (
        "NO_ENEMY", "NO_THREAT", "STALE_WORLD", "UNKNOWN_OWNER",
        "UNSUPPORTED_BATTLE", "SOURCE_UNSAFE", "INSUFFICIENT_FORCE",
        "ETA_UNKNOWN", "MULTI_THREAT_UNRESOLVED", "TOKEN_STALE",
        "RESERVATION_CONFLICT", "RECOVERY_ACTIVE", "NOT_IN_MATCH",
        "AUTHORIZATION_DISABLED",
    )
    assert set(REASON_CODES) <= set(REASON_METADATA)
    assert all(isinstance(REASON_METADATA[code], str)
               and REASON_METADATA[code] for code in REASON_CODES)


@pytest.mark.parametrize(
    ("raw_reason", "expected"),
    [
        ("not_in_match", "NOT_IN_MATCH"),
        ("autonomy_paused", "AUTHORIZATION_DISABLED"),
        ("no-known-threats", "NO_THREAT"),
        ("SOURCE_WOULD_BECOME_UNSAFE", "SOURCE_UNSAFE"),
        ("RESOURCE_RESERVED:source", "RESERVATION_CONFLICT"),
        ("STALE_PROPOSAL:cycle-changed", "TOKEN_STALE"),
        ("threat-eta-unknown", "ETA_UNKNOWN"),
        ("mirror-unsupported", "UNSUPPORTED_BATTLE"),
    ],
)
def test_only_explicit_aliases_are_classified(raw_reason, expected):
    assert classify_no_action_reason(raw_reason) == expected


@pytest.mark.parametrize(
    "raw_reason",
    [
        "OTHER_REASON",
        "prefix-not_in_match-suffix",
        "not_in_match ",
        "Not_In_Match",
        "PVP_ARBITRATION_ATTACK_ENEMY",
        "NO_SAFE_PROPOSAL",
    ],
)
def test_unknown_strings_are_not_guessed(raw_reason):
    assert classify_no_action_reason(raw_reason) == UNKNOWN
    record = build_reason_record(raw_reason)
    assert record["code"] == UNKNOWN
    assert record["raw_reason"] == raw_reason
    assert record["known"] is False


@pytest.mark.parametrize("raw_reason", [None, 0, True, [], {}, object()])
def test_malformed_inputs_fail_closed_without_string_coercion(raw_reason):
    assert classify_no_action_reason(raw_reason) == UNKNOWN
    record = build_reason_record(raw_reason)
    assert record["code"] == UNKNOWN
    assert record["raw_reason"] is None
    assert record["known"] is False


def test_reason_record_schema_and_serialization_are_deterministic():
    first = build_reason_record("not_in_match")
    second = build_reason_record("not_in_match")
    assert first == second
    assert list(first) == [
        "schema_version", "code", "known", "raw_reason", "description",
    ]
    assert first == {
        "schema_version": SCHEMA_VERSION,
        "code": "NOT_IN_MATCH",
        "known": True,
        "raw_reason": "not_in_match",
        "description": REASON_METADATA["NOT_IN_MATCH"],
    }

    serialized = serialize_reason_record("not_in_match")
    assert serialized == serialize_reason_record("not_in_match")
    assert json.loads(serialized) == first
    assert "目前不在對局中" in serialized
