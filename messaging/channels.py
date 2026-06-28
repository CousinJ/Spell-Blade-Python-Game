"""Channel-key builders for the pub/sub hub.

Channels are logical string keys, namespaced per match so traffic never crosses
matches on the shared transport:

    spellblade/v1/<matchId>/<topic>

A new client that does not yet have a match id announces itself on the global
lobby (:data:`GLOBAL_LOBBY`); the coordinator replies with an assigned match id.
"""
from __future__ import annotations

PREFIX = "spellblade"
VERSION = "v1"

# Well-known global channel for matchmaking joins (pre-match).
GLOBAL_LOBBY = f"{PREFIX}/{VERSION}/lobby"


def _base(match_id: str) -> str:
    return f"{PREFIX}/{VERSION}/{match_id}"


def lobby(match_id: str) -> str:
    """Per-match lobby: joins / hero selection / ready signals."""
    return f"{_base(match_id)}/lobby"


def player_input(match_id: str, actor: str) -> str:
    """Per-player input channel (actor = ``p1`` | ``p2``)."""
    return f"{_base(match_id)}/input/{actor}"


def snapshot(match_id: str) -> str:
    """Authoritative world-snapshot channel (coordinator -> clients)."""
    return f"{_base(match_id)}/snapshot"


def lifecycle(match_id: str) -> str:
    """State-chart transition channel (coordinator -> clients)."""
    return f"{_base(match_id)}/lifecycle"


def client_inbox(client_id: str) -> str:
    """Private reply channel for a not-yet-matched client (join handshake)."""
    return f"{PREFIX}/{VERSION}/client/{client_id}/inbox"
