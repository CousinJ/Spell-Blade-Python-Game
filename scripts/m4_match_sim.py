"""M4 end-to-end: two simulated players over WebSockets drive a full match.

Verifies the milestone "Done when":
  * a full LOBBY -> ... -> MATCH_OVER run happens over the real WS transport,
  * damage + transition events land in SQLite (read back via HTTP),
  * /matches and /matches/{id}/events return live data.

No pygame / no game client involved.

Usage (server must be running, e.g. python -m coordinator.run_server):
    python scripts/m4_match_sim.py
"""
import json
import os
import sys
import threading
import time
import urllib.request
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from websocket import create_connection  # noqa: E402

from messaging import channels  # noqa: E402

WS_URL = "ws://localhost:8000/ws"
HTTP_URL = "http://localhost:8000"
GLOBAL = channels.GLOBAL_LOBBY


def env(mtype, match_id=None, actor=None, client_seq=None, payload=None):
    return {
        "v": 1, "type": mtype, "matchId": match_id, "actor": actor,
        "client_seq": client_seq, "ts": time.time(), "payload": payload or {},
    }


class Player(threading.Thread):
    def __init__(self, hero, attacker, x, direction):
        super().__init__(daemon=True)
        self.hero = hero
        self.attacker = attacker
        self.x = x
        self.direction = direction
        self.client_id = uuid.uuid4().hex[:8]
        self.match_id = None
        self.actor = None
        self.phase = "LOBBY"
        self.error = None
        self._seq = 0
        self.done = threading.Event()

    def _pub(self, channel, e):
        self.ws.send(json.dumps({"op": "publish", "channel": channel, "message": e}))

    def _sub(self, channel):
        self.ws.send(json.dumps({"op": "subscribe", "channel": channel}))

    def _send_state(self):
        self._pub(
            channels.player_input(self.match_id, self.actor),
            env("player_state", self.match_id, self.actor,
                payload={"x": self.x, "direction": self.direction, "is_blocking": False, "state": "idle"}),
        )

    def run(self):
        try:
            self.ws = create_connection(WS_URL, timeout=5)
            self._sub(channels.client_inbox(self.client_id))
            self.ws.settimeout(0.2)
            self._pub(GLOBAL, env("join", payload={"clientId": self.client_id}))

            last_attack = 0.0
            deadline = time.time() + 25
            while not self.done.is_set() and time.time() < deadline:
                try:
                    raw = self.ws.recv()
                except Exception:
                    raw = None
                if raw:
                    self._handle(raw)
                if self.phase == "FIGHTING" and self.match_id and self.actor:
                    self._send_state()
                    if self.attacker and time.time() - last_attack > 0.08:
                        self._seq += 1
                        self._pub(
                            channels.player_input(self.match_id, self.actor),
                            env("attack", self.match_id, self.actor, self._seq,
                                {"action_id": "fire_strike"}),
                        )
                        last_attack = time.time()
                if self.phase == "MATCH_OVER":
                    self.done.set()
            self.ws.close()
        except Exception as exc:  # noqa: BLE001
            self.error = exc

    def _handle(self, raw):
        try:
            frame = json.loads(raw)
        except json.JSONDecodeError:
            return
        if frame.get("op") != "message":
            return
        msg = frame.get("message", {})
        mtype = msg.get("type")
        payload = msg.get("payload", {})

        if mtype == "joined":
            self.match_id = payload["matchId"]
            self.actor = payload["actor"]
            self._sub(channels.snapshot(self.match_id))
            self._sub(channels.lifecycle(self.match_id))
            self._pub(channels.lobby(self.match_id),
                      env("hero_select", self.match_id, self.actor, payload={"hero": self.hero}))
            self._pub(channels.lobby(self.match_id),
                      env("assets_loaded", self.match_id, self.actor))
        elif mtype == "lifecycle_event":
            self.phase = payload.get("to", self.phase)


def http_get(path):
    with urllib.request.urlopen(HTTP_URL + path, timeout=5) as r:
        return json.loads(r.read())


def main() -> int:
    # attacker on the left facing right; defender just to the right, in reach.
    attacker = Player("FireChar", attacker=True, x=300.0, direction=1)
    defender = Player("IceChar", attacker=False, x=400.0, direction=-1)

    attacker.start()
    time.sleep(0.3)  # make the attacker join first (p1)
    defender.start()

    deadline = time.time() + 25
    while time.time() < deadline and not (attacker.done.is_set() and defender.done.is_set()):
        time.sleep(0.2)

    for p in (attacker, defender):
        if p.error:
            raise SystemExit(f"{p.hero} thread error: {p.error}")

    assert attacker.phase == "MATCH_OVER", f"attacker phase = {attacker.phase}"
    assert defender.phase == "MATCH_OVER", f"defender phase = {defender.phase}"

    match_id = attacker.match_id
    assert match_id and match_id == defender.match_id

    matches = http_get("/matches")["matches"]
    assert any(m["matchId"] == match_id for m in matches), matches

    events = http_get(f"/matches/{match_id}/events")["events"]
    types = [e["type"] for e in events]
    assert "join" in types and "hero_select" in types, types
    assert types.count("damage") >= 4, f"expected >=4 damage events, got {types.count('damage')}"
    assert any(e["type"] == "transition" and e["payload"].get("to") == "MATCH_OVER" for e in events)

    summary = next(m for m in matches if m["matchId"] == match_id)
    print(f"M4 sim PASS: match {match_id} -> {summary['phase']}")
    print(f"  events: {len(events)} persisted "
          f"({types.count('damage')} damage, {types.count('transition')} transitions)")
    print(f"  final: {json.dumps(summary['players'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
