"""Authoritative per-match state + the Observer-pattern Subject.

``MatchState`` is the single source of truth for one match (players, HP, phase,
winner). Every mutation goes through a **command method** which calls
:meth:`_emit`. ``_emit``:

1. builds one immutable **event** dict,
2. **notifies** observers (the audit Observer persists it and back-fills ``seq``),
3. **applies** it via :meth:`apply` — the *same* reducer used by :meth:`from_events`.

Because the live path and the replay path share one reducer, and because events
carry absolute post-values, every mutation is exactly reconstructable from the
log (event sourcing).

This module is **pygame-free** (server core).
"""
from __future__ import annotations

import time
from dataclasses import asdict, dataclass
from typing import Any, Optional

DEFAULT_MAX_HP = 100


class EventType:
    """Audit/event vocabulary owned by the domain."""

    JOIN = "join"
    LEAVE = "leave"
    HERO_SELECT = "hero_select"
    DAMAGE = "damage"
    HP_CHANGE = "hp_change"
    TRANSITION = "transition"
    ROUND_RESULT = "round_result"


@dataclass
class PlayerState:
    actor: str
    hero: Optional[str] = None
    hp: int = DEFAULT_MAX_HP
    max_hp: int = DEFAULT_MAX_HP
    alive: bool = True
    x: float = 0.0
    rounds_won: int = 0


class MatchState:
    def __init__(self, match_id: str, phase: str = "LOBBY") -> None:
        self.match_id = match_id
        self.phase = phase
        self.players: dict[str, PlayerState] = {}
        self.winner: Optional[str] = None
        self.last_seq = 0
        self._observers: list[Any] = []

    # ------------------------------------------------------------------ Subject
    def attach(self, observer: Any) -> None:
        if observer not in self._observers:
            self._observers.append(observer)

    def detach(self, observer: Any) -> None:
        if observer in self._observers:
            self._observers.remove(observer)

    def _notify(self, event: dict) -> None:
        for observer in list(self._observers):
            observer.on_event(self, event)

    # --------------------------------------------------------- command methods
    def join(self, actor: str, x: float = 0.0) -> dict:
        return self._emit(EventType.JOIN, actor, {"x": x})

    def leave(self, actor: str) -> dict:
        return self._emit(EventType.LEAVE, actor, {})

    def select_hero(self, actor: str, hero: str) -> dict:
        return self._emit(EventType.HERO_SELECT, actor, {"hero": hero})

    def transition(self, frm: str, to: str, event_name: Optional[str] = None) -> dict:
        return self._emit(
            EventType.TRANSITION, "system", {"from": frm, "to": to, "event": event_name}
        )

    def apply_damage(
        self, target: str, amount: int, attacker: Optional[str] = None, blocked: bool = False
    ) -> dict:
        ps = self.players[target]
        hp_after = max(0, ps.hp - max(0, int(amount)))
        return self._emit(
            EventType.DAMAGE,
            target,
            {
                "attacker": attacker,
                "amount": int(amount),
                "blocked": blocked,
                "hp_after": hp_after,
                "alive": hp_after > 0,
            },
        )

    def set_hp(self, actor: str, hp: int) -> dict:
        ps = self.players[actor]
        hp = max(0, min(ps.max_hp, int(hp)))
        return self._emit(EventType.HP_CHANGE, actor, {"hp_after": hp, "alive": hp > 0})

    def round_result(self, round_winner: Optional[str], match_winner: Optional[str] = None) -> dict:
        return self._emit(
            EventType.ROUND_RESULT,
            "system",
            {"round_winner": round_winner, "match_winner": match_winner},
        )

    def _emit(self, type: str, actor: Optional[str], payload: dict) -> dict:
        event = {"type": type, "actor": actor, "payload": payload, "ts": time.time()}
        self._notify(event)  # observers persist & back-fill event["seq"]
        self.apply(event)
        return event

    # ----------------------------------------------- reducer (live + replay)
    def apply(self, event: dict) -> None:
        t = event["type"]
        actor = event.get("actor")
        p = event.get("payload", {})

        if t == EventType.JOIN:
            self.players[actor] = PlayerState(actor=actor, x=float(p.get("x", 0.0)))
        elif t == EventType.LEAVE:
            ps = self.players.get(actor)
            if ps:
                ps.alive = False
        elif t == EventType.HERO_SELECT:
            self.players[actor].hero = p["hero"]
        elif t in (EventType.DAMAGE, EventType.HP_CHANGE):
            ps = self.players[actor]
            ps.hp = int(p["hp_after"])
            ps.alive = bool(p["alive"])
        elif t == EventType.TRANSITION:
            self.phase = p["to"]
        elif t == EventType.ROUND_RESULT:
            rw = p.get("round_winner")
            if rw and rw in self.players:
                self.players[rw].rounds_won += 1
            self.winner = p.get("match_winner")
        # Unknown event types are ignored (forward-compatible).

        seq = event.get("seq")
        if seq is not None:
            self.last_seq = seq

    @classmethod
    def from_events(cls, match_id: str, events: list[dict]) -> "MatchState":
        ms = cls(match_id)
        for event in events:
            ms.apply(event)
        return ms

    # ------------------------------------------------------------- inspection
    def snapshot(self) -> dict:
        return {
            "match_id": self.match_id,
            "phase": self.phase,
            "winner": self.winner,
            "last_seq": self.last_seq,
            "players": {a: asdict(ps) for a, ps in sorted(self.players.items())},
        }
