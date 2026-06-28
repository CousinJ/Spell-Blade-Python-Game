"""Pure-data action & hero tables — the single source of truth for combat.

``damage``, ``frames`` and the hero->attack mapping are extracted verbatim from
the client's ``actions.py`` / ``hero.py`` (which transitively import pygame and
therefore must never be imported by the server). ``reach`` and
``block_mitigation`` are **new** server-side values (no spatial/hit data existed
in the original game).

In M5 the client's ``actions.py`` should be refactored to read ``damage``/
``frames`` from here too, so the two sides can never drift.

Only the standard-library ``dataclasses`` is imported — no pygame, ever.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ActionData:
    action_id: str
    damage: int
    reach: float  # horizontal range in px within which the hit lands
    frames: int  # animation frame count (= actions.py anim_array[1])
    block_mitigation: float = 0.75  # fraction of damage negated when blocked (0..1)


# action_id -> data.  damage/frames match actions.py exactly.
ACTIONS: dict[str, ActionData] = {
    "block": ActionData("block", 0, 0.0, 7, 1.0),
    # ice
    "ice_lance": ActionData("ice_lance", 22, 230.0, 4, 0.60),
    "frost_sweep": ActionData("frost_sweep", 16, 200.0, 5, 0.70),
    "overhead_strike": ActionData("overhead_strike", 20, 170.0, 4, 0.50),
    # forest
    "slash": ActionData("slash", 22, 175.0, 4, 0.70),
    "back_slash": ActionData("back_slash", 16, 175.0, 4, 0.70),
    "quick_thrust": ActionData("quick_thrust", 20, 220.0, 4, 0.60),
    "thrust": ActionData("thrust", 20, 220.0, 4, 0.60),
    # fire
    "fire_strike": ActionData("fire_strike", 30, 170.0, 4, 0.50),
    "fire_slash": ActionData("fire_slash", 25, 175.0, 4, 0.60),
}

# hero class name -> display name + its three attack action_ids (from hero.py).
HEROES: dict[str, dict] = {
    "FireChar": {"name": "Dravin", "attacks": ["fire_slash", "fire_strike", "thrust"]},
    "MagicChar": {"name": "Torin", "attacks": ["back_slash", "ice_lance", "quick_thrust"]},
    "ForestChar": {"name": "Rast", "attacks": ["slash", "back_slash", "quick_thrust"]},
    "IceChar": {"name": "Tyros", "attacks": ["ice_lance", "frost_sweep", "overhead_strike"]},
}

ATTACK_ACTIONS: frozenset[str] = frozenset(a for a in ACTIONS if a != "block")

# --- spatial / match constants (single source of truth, pygame-free) -------
# Shared by the server coordinator AND the pygame client so the two can never
# drift on starting positions, facing, or max HP. The client imports these via
# game_settings; the coordinator imports them directly.
MAX_HP: int = 100
START_X: dict[str, float] = {"p1": 200.0, "p2": 1000.0}
START_DIR: dict[str, int] = {"p1": 1, "p2": -1}
