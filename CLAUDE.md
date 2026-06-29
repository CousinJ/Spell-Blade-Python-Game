# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A 2-player pygame fighting game (Spell Blade) with a **server-authoritative, event-sourced** backend. pygame clients connect over a **WebSocket publish/subscribe** channel to a headless **Match Coordinator** (FastAPI). There is no external broker — the coordinator *is* the broker. The codebase is deliberately built around named **Enterprise Integration Patterns (EIP)** and **GoF** patterns; each module's docstring states which pattern it implements. Preserve that mapping when editing.

## Commands

```bash
# Install (two SEPARATE dependency sets — see invariant below)
pip install -r requirements.txt          # client: pygame-ce, websocket-client
pip install -r requirements-server.txt   # server: fastapi, uvicorn, websockets

# Run locally (needs THREE terminals: 1 coordinator + 2 clients)
python -m coordinator.run_server         # coordinator: ws://localhost:8000/ws + HTTP
python client.py                         # each client opens its own window

# Tests (server core — runs without pygame/SDL)
python -m pytest tests/ -q
python -m pytest tests/test_combat.py -q              # single file
python -m pytest tests/test_combat.py::test_name -q   # single test

# Headless end-to-end (start coordinator first; drives a full match via the real client transport)
python scripts/m5_smoke.py               # prints "M5 smoke PASS"
```

Key env vars: `PORT`, `DB_PATH` (audit SQLite, default `audit.db`), `ROUNDS_TO_WIN` (default 1) for the coordinator; `SPELLBLADE_WS_URL` (default `ws://localhost:8000/ws`) for the client.

Inspect a running match over HTTP: `GET /health`, `GET /matches`, `GET /matches/{matchId}/events` (the replayable audit log).

## Hard invariants (don't break these)

- **The server must stay pygame-free / SDL-free.** Everything under `coordinator/`, `messaging/` (except `messaging/ws_client.py`, which is client-side transport), and `audit/` must import no pygame. `requirements-server.txt` is the *only* file installed into the server image. Shared pure-data constants live in `coordinator/action_data.py` and are re-exported by the client's `game_settings.py` — put shared constants there, not in a pygame module.
- **Single uvicorn worker only.** The `PubSubHub` registry and live match state are in-process memory, not shared across workers.
- **Authority split:** the server is authoritative for HP, hit resolution, death, and match lifecycle. The *client* is authoritative for its own position (relayed to the opponent via the coordinator). The opponent is rendered purely from snapshots.
- **The 60fps render loop never blocks on the network.** `messaging/ws_client.py::GameClient` runs a `websocket-client` daemon thread that fills a shared latest-snapshot buffer + lifecycle/attack queues; the loop reads those each frame (`client.py`).
- **The client never decides screen transitions.** It reacts to `lifecycle_event` messages from the coordinator (`handle_lifecycle` in `client.py`). To change flow, change the state chart, not the client.

## Architecture

Data flow (all over the WebSocket pub/sub hub):

```
client --publish--> input/lobby/global channels
  -> coordinator inbox (a hub Subscriber)
  -> Message Router (by envelope `type`)
  -> handler: Content Enricher (combat) / Aggregator -> MatchState mutation (audited)
  -> Lifecycle state chart
coordinator --publish--> snapshot + lifecycle channels -> clients
```

The single FastAPI service (`coordinator/app.py`) hosts both the WebSocket pub/sub transport and the coordinator. The coordinator subscribes its own `_Inbox` to the inbound channels — that adapter is the entry point for all gameplay.

**Messaging layer (`messaging/`), each module = one pattern:**
- `pubsub.py` — Publish-Subscribe Channel hub. Note: it *retains* the last payload per channel and replays it to new subscribers (late joiners get current state).
- `router.py` — Message Router: content-based dispatch by `type` to registered async handlers.
- `enricher.py` — Content Enricher: turns a bare `attack` (just `action_id`) into a resolved combat outcome; stamps snapshots with `seq`/timestamp. Hit resolver is injected so it has no hard coordinator import.
- `aggregator.py` — Aggregator: merges the per-client movement buffer + authoritative match state into one `world_snapshot` per tick.
- `schema.py` — versioned `Envelope` (Message Translator) + pluggable `Codec` (Strategy). `MessageType` holds all canonical `type` strings; `PROTOCOL_VERSION` is enforced on decode.
- `channels.py` — channel-key builders, namespaced per match: `spellblade/v1/<matchId>/<topic>`.
- `bus.py` — wire-frame helpers shared by the WS endpoint and coordinator.
- `ws_client.py` — **client-side** transport (`GameClient`); the one messaging module that lives on the pygame side.

**Coordinator (`coordinator/`):**
- `match_coordinator.py` — orchestrates the whole pipeline: matchmaking (pairs joins into matches of 2), routing, combat, lifecycle firing, and the per-match asyncio snapshot tick loop (~20 Hz / `tick_interval=0.05`).
- `lifecycle.py` — hand-rolled FSM (GoF State) declared as data in `TRANSITIONS` with guard predicates over a `ctx` dict. States: `LOBBY → CHARACTER_SELECT → LOADING → FIGHTING → ROUND_OVER → (CHARACTER_SELECT | MATCH_OVER)`. `PLAYER_LEFT` from any state → `MATCH_OVER`.
- `combat.py` — pure, deterministic hit resolution (facing + reach + block mitigation); `SwingTracker` enforces one hit per swing.
- `match_state.py` — the domain `MatchState` (Subject); mutations notify attached observers.
- `rules.py` / `action_data.py` — validated lookup over the shared action table (HP, reach, damage, start positions).

**Audit (`audit/`) — event sourcing:**
- `observer.py` — `AuditObserver` (GoF Observer) attaches to `MatchState`; every mutation appends one immutable event and back-fills the assigned `seq`.
- `event_store.py` — append-only SQLite (WAL). `seq` is monotonic per match, derived from stored max (survives restart). `replay()` folds events back into a `MatchState` at any point. **Audit granularity: discrete game-state mutations only — never the ~30 Hz movement stream.**

**Client rendering (`client.py`, `game.py`, `state.py`, `player.py`, `anim.py`, `hero.py`, `actions.py`):** screen/state machine, animation, and input. `state.py` is a per-player animation state machine; `game.py` holds the screen states (title/select/loading/fight/over).

## Reference docs

- `README.md` — install / run / controls / startup sequence.
- `DETAILS.md` — the full EIP/GoF write-up, channel keys, message schema, and lifecycle state chart (the authoritative design doc).
- `requirements.md`, `sprints/` — original requirements and sprint notes.
