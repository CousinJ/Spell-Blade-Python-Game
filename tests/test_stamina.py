"""Coordinator stamina + parry tests.

Drives a real ``MatchCoordinator`` over an in-process ``PubSubHub`` (the same
path the WebSocket endpoint uses) through join -> select -> load -> FIGHTING,
then verifies:

  * an attack deducts the attacker's stamina by the action's cost,
  * an attack the attacker can't afford is rejected (no swing, no deduction),
  * a blocked hit drains the defender's stamina and bumps ``blocks_taken``
    (the signal the client uses to play the parry animation).

A large ``tick_interval`` keeps the per-tick stamina regen from interfering.

    python tests/test_stamina.py
    pytest tests/test_stamina.py
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from audit.event_store import EventStore  # noqa: E402
from coordinator import action_data  # noqa: E402
from coordinator.match_coordinator import MatchCoordinator  # noqa: E402
from messaging import bus, channels  # noqa: E402
from messaging.pubsub import PubSubHub  # noqa: E402
from messaging.schema import Envelope, MessageType  # noqa: E402


async def _start_fighting_match():
    """Return (coordinator, match_context, publish_fn) with the match in FIGHTING."""
    hub = PubSubHub()
    store = EventStore(":memory:")
    # Large tick so the snapshot loop's stamina regen doesn't fire mid-test.
    coord = MatchCoordinator(hub, store, rounds_to_win=1, tick_interval=100.0)
    await coord.start()

    async def pub(channel, env):
        await hub.publish(channel, bus.message_frame(channel, env))

    await pub(channels.GLOBAL_LOBBY, Envelope(type=MessageType.JOIN, payload={"clientId": "c1"}))
    await pub(channels.GLOBAL_LOBBY, Envelope(type=MessageType.JOIN, payload={"clientId": "c2"}))
    mc = next(iter(coord._matches.values()))
    mid = mc.match_id

    for actor, hero in (("p1", "FireChar"), ("p2", "IceChar")):
        await pub(channels.lobby(mid),
                  Envelope(type=MessageType.HERO_SELECT, match_id=mid, actor=actor, payload={"hero": hero}))
    for actor in ("p1", "p2"):
        await pub(channels.lobby(mid),
                  Envelope(type=MessageType.ASSETS_LOADED, match_id=mid, actor=actor))

    assert mc.machine.state == "FIGHTING", mc.machine.state
    return coord, mc, pub, mid


async def _set_positions(pub, mid, *, p2_blocking=False):
    # p1 at 300 facing right; p2 at 400 facing left -> dx 100, within reach.
    await pub(channels.player_input(mid, "p1"),
              Envelope(type=MessageType.PLAYER_STATE, match_id=mid, actor="p1",
                       payload={"x": 300.0, "direction": 1, "is_blocking": False, "state": "idle"}))
    await pub(channels.player_input(mid, "p2"),
              Envelope(type=MessageType.PLAYER_STATE, match_id=mid, actor="p2",
                       payload={"x": 400.0, "direction": -1, "is_blocking": p2_blocking, "state": "idle"}))


async def _attack(pub, mid, seq, action_id="strike_2"):
    await pub(channels.player_input(mid, "p1"),
              Envelope(type=MessageType.ATTACK, match_id=mid, actor="p1", client_seq=seq,
                       payload={"action_id": action_id}))


def test_attack_deducts_attacker_stamina():
    async def main():
        _, mc, pub, mid = await _start_fighting_match()
        await _set_positions(pub, mid)
        cost = action_data.ACTIONS["strike_2"].stamina_cost
        before = mc.stamina["p1"]
        await _attack(pub, mid, seq=1)
        assert mc.stamina["p1"] == before - cost
    asyncio.run(main())


def test_insufficient_stamina_rejects_attack():
    async def main():
        _, mc, pub, mid = await _start_fighting_match()
        await _set_positions(pub, mid)
        mc.stamina["p1"] = 1.0  # too low for any attack
        hp_before = mc.state.players["p2"].hp
        await _attack(pub, mid, seq=1)
        assert mc.stamina["p1"] == 1.0          # not deducted
        assert mc.state.players["p2"].hp == hp_before  # no damage landed
    asyncio.run(main())


def test_blocked_hit_drains_defender_and_bumps_counter():
    async def main():
        _, mc, pub, mid = await _start_fighting_match()
        await _set_positions(pub, mid, p2_blocking=True)
        stam_before = mc.stamina["p2"]
        await _attack(pub, mid, seq=1)
        assert mc.blocks_taken["p2"] == 1
        assert mc.stamina["p2"] == stam_before - action_data.BLOCK_STAMINA_DRAIN
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
    print(f"stamina: {'all tests passed' if not failures else f'{failures} FAILED'}")
    sys.exit(1 if failures else 0)
