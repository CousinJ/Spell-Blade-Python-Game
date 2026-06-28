"""Unit tests for the message envelope + codec (Message Translator / Strategy).

Runnable two ways:
    python tests/test_schema.py        # standalone
    pytest tests/test_schema.py        # if pytest installed
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from messaging.schema import (  # noqa: E402
    Envelope,
    JsonCodec,
    MessageType,
    SchemaError,
    decode,
    encode,
)


def test_round_trip_full():
    env = Envelope(
        type=MessageType.ATTACK,
        payload={"action_id": "fire_strike"},
        match_id="m-123",
        actor="p1",
        client_seq=7,
    )
    assert decode(encode(env)) == env


def test_round_trip_minimal():
    env = Envelope(type=MessageType.JOIN)
    back = decode(encode(env))
    assert back == env
    assert back.payload == {}


def test_version_rejected():
    try:
        decode('{"v":99,"type":"join","payload":{}}')
    except SchemaError:
        return
    raise AssertionError("expected SchemaError for bad version")


def test_missing_type_rejected():
    try:
        decode('{"v":1,"payload":{}}')
    except SchemaError:
        return
    raise AssertionError("expected SchemaError for missing type")


def test_invalid_json_rejected():
    try:
        decode("not json at all")
    except SchemaError:
        return
    raise AssertionError("expected SchemaError for invalid json")


def test_non_object_payload_rejected():
    try:
        decode('{"v":1,"type":"attack","payload":[1,2,3]}')
    except SchemaError:
        return
    raise AssertionError("expected SchemaError for non-object payload")


def test_strategy_explicitly_swappable():
    codec = JsonCodec()
    env = Envelope(type=MessageType.PLAYER_STATE, payload={"x": 100})
    assert decode(encode(env, codec), codec) == env


if __name__ == "__main__":
    failures = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("PASS", name)
            except AssertionError as e:
                failures += 1
                print("FAIL", name, "-", e)
    print(f"schema: {'all tests passed' if not failures else f'{failures} FAILED'}")
    sys.exit(1 if failures else 0)
