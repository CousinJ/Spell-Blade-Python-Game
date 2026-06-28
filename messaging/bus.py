"""Wire-frame helpers shared by the WS endpoint and the coordinator.

A published domain message travels as a transport frame:
    {"op": "message", "channel": "<key>", "message": <envelope dict>}
"""
from __future__ import annotations

import json
from typing import Optional, Tuple

from messaging.schema import Envelope, SchemaError


def message_frame(channel: str, env: Envelope) -> str:
    return json.dumps(
        {"op": "message", "channel": channel, "message": env.to_dict()},
        separators=(",", ":"),
    )


def parse_message_frame(raw: str) -> Optional[Tuple[str, Envelope]]:
    """Return ``(channel, Envelope)`` if ``raw`` is an op=message frame, else None."""
    try:
        d = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(d, dict) or d.get("op") != "message":
        return None
    channel = d.get("channel")
    if not channel:
        return None
    try:
        env = Envelope.from_dict(d.get("message") or {})
    except SchemaError:
        return None
    return channel, env
