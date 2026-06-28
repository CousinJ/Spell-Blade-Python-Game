"""FastAPI app: WebSocket pub/sub transport + Match Coordinator + audit HTTP.

The single web service hosts:
  * ``WebSocket /ws`` — the publish/subscribe transport (and, via the coordinator
    inbox subscribed to the inbound channels, the entry point for gameplay).
  * ``GET /health``               — liveness + active match count.
  * ``GET /matches``              — live matches and their phase/players.
  * ``GET /matches/{id}/events``  — the raw audit log (point-in-time history).

WebSocket frame protocol (JSON text frames):
    client -> server:
        {"op": "subscribe",   "channel": "<key>"}
        {"op": "unsubscribe", "channel": "<key>"}
        {"op": "publish",     "channel": "<key>", "message": <envelope dict>}
    server -> client:
        {"op": "subscribed",  "channel": "<key>"}
        {"op": "message",     "channel": "<key>", "message": <envelope dict>}
        {"op": "error",       "error": "<reason>"}
"""
from __future__ import annotations

import itertools
import json
import os
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect

from audit.event_store import EventStore
from coordinator.match_coordinator import MatchCoordinator
from messaging import bus
from messaging.pubsub import PubSubHub
from messaging.schema import Envelope, SchemaError

hub = PubSubHub()
store = EventStore(os.environ.get("DB_PATH", "audit.db"))
coordinator = MatchCoordinator(
    hub, store, rounds_to_win=int(os.environ.get("ROUNDS_TO_WIN", "1"))
)

_START = time.time()
_conn_ids = itertools.count(1)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await coordinator.start()
    yield
    store.close()


app = FastAPI(title="Spell Blade Match Coordinator", lifespan=lifespan)


class WsSubscriber:
    """Adapts a FastAPI WebSocket to the hub's ``Subscriber`` protocol."""

    def __init__(self, ws: WebSocket, sub_id: str) -> None:
        self._ws = ws
        self.id = sub_id

    async def send(self, text: str) -> None:
        await self._ws.send_text(text)

    def __hash__(self) -> int:
        return hash(self.id)

    def __eq__(self, other: object) -> bool:
        return isinstance(other, WsSubscriber) and other.id == self.id


# ---------------------------------------------------------------- HTTP routes
@app.get("/health")
async def health() -> dict:
    return {
        "status": "ok",
        "uptime_s": round(time.time() - _START, 1),
        "channels": len(hub.channels()),
        "matches": len(coordinator.match_summaries()),
    }


@app.get("/matches")
async def matches() -> dict:
    return {"matches": coordinator.match_summaries()}


@app.get("/matches/{match_id}/events")
async def match_events(match_id: str, upto: int | None = None) -> dict:
    return {"match_id": match_id, "events": coordinator.events_for(match_id, upto)}


# ------------------------------------------------------------- WebSocket /ws
@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket) -> None:
    await ws.accept()
    sub = WsSubscriber(ws, f"conn-{next(_conn_ids)}")
    try:
        while True:
            raw = await ws.receive_text()
            await _handle_frame(sub, raw)
    except WebSocketDisconnect:
        pass
    finally:
        await hub.unsubscribe_all(sub)


async def _handle_frame(sub: WsSubscriber, raw: str) -> None:
    try:
        frame = json.loads(raw)
        op = frame.get("op")
    except (json.JSONDecodeError, AttributeError):
        return await _send(sub, {"op": "error", "error": "malformed frame"})

    channel = frame.get("channel")
    if op in ("subscribe", "unsubscribe", "publish") and not channel:
        return await _send(sub, {"op": "error", "error": f"'{op}' requires 'channel'"})

    if op == "subscribe":
        await hub.subscribe(channel, sub)
        await _send(sub, {"op": "subscribed", "channel": channel})
    elif op == "unsubscribe":
        await hub.unsubscribe(channel, sub)
    elif op == "publish":
        try:
            env = Envelope.from_dict(frame.get("message") or {})
        except SchemaError as e:
            return await _send(sub, {"op": "error", "error": f"invalid message: {e}"})
        await hub.publish(channel, bus.message_frame(channel, env))
    else:
        await _send(sub, {"op": "error", "error": f"unknown op: {op!r}"})


async def _send(sub: WsSubscriber, obj: dict) -> None:
    await sub.send(json.dumps(obj, separators=(",", ":")))
