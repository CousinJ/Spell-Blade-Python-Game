"""Versioned message envelope + pluggable codec.

EIP — **Message Translator**: converts between in-memory domain objects/dicts and
the versioned JSON wire format, so components never exchange raw/pickled objects.

GoF — **Strategy**: :class:`Codec` is the strategy interface and :class:`JsonCodec`
the default concrete strategy; the wire format can be swapped without touching any
call site (which only use :func:`encode` / :func:`decode`).
"""
from __future__ import annotations

import json
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional

PROTOCOL_VERSION = 1


class MessageType:
    """Canonical ``type`` values for the domain envelope (see plan schema)."""

    # client -> server (lobby / input)
    JOIN = "join"
    HERO_SELECT = "hero_select"
    ASSETS_LOADED = "assets_loaded"
    PLAYER_STATE = "player_state"
    ATTACK = "attack"
    REMATCH = "rematch"
    # server -> client
    JOINED = "joined"
    WORLD_SNAPSHOT = "world_snapshot"
    LIFECYCLE_EVENT = "lifecycle_event"
    ERROR = "error"


class SchemaError(ValueError):
    """Raised when a frame/envelope fails validation or the version check."""


@dataclass
class Envelope:
    """The common message envelope wrapping every domain message.

    Wire shape: ``{v, type, matchId, actor, client_seq, ts, payload}``.
    """

    type: str
    payload: dict[str, Any] = field(default_factory=dict)
    match_id: Optional[str] = None
    actor: Optional[str] = None
    client_seq: Optional[int] = None
    ts: float = field(default_factory=time.time)
    v: int = PROTOCOL_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "v": self.v,
            "type": self.type,
            "matchId": self.match_id,
            "actor": self.actor,
            "client_seq": self.client_seq,
            "ts": self.ts,
            "payload": self.payload,
        }

    @classmethod
    def from_dict(cls, d: Any) -> "Envelope":
        if not isinstance(d, dict):
            raise SchemaError("envelope must be a JSON object")
        v = d.get("v")
        if v != PROTOCOL_VERSION:
            raise SchemaError(f"unsupported protocol version: {v!r}")
        mtype = d.get("type")
        if not isinstance(mtype, str) or not mtype:
            raise SchemaError("missing or invalid 'type'")
        payload = d.get("payload") or {}
        if not isinstance(payload, dict):
            raise SchemaError("'payload' must be an object")
        return cls(
            type=mtype,
            payload=payload,
            match_id=d.get("matchId"),
            actor=d.get("actor"),
            client_seq=d.get("client_seq"),
            ts=d.get("ts", time.time()),
            v=v,
        )


class Codec(ABC):
    """Strategy interface for (de)serializing envelopes to/from the wire."""

    @abstractmethod
    def encode(self, env: Envelope) -> str: ...

    @abstractmethod
    def decode(self, text: str) -> Envelope: ...


class JsonCodec(Codec):
    """Default concrete strategy: compact JSON."""

    def encode(self, env: Envelope) -> str:
        return json.dumps(env.to_dict(), separators=(",", ":"))

    def decode(self, text: str) -> Envelope:
        try:
            d = json.loads(text)
        except (json.JSONDecodeError, TypeError) as e:
            raise SchemaError(f"invalid JSON: {e}") from e
        return Envelope.from_dict(d)


DEFAULT_CODEC: Codec = JsonCodec()


def encode(env: Envelope, codec: Codec = DEFAULT_CODEC) -> str:
    return codec.encode(env)


def decode(text: str, codec: Codec = DEFAULT_CODEC) -> Envelope:
    return codec.decode(text)
