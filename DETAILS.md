# Spell Blade — How It All Works (DETAILS)

A deep-dive companion to the [README](README.md). This document explains how the
pieces fit together end-to-end: the messaging architecture, the Enterprise
Integration Patterns (EIPs) and GoF patterns, the match-lifecycle state chart,
the combat/stamina model, and the event-sourced audit trail.

> **One-line summary:** Two thin pygame clients talk to one headless **Match
> Coordinator** (FastAPI) over a **WebSocket publish/subscribe** channel. The
> coordinator *is* the message broker, runs an EIP pipeline, drives a match
> state chart, and appends every meaningful mutation to an append-only SQLite
> **audit log** that can be replayed to reconstruct any match at any point.

---

## 1. Big picture

```
  ┌──────────────────────────┐                         ┌────────────────────────────────────────────────────┐
  │  client.py  (pygame, P1)  │  ── player_state ──▶    │            Match Coordinator (FastAPI)             │
  │  60 fps render loop       │  ── attack ────────▶    │                                                    │
  │  GameClient (WS thread)   │  ◀── world_snapshot ─   │  WebSocket /ws  =  Publish-Subscribe hub           │
  └──────────────────────────┘  ◀── lifecycle_event ─  │     │  (channel registry + fan-out + retained)    │
                                                        │     ▼                                              │
  ┌──────────────────────────┐                         │  Router ─▶ Enricher(+combat) / Aggregator          │
  │  client.py  (pygame, P2)  │  ── player_state ──▶    │     │                                              │
  │  ...                      │  ── attack ────────▶    │     ▼                                              │
  │                           │  ◀── world_snapshot ─   │  MatchState (Subject) ──notify──▶ AuditObserver    │
  └──────────────────────────┘  ◀── lifecycle_event ─  │     │                              └─▶ SQLite log   │
                                                        │     ▼                                              │
                                                        │  LifecycleMachine (state chart)                    │
                                                        │  HTTP: /health  /matches  /matches/{id}/events     │
                                                        └────────────────────────────────────────────────────┘
```

- **Server-authoritative** for HP, hit resolution, death, **stamina**, and the
  match lifecycle.
- **Client-authoritative** for its *own* position (relayed to the opponent
  through the coordinator). The opponent is rendered entirely from snapshots.
- **No external broker.** The coordinator hosts the pub/sub hub in process
  memory, so it must run as a **single uvicorn worker**.

---

## 2. The transport: Publish-Subscribe over WebSockets

Everything flows over one WebSocket endpoint, `ws://<host>:8000/ws`
(`coordinator/app.py`). The frame protocol is tiny JSON:

```
client → server:   {"op":"subscribe"|"unsubscribe"|"publish", "channel":"<key>", "message":<envelope>}
server → client:   {"op":"subscribed"|"message"|"error", "channel":"<key>", "message":<envelope>}
```

`messaging/pubsub.py::PubSubHub` is the broker core: a `{channel: set(subscribers)}`
registry that fans each published payload out to that channel's subscribers. It
also **retains the last payload per channel** and replays it to new subscribers,
so a late joiner immediately sees current state. Subscribers only need an async
`send(text)` and a stable `id`, which keeps the hub fully unit-testable without a
real socket.

### Channels (`messaging/channels.py`)

Logical string keys, namespaced per match so traffic never crosses matches:

| Channel | Key | Direction |
|---|---|---|
| Global lobby | `spellblade/v1/lobby` | clients → coordinator (matchmaking `join`) |
| Client inbox | `spellblade/v1/client/<clientId>/inbox` | coordinator → one client (`joined` reply) |
| Per-match lobby | `spellblade/v1/<matchId>/lobby` | hero select / assets-loaded / rematch |
| Player input | `spellblade/v1/<matchId>/input/<actor>` | client → coordinator (`player_state`, `attack`) |
| Snapshot | `spellblade/v1/<matchId>/snapshot` | coordinator → clients (`world_snapshot`) |
| Lifecycle | `spellblade/v1/<matchId>/lifecycle` | coordinator → clients (`lifecycle_event`) |

The coordinator subscribes its own `_Inbox` (a hub `Subscriber`) to the global
lobby and to each match's lobby + input channels — that adapter is the single
entry point for all gameplay messages.

### The message envelope (`messaging/schema.py`)

Every domain message is wrapped in a versioned envelope:

```json
{"v":1, "type":"attack", "matchId":"M…", "actor":"p1", "client_seq":7, "ts":…, "payload":{…}}
```

`Envelope.from_dict` enforces `PROTOCOL_VERSION` and validates shape, so a
malformed or wrong-version frame is rejected at the edge instead of corrupting
state. `MessageType` holds the canonical `type` strings (`join`, `hero_select`,
`assets_loaded`, `player_state`, `attack`, `rematch`, `joined`,
`world_snapshot`, `lifecycle_event`, `error`).

---

## 3. End-to-end message flow

