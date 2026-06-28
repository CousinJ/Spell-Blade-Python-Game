"""Unit tests for the match-lifecycle state chart (valid/invalid transitions, guards).

Also asserts the whole M3 server core imports with **no pygame**.

    python tests/test_lifecycle.py
    pytest tests/test_lifecycle.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from coordinator.lifecycle import (  # noqa: E402
    Event,
    InvalidTransition,
    LifecycleMachine,
    State,
    transitions_table,
)

BOTH = {"players_connected": 2, "heroes_selected": 2, "assets_loaded": 2}


def test_happy_path_to_match_over():
    m = LifecycleMachine()
    assert m.state == State.LOBBY
    m.fire(Event.PLAYER_JOINED, BOTH)
    assert m.state == State.CHARACTER_SELECT
    m.fire(Event.HERO_SELECTED, BOTH)
    assert m.state == State.LOADING
    m.fire(Event.ASSETS_LOADED, BOTH)
    assert m.state == State.FIGHTING
    m.fire(Event.PLAYER_DIED, {"any_player_dead": True})
    assert m.state == State.ROUND_OVER
    # best-of-1: winner already has rounds_won == 1 == N
    m.fire(Event.MATCH_DECIDED, {"max_rounds_won": 1, "rounds_to_win": 1})
    assert m.state == State.MATCH_OVER


def test_guard_blocks_join_with_one_player():
    m = LifecycleMachine()
    assert not m.can_fire(Event.PLAYER_JOINED, {"players_connected": 1})
    try:
        m.fire(Event.PLAYER_JOINED, {"players_connected": 1})
    except InvalidTransition:
        assert m.state == State.LOBBY
        return
    raise AssertionError("expected InvalidTransition when only one player connected")


def test_invalid_event_for_state():
    m = LifecycleMachine()  # LOBBY
    try:
        m.fire(Event.HERO_SELECTED, BOTH)
    except InvalidTransition:
        return
    raise AssertionError("HERO_SELECTED should be invalid from LOBBY")


def test_player_left_is_wildcard_from_any_state():
    m = LifecycleMachine(State.FIGHTING)
    m.fire(Event.PLAYER_LEFT, {})
    assert m.state == State.MATCH_OVER

    m2 = LifecycleMachine(State.CHARACTER_SELECT)
    m2.fire(Event.PLAYER_LEFT, {})
    assert m2.state == State.MATCH_OVER


def test_rematch_path_for_best_of_three():
    # round 1 over, no one at N=2 yet -> rematch returns to CHARACTER_SELECT
    m = LifecycleMachine(State.ROUND_OVER)
    ctx = {"rematch_requests": 2, "max_rounds_won": 1, "rounds_to_win": 2}
    assert m.can_fire(Event.REMATCH, ctx)
    assert not m.can_fire(Event.MATCH_DECIDED, ctx)  # not decided yet
    m.fire(Event.REMATCH, ctx)
    assert m.state == State.CHARACTER_SELECT


def test_rematch_blocked_when_match_already_decided():
    m = LifecycleMachine(State.ROUND_OVER)
    ctx = {"rematch_requests": 2, "max_rounds_won": 2, "rounds_to_win": 2}
    assert not m.can_fire(Event.REMATCH, ctx)
    assert m.can_fire(Event.MATCH_DECIDED, ctx)


def test_transitions_table_is_complete():
    table = transitions_table()
    assert len(table) == 7
    # every row documents a guard
    assert all(row["guard"] for row in table)


def test_m3_core_is_pygame_free():
    import coordinator.action_data  # noqa: F401
    import coordinator.combat  # noqa: F401
    import coordinator.lifecycle  # noqa: F401
    import coordinator.rules  # noqa: F401

    leaked = [m for m in sys.modules if m.split(".")[0] == "pygame"]
    assert leaked == [], f"pygame leaked into the server core: {leaked}"


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
    print(f"lifecycle: {'all tests passed' if not failures else f'{failures} FAILED'}")
    sys.exit(1 if failures else 0)
