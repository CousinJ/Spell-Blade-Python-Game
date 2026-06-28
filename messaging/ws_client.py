"""Client-side WebSocket transport for the pygame game loop.

A thin sync wrapper around ``websocket-client``'s :class:`WebSocketApp`, which
runs its own daemon thread and delivers frames via callbacks. That integrates
cleanly with the synchronous 60fps pygame loop: the game thread never blocks on
the socket — it reads the latest snapshot from a shared buffer and drains
lifecycle/attack queues each frame, and publishes input by calling ``send_*``.

This module is intentionally **pygame-free** so the same transport can be driven
by a headless test (see ``scripts/m5_smoke.py``).

Handshake & subscriptions (see plan "Channel hierarchy"):
  * on open: subscribe own ``client_inbox`` + publish ``join`` on the global lobby.
  * on ``joined``: learn ``matchId``/``actor``; subscribe the match ``snapshot``,
    ``lifecycle`` and per-match ``lobby`` channels, plus the *opponent's* input
    channel (to render their attack swings).
"""
from __future__ import annotations

import json
import queue
import threading
import uuid
from typing import Optional

from websocket import WebSocketApp

from messaging import channels
from messaging.schema import Envelope, MessageType


class GameClient:
    def __init__(self, url: str, client_id: Optional[str] = None) -> None:
        self.url = url
        self.client_id = client_id or uuid.uuid4().hex[:8]

        self.match_id: Optional[str] = None
        self.actor: Optional[str] = None
        self.opponent: Optional[str] = None
        self.opponent_hero: Optional[str] = None

        self._ws: Optional[WebSocketApp] = None
        self._thread: Optional[threading.Thread] = None

        self._lock = threading.Lock()
        self._snapshot: Optional[dict] = None
        self._snapshot_seq = -1
        self._lifecycle_q: "queue.Queue[dict]" = queue.Queue()
        self._attack_q: "queue.Queue[str]" = queue.Queue()
        self._client_seq = 0

        self.connected = threading.Event()
        self.joined = threading.Event()
        self.closed = threading.Event()

    # ----------------------------------------------------------- lifecycle
    def start(self) -> None:
        self._ws = WebSocketApp(
            self.url,
            on_open=self._on_open,
            on_message=self._on_message,
            on_close=self._on_close,
            on_error=self._on_error,
        )
        self._thread = threading.Thread(
            target=self._ws.run_forever,
            kwargs={"ping_interval": 20, "ping_timeout": 10},
            daemon=True,
        )
        self._thread.start()

    def wait_until_joined(self, timeout: float = 15.0) -> bool:
        return self.joined.wait(timeout)

    def close(self) -> None:
        if self._ws is not None:
            try:
                self._ws.close()
            except Exception:
                pass

    # --------------------------------------------------------- raw transport
    def _send(self, obj: dict) -> None:
        ws = self._ws
        if ws is None:
            return
        try:
            ws.send(json.dumps(obj, separators=(",", ":")))
        except Exception:
            pass

    def _sub(self, channel: str) -> None:
        self._send({"op": "subscribe", "channel": channel})

    def _pub(self, channel: str, env: Envelope) -> None:
        self._send({"op": "publish", "channel": channel, "message": env.to_dict()})

    # ----------------------------------------------------------- callbacks
    def _on_open(self, ws) -> None:
        self.connected.set()
        self._sub(channels.client_inbox(self.client_id))
        self._pub(
            channels.GLOBAL_LOBBY,
            Envelope(type=MessageType.JOIN, payload={"clientId": self.client_id}),
        )

    def _on_close(self, ws, *args) -> None:
        self.closed.set()

    def _on_error(self, ws, error) -> None:
        # Surface transport errors without crashing the render thread.
        print(f"[ws_client {self.client_id}] error: {error}")

    def _on_message(self, ws, raw) -> None:
        try:
            frame = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return
        if frame.get("op") != "message":
            return
        channel = frame.get("channel")
        msg = frame.get("message") or {}
        mtype = msg.get("type")
        payload = msg.get("payload") or {}

        if mtype == MessageType.JOINED:
            self._handle_joined(payload)
        elif mtype == MessageType.WORLD_SNAPSHOT:
            self._handle_snapshot(payload)
        elif mtype == MessageType.LIFECYCLE_EVENT:
            self._lifecycle_q.put(payload)
        elif mtype == MessageType.HERO_SELECT:
            if msg.get("actor") and msg.get("actor") != self.actor:
                self.opponent_hero = payload.get("hero")
        elif mtype == MessageType.ATTACK:
            # Only the opponent's input channel is subscribed for attacks.
            if msg.get("actor") and msg.get("actor") == self.opponent:
                action_id = payload.get("action_id")
                if action_id:
                    self._attack_q.put(action_id)

    def _handle_joined(self, payload: dict) -> None:
        self.match_id = payload.get("matchId")
        self.actor = payload.get("actor")
        self.opponent = "p2" if self.actor == "p1" else "p1"
        if self.match_id:
            self._sub(channels.snapshot(self.match_id))
            self._sub(channels.lifecycle(self.match_id))
            self._sub(channels.lobby(self.match_id))
            self._sub(channels.player_input(self.match_id, self.opponent))
        self.joined.set()

    def _handle_snapshot(self, payload: dict) -> None:
        seq = payload.get("seq", 0)
        with self._lock:
            if seq >= self._snapshot_seq:
                self._snapshot = payload
                self._snapshot_seq = seq

    # ------------------------------------------------------------- reads
    def latest_snapshot(self) -> Optional[dict]:
        with self._lock:
            return self._snapshot

    def poll_lifecycle(self) -> list[dict]:
        out: list[dict] = []
        while True:
            try:
                out.append(self._lifecycle_q.get_nowait())
            except queue.Empty:
                break
        return out

    def poll_opponent_attacks(self) -> list[str]:
        out: list[str] = []
        while True:
            try:
                out.append(self._attack_q.get_nowait())
            except queue.Empty:
                break
        return out

    # ------------------------------------------------------------- writes
    def _ready(self) -> bool:
        return bool(self.match_id and self.actor)

    def send_player_state(self, x, direction, moving, is_blocking, state) -> None:
        if not self._ready():
            return
        self._pub(
            channels.player_input(self.match_id, self.actor),
            Envelope(
                type=MessageType.PLAYER_STATE,
                match_id=self.match_id,
                actor=self.actor,
                payload={
                    "x": x,
                    "direction": direction,
                    "moving": moving,
                    "is_blocking": is_blocking,
                    "state": state,
                },
            ),
        )

    def send_attack(self, action_id: str) -> None:
        if not self._ready():
            return
        self._client_seq += 1
        self._pub(
            channels.player_input(self.match_id, self.actor),
            Envelope(
                type=MessageType.ATTACK,
                match_id=self.match_id,
                actor=self.actor,
                client_seq=self._client_seq,
                payload={"action_id": action_id},
            ),
        )

    def send_hero_select(self, hero: str) -> None:
        if not self._ready():
            return
        self._pub(
            channels.lobby(self.match_id),
            Envelope(
                type=MessageType.HERO_SELECT,
                match_id=self.match_id,
                actor=self.actor,
                payload={"hero": hero},
            ),
        )

    def send_assets_loaded(self) -> None:
        if not self._ready():
            return
        self._pub(
            channels.lobby(self.match_id),
            Envelope(
                type=MessageType.ASSETS_LOADED,
                match_id=self.match_id,
                actor=self.actor,
            ),
        )

    def send_rematch(self) -> None:
        if not self._ready():
            return
        self._pub(
            channels.lobby(self.match_id),
            Envelope(
                type=MessageType.REMATCH,
                match_id=self.match_id,
                actor=self.actor,
            ),
        )
