"""M5 headless end-to-end: two real ``GameClient`` transports play a full match.

This exercises the *actual* client networking layer used by ``client.py``
(``messaging.ws_client.GameClient``) — join handshake, channel subscriptions,
snapshot buffer, lifecycle/attack queues, and the ``send_*`` publishers — driving
a complete LOBBY -> CHARACTER_SELECT -> LOADING -> FIGHTING -> MATCH_OVER run
without pygame or a display.

It mirrors how ``client.py`` reacts to lifecycle events, so a pass means the
pygame client's transport contract is correct. Pygame rendering itself still
needs the manual two-window run (see README).

Usage (server must be running, e.g. `python -m coordinator.run_server`):
    python scripts/m5_smoke.py
"""
import os
import sys
import threading
import time
import urllib.request
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from messaging.ws_client import GameClient  # noqa: E402

WS_URL = os.environ.get("SPELLBLADE_WS_URL", "ws://localhost:8000/ws")
HTTP_URL = os.environ.get("SPELLBLADE_HTTP_URL", "http://localhost:8000")


class Driver(threading.Thread):
    """Drives one GameClient through the match, reacting to lifecycle like client.py."""

    def __init__(self, hero, attacker, x):
        super().__init__(daemon=True)
        self.hero = hero
        self.attacker = attacker
        self.x = x
        self.direction = 1 if attacker else -1
        self.gc = GameClient(WS_URL)
        self.phase = "LOBBY"
        self.error = None
        self.saw_snapshot = False
        self.done = threading.Event()

    def run(self):
        try:
            self.gc.start()
            if not self.gc.wait_until_joined(timeout=10):
                raise RuntimeError("never joined")

            last_attack = 0.0
            deadline = time.time() + 25
            while not self.done.is_set() and time.time() < deadline:
                for ev in self.gc.poll_lifecycle():
                    self._on_phase(ev.get("to"))

                if self.gc.latest_snapshot() is not None:
                    self.saw_snapshot = True

                if self.phase == "FIGHTING":
                    self.gc.send_player_state(
                        self.x, self.direction, False, False, "idle"
                    )
                    if self.attacker and time.time() - last_attack > 0.1:
                        self.gc.send_attack("strike_2")
                        last_attack = time.time()

                if self.phase == "MATCH_OVER":
                    self.done.set()
                time.sleep(0.02)
            self.gc.close()
        except Exception as exc:  # noqa: BLE001
            self.error = exc

    def _on_phase(self, to):
        if not to:
            return
        self.phase = to
        if to == "CHARACTER_SELECT":
            self.gc.send_hero_select(self.hero)
        elif to == "LOADING":
            self.gc.send_assets_loaded()


def http_get(path):
    with urllib.request.urlopen(HTTP_URL + path, timeout=5) as r:
        return json.loads(r.read())


def main() -> int:
    attacker = Driver("FireChar", attacker=True, x=300.0)
    defender = Driver("IceChar", attacker=False, x=400.0)

    attacker.start()
    time.sleep(0.3)  # ensure the attacker joins first -> becomes p1
    defender.start()

    deadline = time.time() + 25
    while time.time() < deadline and not (attacker.done.is_set() and defender.done.is_set()):
        time.sleep(0.1)

    for d in (attacker, defender):
        if d.error:
            raise SystemExit(f"{d.hero} driver error: {d.error}")

    assert attacker.phase == "MATCH_OVER", f"attacker phase = {attacker.phase}"
    assert defender.phase == "MATCH_OVER", f"defender phase = {defender.phase}"
    assert attacker.saw_snapshot and defender.saw_snapshot, "no world snapshots received"

    match_id = attacker.gc.match_id
    assert match_id and match_id == defender.gc.match_id, (match_id, defender.gc.match_id)
    assert {attacker.gc.actor, defender.gc.actor} == {"p1", "p2"}

    # Each client learned the opponent's hero off the lobby channel.
    assert attacker.gc.opponent_hero == "IceChar", attacker.gc.opponent_hero
    assert defender.gc.opponent_hero == "FireChar", defender.gc.opponent_hero

    # The final snapshot names the winner (the attacker).
    final = attacker.gc.latest_snapshot()
    assert final and final.get("winner") == attacker.gc.actor, final

    events = http_get(f"/matches/{match_id}/events")["events"]
    types = [e["type"] for e in events]
    assert "hero_select" in types and "join" in types, types
    assert types.count("damage") >= 4, f"expected >=4 damage events, got {types.count('damage')}"
    assert any(e["type"] == "transition" and e["payload"].get("to") == "MATCH_OVER" for e in events)

    print(f"M5 smoke PASS: match {match_id}")
    print(f"  actors: attacker={attacker.gc.actor}, defender={defender.gc.actor}")
    print(f"  winner: {final.get('winner')}  | snapshots received by both clients")
    print(f"  events: {len(events)} persisted ({types.count('damage')} damage)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
