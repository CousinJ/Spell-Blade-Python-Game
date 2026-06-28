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
    stamina_cost: int = 0  # stamina the attacker spends to perform the action


# action_id -> data. STANDARDIZED moveset: every hero shares these same five
# actions (same stats, same effect-sheet animations). The four attacks are bound
# to the arrow keys client-side (up/left/right/down); block is held with Space.
# damage/frames/stamina_cost are mirrored by the client's actions.py via this
# table, so the two sides can never drift.
ACTIONS: dict[str, ActionData] = {
    #            id              dmg  reach  frm  block_mit  cost
    "block":        ActionData("block",        0,   0.0, 7, 1.00,  0),
    "jump_attack":  ActionData("jump_attack", 26, 190.0, 5, 0.50, 34),  # Up
    "strike_1":     ActionData("strike_1",    16, 175.0, 4, 0.70, 18),  # Left
    "strike_2":     ActionData("strike_2",    20, 175.0, 4, 0.60, 24),  # Right
    "sweep":        ActionData("sweep",       14, 210.0, 5, 0.70, 20),  # Down
}

# hero class name -> display name. Movesets are shared now, so heroes carry no
# per-hero attack list; only the display name (sprite/effect sheets live in the
# pygame-side hero.py).
HEROES: dict[str, dict] = {
    "FireChar": {"name": "Dravin"},
    "MagicChar": {"name": "Torin"},
    "ForestChar": {"name": "Rast"},
    "IceChar": {"name": "Tyros"},
}

ATTACK_ACTIONS: frozenset[str] = frozenset(a for a in ACTIONS if a != "block")

# --- spatial / match constants (single source of truth, pygame-free) -------
# Shared by the server coordinator AND the pygame client so the two can never
# drift on starting positions, facing, or max HP. The client imports these via
# game_settings; the coordinator imports them directly.
MAX_HP: int = 100
START_X: dict[str, float] = {"p1": 200.0, "p2": 1000.0}
START_DIR: dict[str, int] = {"p1": 1, "p2": -1}

# --- stamina (server-authoritative; mirrored to clients in the snapshot) ----
# Stamina is fast/continuous like position and is NOT written to the audit log.
MAX_STAMINA: int = 100
STAMINA_REGEN_PER_SEC: float = 18.0  # refill rate; paused while a player blocks
BLOCK_STAMINA_DRAIN: int = 14  # stamina the defender loses per blocked hit