```
client --publish--> input/lobby/global channel
   → PubSubHub fan-out → coordinator _Inbox.send()
   → MatchCoordinator._on_frame  (parse envelope)
   → MatchRouter.route(by type)
   → handler: _on_join / _on_hero_select / _on_assets_loaded /
              _on_player_state / _on_attack / _on_rematch
       • Enricher resolves combat (for attack)
       • Aggregator stores latest movement (for player_state)
       • MatchState mutation → notifies AuditObserver → SQLite
       • LifecycleMachine.fire(event) on phase-changing handlers
   → coordinator --publish--> snapshot + lifecycle channels → clients
```

A dedicated **asyncio task per match** publishes the aggregated world snapshot
~20 Hz (`tick_interval=0.05`) while the match is `FIGHTING`.

---

## 4. The EIP pipeline (5 patterns)

Each module names and cites its pattern in its docstring.

| EIP | Module | What it does |
|---|---|---|
| **Publish-Subscribe Channel** | `messaging/pubsub.py` | Self-hosted WebSocket channel registry + fan-out + retained last message. |
| **Message Router** | `messaging/router.py` | Content-based dispatch by envelope `type` to one registered async handler each. |
| **Content Enricher** | `messaging/enricher.py` | Stamps outbound snapshots with monotonic `seq` + server `ts`; turns a bare `attack` (just `action_id`) into a fully resolved combat outcome using live positions, the action table, and the clock. The hit resolver is injected, so the module has no hard coordinator import. |
| **Message Translator** | `messaging/schema.py` | Converts in-memory domain dicts ↔ the versioned JSON wire envelope, with a pluggable codec. |
| **Aggregator** | `messaging/aggregator.py` | Correlates two sources per actor — the live movement buffer (`player_state`) and the authoritative match state (hp/alive/hero/**stamina**) — into one `world_snapshot` per tick. |

(Citations: <https://www.enterpriseintegrationpatterns.com>.)

---

## 5. GoF design patterns (3)

| GoF | Where | Role |
|---|---|---|
| **State** | `coordinator/lifecycle.py` (match phases) and `state.py` (per-player animation states) | The match FSM and the player animation FSM both swap behavior by state object/value. |
| **Observer** | `coordinator/match_state.py` (Subject) + `audit/observer.py` (Observer) | `MatchState` notifies attached observers on every mutation; `AuditObserver` persists each one. |
| **Strategy** | `messaging/schema.py` | `Codec` is the strategy interface, `JsonCodec` the concrete strategy; the wire format can be swapped without touching call sites (`encode`/`decode`). |

---

## 6. Match-lifecycle state chart (`coordinator/lifecycle.py`)

A hand-rolled FSM declared **as data** in `TRANSITIONS`, so it can be documented,
introspected (`transitions_table()`), and unit-tested directly. Guards are
predicates over a plain `ctx` dict the coordinator supplies each fire.

**States:** `LOBBY · CHARACTER_SELECT · LOADING · FIGHTING · ROUND_OVER · MATCH_OVER`

**Events:** `PLAYER_JOINED · HERO_SELECTED · ASSETS_LOADED · PLAYER_DIED · REMATCH · MATCH_DECIDED · PLAYER_LEFT`

**Transitions & guards:**

| From | Event | To | Guard |
|---|---|---|---|
| `LOBBY` | `PLAYER_JOINED` | `CHARACTER_SELECT` | both players connected (`players_connected ≥ 2`) |
| `CHARACTER_SELECT` | `HERO_SELECTED` | `LOADING` | both heroes chosen (`heroes_selected ≥ 2`) |
| `LOADING` | `ASSETS_LOADED` | `FIGHTING` | both clients report loaded (`assets_loaded ≥ 2`) |
| `FIGHTING` | `PLAYER_DIED` | `ROUND_OVER` | some player `hp ≤ 0` |
| `ROUND_OVER` | `REMATCH` | `CHARACTER_SELECT` | both requested **and** no one reached N (`max_rounds_won < rounds_to_win`) |
| `ROUND_OVER` | `MATCH_DECIDED` | `MATCH_OVER` | a player reached N (`max_rounds_won ≥ rounds_to_win`) |
| `*` (any) | `PLAYER_LEFT` | `MATCH_OVER` | always (a player disconnected) |

`rounds_to_win` defaults to 1 (best-of-1; configurable via `ROUNDS_TO_WIN`).
Transitions are guarded inside `LifecycleMachine.fire`; an event whose guard
fails (or that isn't allowed from the current state) is a no-op, never a crash.
Each successful transition is **published** on the lifecycle channel (clients
switch screens off it) **and** written to the audit log.

**Client side:** clients never decide screen transitions themselves — they react
to `lifecycle_event` messages (`client.py::handle_lifecycle`). The per-player
animation FSM (`state.py`) is a second State machine with priority
`dead > parry > hurt > acting > blocking > running > idle`.

---

## 7. Combat, stamina & parry

The original game had no HP or hit detection; combat is a deterministic,
server-authoritative model. The single source of truth for all numbers is the
pygame-free table in **`coordinator/action_data.py`**, imported by the server
directly and by the client via `game_settings` — so the two sides can never drift.

### Standardized moveset (identical for every hero)

| Key | action_id | damage | reach (px) | stamina cost | block mitigation |
|---|---|---|---|---|---|
| `↑` Up | `jump_attack` | 26 | 190 | 34 | 0.50 |
| `←` Left | `strike_1` | 16 | 175 | 18 | 0.70 |
| `→` Right | `strike_2` | 20 | 175 | 24 | 0.60 |
| `↓` Down | `sweep` | 14 | 210 | 20 | 0.70 |
| `Space` | `block` | 0 | — | 0 | 1.00 |

`A`/`D` move; all hero animations are drawn from `assets/effect_sheets/`.

### Hit resolution (`coordinator/combat.py::resolve_hit`)

On an `attack` event the server checks, in order: is it an attack? is the target
alive? is the attacker **facing** the target (direction toward target's x)? is
the target within the action's **reach**? If blocking, damage is reduced by
`block_mitigation`. `SwingTracker` enforces **one hit per swing**, keyed by
`(actor, client_seq)`, so a duplicated frame can't double-hit.

### Stamina & parry (`coordinator/match_coordinator.py`)

- Each attack **costs stamina**; the client gates locally and the server
  re-checks authoritatively — an attack you can't afford simply never fires.
- Stamina **regenerates** ~18/sec, **paused while a player holds block**.
- A **blocked hit drains the defender's stamina** (`BLOCK_STAMINA_DRAIN`) and
  increments a per-actor `blocks_taken` counter. The client watches that counter
  rise and plays the **parry** animation (suppressing the hurt clip for that hit).
- **Design note:** stamina and the parry counter are *fast/continuous* like
  player position, so they are **not** written to the audit log — they live on
  the live `MatchContext` and are mirrored to clients inside the world snapshot.
  This keeps the audit granularity at "discrete game-state mutations only."

---

## 8. Audit trail / event sourcing (`audit/`)

Every meaningful mutation goes through a **command method** on `MatchState`
(`join`, `select_hero`, `apply_damage`, `set_hp`, `transition`, `round_result`).
Each command calls `_emit`, which:

1. builds one immutable **event** dict,
2. **notifies** observers — `AuditObserver` appends it to the `EventStore` and
   back-fills the assigned `seq`,
3. **applies** it via `MatchState.apply` — the *same reducer* used by replay.

Because the live path and the replay path share one reducer, and events carry
absolute post-values, **every mutation is exactly reconstructable**:

```python
MatchState.from_events(match_id, store.events_for(match_id, upto=<seq>))  # point-in-time
```

`EventStore` is append-only SQLite (WAL mode). `seq` is **monotonic per match**,
derived from the stored max, so it survives process restarts (crash recovery).
Audit granularity is deliberate: discrete mutations only — never the ~20–30 Hz
movement/stamina stream. Inspect it live over HTTP:

```
GET /matches/<matchId>/events     # the replayable history
```

---

## 9. The client render loop & authority (`client.py`)

The 60 fps loop never blocks on the network. A background
`messaging/ws_client.py::GameClient` (a `websocket-client` daemon thread) fills a
shared latest-snapshot buffer plus lifecycle/attack queues. Each frame the loop:

1. drains lifecycle events → switches screens (coordinator-authoritative),
2. applies the latest world snapshot → opponent position + authoritative HP +
   stamina + parry detection,
3. renders the opponent's relayed attack swings,
4. reads local input → publishes `player_state` (30 Hz) and `attack` events,
5. renders.

The local player stays client-authoritative for position; HP, death, stamina,
parry, and lifecycle all come from the server.

---

## 10. Perfect Framework concerns addressed

- **Audit trails / point-in-time history** — append-only event store with
  deterministic replay (`audit/`).
- **Reliability / fault-tolerance** — a single WebSocket gives ordered, reliable
  delivery; `seq` survives restarts (crash recovery via replay); a disconnect
  publishes `PLAYER_LEFT` → `MATCH_OVER`; one bad message can't kill the inbox
  (handlers are wrapped).
- **Correctness** — server-authoritative combat/stamina with deterministic,
  pure resolution (`combat.py`) and one-hit-per-swing dedupe.
- **Testability** — pygame-free server core; pure combat + deterministic replay;
  the hub and pipeline are unit-tested without a real socket (`tests/`).

---

## 11. Run & verify

```bash
# server (single worker)
python -m coordinator.run_server

# two clients (separate terminals/machines)
python client.py

# tests (pygame-free server core)
python -m pytest tests/ -q

# headless end-to-end (start coordinator first)
python scripts/m5_smoke.py        # → "M5 smoke PASS"
```

See the [README](README.md) for controls, install, and environment variables;
`plan.md` for the original design write-up and deployment notes.
