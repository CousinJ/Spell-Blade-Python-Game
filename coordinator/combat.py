"""Event-based combat resolution (pure, pygame-free).

The original game had no HP, hitboxes, or hit detection. This module defines a
simple, deterministic, server-authoritative model:

On an ``attack`` event the server checks
  * the action is actually an attack,
  * the target is alive,
  * the attacker is **facing** the target (``direction`` toward the target's x),
  * the target is within the action's **reach** (horizontal distance),
and, if so, applies ``damage`` (reduced by ``block_mitigation`` when the target
is blocking). :class:`SwingTracker` enforces **one hit per swing**.

Facing convention matches the game: ``direction`` is ``+1`` (right) / ``-1``
(left); the attacker must face toward the target's x for the hit to count.
"""
from __future__ import annotations

from dataclasses import dataclass

from coordinator import rules


@dataclass(frozen=True)
class HitResult:
    hit: bool
    damage: int  # effective damage applied (after block mitigation)
    blocked: bool
    reason: str  # "hit" | "not_attack" | "target_dead" | "wrong_facing" | "out_of_range"


def resolve_hit(
    attacker_x: float,
    attacker_dir: int,
    target_x: float,
    target_blocking: bool,
    action_id: str,
    *,
    target_alive: bool = True,
) -> HitResult:
    if not rules.is_attack(action_id):
        return HitResult(False, 0, False, "not_attack")
    if not target_alive:
        return HitResult(False, 0, False, "target_dead")

    action = rules.get_action(action_id)

    # Facing: attacker must point toward the target. Same-x always "faces".
    dx = target_x - attacker_x
    if dx != 0:
        required_dir = 1 if dx > 0 else -1
        if attacker_dir != required_dir:
            return HitResult(False, 0, False, "wrong_facing")

    if abs(dx) > action.reach:
        return HitResult(False, 0, False, "out_of_range")

    if target_blocking:
        effective = max(0, int(round(action.damage * (1.0 - action.block_mitigation))))
        return HitResult(True, effective, True, "hit")
    return HitResult(True, action.damage, False, "hit")


class SwingTracker:
    """Dedupe so a single attack swing can only land once.

    Keyed by ``(actor, swing_id)`` where ``swing_id`` is a per-attack identifier
    (e.g. the client_seq of the attack message).
    """

    def __init__(self) -> None:
        self._seen: set[tuple[str, object]] = set()

    def register(self, actor: str, swing_id: object) -> bool:
        """Return True the first time a swing is seen, False on repeats."""
        key = (actor, swing_id)
        if key in self._seen:
            return False
        self._seen.add(key)
        return True

    def reset(self) -> None:
        self._seen.clear()
