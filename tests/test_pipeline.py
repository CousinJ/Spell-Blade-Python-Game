"""Unit tests for the EIP pipeline pieces: Router, Enricher, Aggregator.

    python tests/test_pipeline.py
    pytest tests/test_pipeline.py
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from coordinator.match_state import MatchState  # noqa: E402
from messaging.aggregator import SnapshotAggregator  # noqa: E402
from messaging.enricher import CombatView, Enricher  # noqa: E402
from messaging.router import MatchRouter, NoRouteError  # noqa: E402
from messaging.schema import Envelope, MessageType  # noqa: E402


def _run(coro):
    return asyncio.run(coro)


def test_router_dispatches_by_type():
    async def main():
        seen = []
        r = MatchRouter()
        r.register(MessageType.ATTACK, lambda env, ch: seen.append(("atk", env, ch)) or _aw())
        await r.route(Envelope(type=MessageType.ATTACK, actor="p1"), "input/p1")
        assert seen and seen[0][0] == "atk"

    async def _aw():
        return None

    _run(main())


def test_router_unknown_type_raises():
    async def main():
        r = MatchRouter()
        try:
            await r.route(Envelope(type="nope"), "ch")
        except NoRouteError:
            return
        raise AssertionError("expected NoRouteError")

    _run(main())


def test_enricher_snapshot_adds_monotonic_seq_and_ts():
    clock = iter([100.0, 101.0]).__next__
    e = Enricher(clock=clock, hit_resolver=lambda *a, **k: None)
    a = e.enrich_snapshot({"phase": "FIGHTING"})
    b = e.enrich_snapshot({"phase": "FIGHTING"})
    assert a["seq"] == 1 and b["seq"] == 2
    assert a["server_ts"] == 100.0 and b["server_ts"] == 101.0
    assert a["phase"] == "FIGHTING"  # original fields preserved


def test_enricher_attack_resolves_and_adds_metadata():
    class FakeHit:
        hit, damage, blocked, reason = True, 30, False, "hit"

    e = Enricher(clock=lambda: 42.0, hit_resolver=lambda *a, **k: FakeHit())
    view = CombatView(
        attacker="p1", target_actor="p2", attacker_x=300, attacker_dir=1,
        target_x=400, target_blocking=False, target_alive=True, attacker_hero="FireChar",
    )
    env = Envelope(type=MessageType.ATTACK, actor="p1", payload={"action_id": "fire_strike"})
    out = e.enrich_attack(env, view)
    assert out["attacker"] == "p1" and out["target"] == "p2"
    assert out["attacker_hero"] == "FireChar"
    assert out["server_ts"] == 42.0
    assert out["hit"] == {"hit": True, "damage": 30, "blocked": False, "reason": "hit"}


def test_aggregator_merges_movement_and_authoritative_state():
    ms = MatchState("M")
    ms.join("p1", x=200.0)
    ms.join("p2", x=1000.0)
    ms.select_hero("p1", "FireChar")
    ms.apply_damage("p2", 30, attacker="p1")  # p2 hp 70

    agg = SnapshotAggregator()
    agg.update("p1", {"x": 333.0, "direction": 1, "is_blocking": False})

    snap = agg.build(ms)
    p1 = next(p for p in snap["players"] if p["actor"] == "p1")
    p2 = next(p for p in snap["players"] if p["actor"] == "p2")
    assert p1["x"] == 333.0 and p1["hero"] == "FireChar"  # live movement + auth hero
    assert p2["x"] == 1000.0 and p2["hp"] == 70  # falls back to auth x; auth hp
    assert snap["phase"] == "LOBBY"


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
    print(f"pipeline: {'all tests passed' if not failures else f'{failures} FAILED'}")
    sys.exit(1 if failures else 0)
