"""Match Coordinator: the authoritative, pygame-free server core.

Holds the game-rules engine (``action_data``, ``rules``, ``combat``), the
match-lifecycle state chart (``lifecycle``), per-match authoritative state
(``match_state``), the orchestration (``match_coordinator``), and the FastAPI
entrypoint (``app`` / ``run_server``).

IMPORTANT: nothing in this package may import ``pygame`` (directly or via
``actions``/``hero``/``anim``/``state``/``player``). The server image ships
without SDL.
"""
