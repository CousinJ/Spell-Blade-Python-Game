"""Coordinator disconnect handling (lobby robustness).

Verifies that a dropped WebSocket connection is turned into a clean outcome:

  * mid-match disconnect  -> opponent wins by forfeit (PLAYER_LEFT -> MATCH_OVER),
  * waiting-alone disconnect -> the pending match is discarded (no "ghost"),
  * post-match disconnect  -> no-op (the normal reconnect-to-lobby path),

plus the channel parser the WS endpoint uses to tie a connection to its client.

    python tests/test_disconnect.py
    pytest tests/test_disconnect.py
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from audit.event_store import EventStore  # noqa: E402
from coordinator.lifecycle import State  # noqa: E402
from coordinator.match_coordinator import MatchCoordinator  # noqa: E402
from messaging import bus, channels  # noqa: E402
from messaging.pubsub import PubSubHub  # noqa: E402
from messaging.schema import Envelope, MessageType  # noqa: E402


async def _coordinator():
    hub = PubSubHub()
    coord = MatchCoordinator(hub, EventStore(":memory:"), rounds_to_win=1, tick_interval=100.0)
    await coord.start()

    async def pub(channel, env):
        await hub.publish(channel, bus.message_frame(channel, env))

    return coord, pub


async def _join(pub, client_id):
    await pub(channels.GLOBAL_LOBBY, Envelope(type=MessageType.JOIN, payload={"clientId": client_id}))


def test_channel_parser_roundtrip():
    ch = channels.client_inbox("abc123")
    assert channels.client_id_from_inbox(ch) == "abc123"
    assert channels.client_id_from_inbox(channels.GLOBAL_LOBBY) is None
    assert channels.client_id_from_inbox("spellblade/v1/M1/snapshot") is None


def test_waiting_disconnect_discards_pending_match():
    async def main():
        coord, pub = await _coordinator()
        await _join(pub, "c1")  # alone in a pending match (LOBBY)
        mc = next(iter(coord._matches.values()))
        assert mc.machine.state == State.LOBBY

        await coord.on_disconnect("c1")
        # The ghost match is gone and the pending slot is cleared, so the next
        # joiner starts a brand-new match instead of pairing with a ghost.
        assert coord._matches == {}
        assert coord._pending is None
    asyncio.run(main())


def test_midmatch_disconnect_forfeits_to_opponent():
    async def main():
        coord, pub = await _coordinator()
        await _join(pub, "c1")
        await _join(pub, "c2")  # pairs -> CHARACTER_SELECT (active)
        mc = next(iter(coord._matches.values()))
        assert mc.machine.state == State.CHARACTER_SELECT
        loser = "p1"
        winner = mc.opponent(loser)

        await coord.on_disconnect("c1")  # p1 drops
        assert mc.machine.state == State.MATCH_OVER
        assert mc.state.winner == winner
        assert not mc.state.players[loser].alive
    asyncio.run(main())


def test_postmatch_disconnect_is_noop():
    async def main():
        coord, pub = await _coordinator()
        await _join(pub, "c1")
        await _join(pub, "c2")
        mc = next(iter(coord._matches.values()))
        # Force the terminal state, as the normal reconnect-to-lobby path would.
        mc.machine.state = State.MATCH_OVER
        await coord.on_disconnect("c1")  # should not raise or change anything
        assert mc.machine.state == State.MATCH_OVER

        # Unknown client id is also a safe no-op.
        await coord.on_disconnect("nobody")
    asyncio.run(main())


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
    print(f"disconnect: {'all tests passed' if not failures else f'{failures} FAILED'}")
    sys.exit(1 if failures else 0)
