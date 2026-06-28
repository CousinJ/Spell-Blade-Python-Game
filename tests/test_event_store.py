"""Unit tests for the audit event store + point-in-time replay (M2 "Done when").

Runnable two ways:
    python tests/test_event_store.py
    pytest tests/test_event_store.py
"""
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from audit.event_store import EventStore  # noqa: E402
from audit.observer import AuditObserver  # noqa: E402
from coordinator.match_state import MatchState  # noqa: E402


def _new_db():
    tmp = tempfile.mkdtemp()
    return tmp, os.path.join(tmp, "audit.db")


def test_replay_reconstructs_exact_state_and_point_in_time():
    tmp, db = _new_db()
    try:
        store = EventStore(db)
        ms = MatchState("M-1")
        ms.attach(AuditObserver(store))

        ms.join("p1", x=200.0)
        ms.join("p2", x=1000.0)
        ms.select_hero("p1", "FireChar")
        ms.select_hero("p2", "IceChar")
        ms.transition("LOBBY", "CHARACTER_SELECT", "PLAYER_JOINED")
        ms.transition("CHARACTER_SELECT", "FIGHTING", "ASSETS_LOADED")
        mid = ms.apply_damage("p2", 22, attacker="p1")  # p2 hp -> 78
        mid_seq = mid["seq"]
        ms.apply_damage("p2", 22, attacker="p1")  # 56
        ms.apply_damage("p2", 56, attacker="p1")  # 0 -> dead
        ms.round_result("p1", match_winner="p1")
        ms.transition("FIGHTING", "MATCH_OVER", "MATCH_DECIDED")

        # Full replay reproduces the live state exactly.
        replayed = store.replay("M-1")
        assert replayed.snapshot() == ms.snapshot(), (replayed.snapshot(), ms.snapshot())

        # Point-in-time replay: as of the first damage, p2 had 78 hp and was alive.
        midstate = store.replay("M-1", upto_seq=mid_seq)
        assert midstate.players["p2"].hp == 78, midstate.players["p2"].hp
        assert midstate.players["p2"].alive is True
        assert midstate.phase == "FIGHTING"
        assert midstate.winner is None

        # Final reconstructed facts.
        assert replayed.players["p2"].hp == 0
        assert replayed.players["p2"].alive is False
        assert replayed.players["p1"].rounds_won == 1
        assert replayed.winner == "p1"
        assert replayed.phase == "MATCH_OVER"
        store.close()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_seq_is_monotonic_per_match_and_survives_reopen():
    tmp, db = _new_db()
    try:
        store = EventStore(db)
        ms = MatchState("M-2")
        ms.attach(AuditObserver(store))
        ms.join("p1")
        ms.join("p2")  # seqs 1, 2
        store.close()

        # Reopen the same db -> seq must continue from the persisted max.
        store2 = EventStore(db)
        seq = store2.append("M-2", "transition", "system", {"from": "LOBBY", "to": "FIGHTING"})
        assert seq == 3, seq
        assert "M-2" in store2.matches()
        store2.close()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_two_matches_have_independent_seq_lines():
    tmp, db = _new_db()
    try:
        store = EventStore(db)
        a = MatchState("A")
        b = MatchState("B")
        a.attach(AuditObserver(store))
        b.attach(AuditObserver(store))
        a.join("p1")  # A seq 1
        b.join("p1")  # B seq 1
        a.join("p2")  # A seq 2
        assert [e["seq"] for e in store.events_for("A")] == [1, 2]
        assert [e["seq"] for e in store.events_for("B")] == [1]
        assert set(store.matches()) == {"A", "B"}
        store.close()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


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
    print(f"event_store: {'all tests passed' if not failures else f'{failures} FAILED'}")
    sys.exit(1 if failures else 0)
