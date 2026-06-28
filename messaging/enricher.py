"""Content Enricher (EIP): augment messages with server-derived data.

Two enrichments:
  * :meth:`enrich_snapshot` stamps an outbound snapshot payload with a monotonic
    ``seq`` and a server timestamp.
  * :meth:`enrich_attack` turns a bare ``attack`` message (just ``action_id``)
    into a fully resolved combat outcome, drawing on external resources: the
    live positions/HP (match state), the action table, and the server clock —
    attaching the hit result and the attacker's hero metadata.

The hit resolver is injected (defaults to ``coordinator.combat.resolve_hit``)
so this module has no hard import of the coordinator and stays easy to test.

Reference: https://www.enterpriseintegrationpatterns.com/DataEnricher.html
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable, Optional

from messaging.schema import Envelope


@dataclass
class CombatView:
    attacker: str
    target_actor: str
    attacker_x: float
    attacker_dir: int
    target_x: float
    target_blocking: bool
    target_alive: bool
    attacker_hero: Optional[str]


class Enricher:
    def __init__(self, clock: Callable[[], float] = time.time, hit_resolver=None) -> None:
        self._clock = clock
        if hit_resolver is None:
            from coordinator.combat import resolve_hit as hit_resolver
        self._resolve = hit_resolver
        self._seq = 0

    def next_seq(self) -> int:
        self._seq += 1
        return self._seq

    def enrich_snapshot(self, payload: dict) -> dict:
        out = dict(payload)
        out["seq"] = self.next_seq()
        out["server_ts"] = self._clock()
        return out

    def enrich_attack(self, env: Envelope, view: CombatView) -> dict:
        action_id = env.payload.get("action_id")
        hit = self._resolve(
            view.attacker_x,
            view.attacker_dir,
            view.target_x,
            view.target_blocking,
            action_id,
            target_alive=view.target_alive,
        )
        return {
            "server_ts": self._clock(),
            "attacker": env.actor or view.attacker,
            "target": view.target_actor,
            "action_id": action_id,
            "attacker_hero": view.attacker_hero,
            "hit": {
                "hit": hit.hit,
                "damage": hit.damage,
                "blocked": hit.blocked,
                "reason": hit.reason,
            },
        }
