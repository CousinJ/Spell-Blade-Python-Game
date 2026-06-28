"""M1 end-to-end smoke test: two ``websocket-client`` connections, fan-out via the hub.

This is the milestone's "Done when" check: a publish from connection A is fanned
out to subscriber B through a locally-running coordinator.

Usage:
    # terminal 1
    python -m coordinator.run_server
    # terminal 2
    python scripts/m1_ws_smoke.py            # connects to ws://localhost:8000/ws

The script retries the initial connection for a few seconds so it can be started
immediately after (or just before) the server.
"""
import json
import sys
import time

from websocket import create_connection

URL = "ws://localhost:8000/ws"
CHANNEL = "spellblade/v1/SMOKE/snapshot"


def connect(url: str, attempts: int = 40):
    last = None
    for _ in range(attempts):
        try:
            return create_connection(url, timeout=5)
        except Exception as e:  # noqa: BLE001 - server may not be up yet
            last = e
            time.sleep(0.25)
    raise SystemExit(f"could not connect to {url}: {last}")


def main() -> int:
    a = connect(URL)
    b = connect(URL)
    try:
        # B subscribes and waits for the ack so the subscription is registered
        # before A publishes (deterministic, no sleeps).
        b.send(json.dumps({"op": "subscribe", "channel": CHANNEL}))
        ack = json.loads(b.recv())
        assert ack.get("op") == "subscribed" and ack.get("channel") == CHANNEL, ack

        msg = {
            "v": 1,
            "type": "world_snapshot",
            "matchId": "SMOKE",
            "actor": None,
            "client_seq": None,
            "ts": time.time(),
            "payload": {"hello": "world"},
        }
        a.send(json.dumps({"op": "publish", "channel": CHANNEL, "message": msg}))

        b.settimeout(5)
        frame = json.loads(b.recv())
        assert frame.get("op") == "message", frame
        assert frame["channel"] == CHANNEL, frame
        assert frame["message"]["payload"] == {"hello": "world"}, frame
        print("M1 smoke PASS: publish from A fanned out to subscriber B")
        return 0
    finally:
        a.close()
        b.close()


if __name__ == "__main__":
    sys.exit(main())
