"""Match-lifecycle state chart (hand-rolled FSM) — GoF State, pygame-free.

States, events, transitions and guards are declared as data in
:data:`TRANSITIONS` so they can be documented (README) and tested directly.

Guards are predicates over a plain ``ctx`` dict the coordinator supplies:
    players_connected : int   - distinct connected players
    heroes_selected   : int   - players who have chosen a hero
    assets_loaded     : int   - clients reporting assets loaded
    any_player_dead   : bool  - some player's hp <= 0
    rematch_requests  : int   - players who requested a rematch
    max_rounds_won    : int   - highest rounds_won across players
    rounds_to_win     : int   - N for best-of-N (default 1)
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

DEFAULT_ROUNDS_TO_WIN = 1


class State:
    LOBBY = "LOBBY"
    CHARACTER_SELECT = "CHARACTER_SELECT"
    LOADING = "LOADING"
    FIGHTING = "FIGHTING"
    ROUND_OVER = "ROUND_OVER"
    MATCH_OVER = "MATCH_OVER"


class Event:
    PLAYER_JOINED = "PLAYER_JOINED"
    HERO_SELECTED = "HERO_SELECTED"
    ASSETS_LOADED = "ASSETS_LOADED"
    PLAYER_DIED = "PLAYER_DIED"
    REMATCH = "REMATCH"
    MATCH_DECIDED = "MATCH_DECIDED"
    PLAYER_LEFT = "PLAYER_LEFT"


WILDCARD = "*"


class InvalidTransition(Exception):
    """Raised when an event is not allowed from the current state (or its guard fails)."""


Guard = Callable[[dict], bool]


@dataclass(frozen=True)
class Transition:
    source: str
    event: str
    target: str
    guard: Guard
    guard_desc: str


def _ctx(ctx: dict, key: str, default: int = 0):
    return ctx.get(key, default)


TRANSITIONS: list[Transition] = [
    Transition(State.LOBBY, Event.PLAYER_JOINED, State.CHARACTER_SELECT,
               lambda c: _ctx(c, "players_connected") >= 2, "both players connected"),
    Transition(State.CHARACTER_SELECT, Event.HERO_SELECTED, State.LOADING,
               lambda c: _ctx(c, "heroes_selected") >= 2, "both heroes chosen"),
    Transition(State.LOADING, Event.ASSETS_LOADED, State.FIGHTING,
               lambda c: _ctx(c, "assets_loaded") >= 2, "both clients report loaded"),
    Transition(State.FIGHTING, Event.PLAYER_DIED, State.ROUND_OVER,
               lambda c: bool(c.get("any_player_dead")), "a player hp <= 0"),
    Transition(State.ROUND_OVER, Event.REMATCH, State.CHARACTER_SELECT,
               lambda c: _ctx(c, "rematch_requests") >= 2
               and _ctx(c, "max_rounds_won") < _ctx(c, "rounds_to_win", DEFAULT_ROUNDS_TO_WIN),
               "both request rematch & no one has reached N"),
    Transition(State.ROUND_OVER, Event.MATCH_DECIDED, State.MATCH_OVER,
               lambda c: _ctx(c, "max_rounds_won") >= _ctx(c, "rounds_to_win", DEFAULT_ROUNDS_TO_WIN),
               "a player reached N rounds won"),
    Transition(WILDCARD, Event.PLAYER_LEFT, State.MATCH_OVER,
               lambda c: True, "a player disconnected"),
]


class LifecycleMachine:
    def __init__(self, state: str = State.LOBBY) -> None:
        self.state = state

    def allowed(self, event: str, ctx: Optional[dict] = None) -> Optional[Transition]:
        """Return the transition that would fire for ``event`` now, or None."""
        ctx = ctx or {}
        for t in TRANSITIONS:
            if t.event != event:
                continue
            if t.source not in (self.state, WILDCARD):
                continue
            if t.guard(ctx):
                return t
        return None

    def can_fire(self, event: str, ctx: Optional[dict] = None) -> bool:
        return self.allowed(event, ctx) is not None

    def fire(self, event: str, ctx: Optional[dict] = None) -> Transition:
        t = self.allowed(event, ctx)
        if t is None:
            raise InvalidTransition(
                f"event {event!r} not allowed from state {self.state!r}"
            )
        self.state = t.target
        return t


def transitions_table() -> list[dict]:
    """Introspection for docs/tests: the declared transitions as plain dicts."""
    return [
        {"from": t.source, "event": t.event, "to": t.target, "guard": t.guard_desc}
        for t in TRANSITIONS
    ]
