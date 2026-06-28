"""Unit tests for event-based combat resolution (reach / facing / block / dedupe).

    python tests/test_combat.py
    pytest tests/test_combat.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from coordinator import action_data  # noqa: E402
from coordinator.combat import SwingTracker, resolve_hit  # noqa: E402

# strike_2: damage 20, reach 175, block_mitigation 0.60
ATK = "strike_2"


def test_hit_in_range_and_facing():
    r = resolve_hit(200.0, +1, 300.0, False, ATK)  # target to the right, facing right
    assert r.hit and r.reason == "hit"
    assert r.damage == 20 and not r.blocked


def test_miss_out_of_range():
    r = resolve_hit(200.0, +1, 500.0, False, ATK)  # 300 px > reach 175
    assert not r.hit and r.reason == "out_of_range" and r.damage == 0


def test_miss_wrong_facing():
    r = resolve_hit(200.0, -1, 300.0, False, ATK)  # target right, but facing left
    assert not r.hit and r.reason == "wrong_facing"


def test_block_reduces_damage():
    r = resolve_hit(200.0, +1, 300.0, True, ATK)  # blocking
    assert r.hit and r.blocked
    assert r.damage == 8  # 20 * (1 - 0.60)


def test_dead_target_no_hit():
    r = resolve_hit(200.0, +1, 300.0, False, ATK, target_alive=False)
    assert not r.hit and r.reason == "target_dead"


def test_block_action_is_not_an_attack():
    r = resolve_hit(200.0, +1, 210.0, False, "block")
    assert not r.hit and r.reason == "not_attack"


def test_facing_left_hits():
    # attacker at 500 facing left hits target at 400 within reach
    r = resolve_hit(500.0, -1, 400.0, False, ATK)
    assert r.hit and r.damage == 20


def test_reach_boundary_inclusive():
    # exactly at reach distance counts as a hit
    r = resolve_hit(200.0, +1, 200.0 + 175.0, False, ATK)
    assert r.hit


def test_swing_tracker_dedupes_one_hit_per_swing():
    t = SwingTracker()
    assert t.register("p1", 42) is True   # first time -> lands
    assert t.register("p1", 42) is False  # same swing -> ignored
    assert t.register("p1", 43) is True   # next swing -> lands
    assert t.register("p2", 42) is True   # different actor, same id -> independent


def test_damage_values_match_source_table():
    # guards against accidental edits drifting from the documented data
    assert action_data.ACTIONS["strike_2"].damage == 20
    assert action_data.ACTIONS["jump_attack"].damage == 26


def test_standardized_moveset_and_stamina_costs():
    # the four arrow attacks + block, each with a positive cost (block is free)
    assert set(action_data.ACTIONS) == {"block", "jump_attack", "strike_1", "strike_2", "sweep"}
    assert action_data.ACTIONS["block"].stamina_cost == 0
    for aid in ("jump_attack", "strike_1", "strike_2", "sweep"):
        assert action_data.ACTIONS[aid].stamina_cost > 0


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
    print(f"combat: {'all tests passed' if not failures else f'{failures} FAILED'}")
    sys.exit(1 if failures else 0)
