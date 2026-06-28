"""Aggregator (EIP): correlate per-player state into one world snapshot.

Combines two sources keyed by actor: the **live movement buffer** (the latest
``player_state`` published by each client) and the **authoritative match state**
(hp / alive / hero) — emitting a single ``world_snapshot`` payload per tick.

Reference: https://www.enterpriseintegrationpatterns.com/Aggregator.html
"""
from __future__ import annotations


class SnapshotAggregator:
    def __init__(self) -> None:
        self._latest: dict[str, dict] = {}

    def update(self, actor: str, player_state: dict) -> None:
        self._latest[actor] = dict(player_state)

    def latest(self, actor: str) -> dict:
        return self._latest.get(actor, {})

    def build(self, match_state) -> dict:
        players = []
        for actor in sorted(match_state.players):
            ps = match_state.players[actor]
            mv = self._latest.get(actor, {})
            players.append(
                {
                    "actor": actor,
                    "x": mv.get("x", ps.x),
                    "direction": mv.get("direction"),
                    "state": mv.get("state"),
                    "is_blocking": bool(mv.get("is_blocking", False)),
                    "hp": ps.hp,
                    "alive": ps.alive,
                    "hero": ps.hero,
                }
            )
        return {"phase": match_state.phase, "winner": match_state.winner, "players": players}
