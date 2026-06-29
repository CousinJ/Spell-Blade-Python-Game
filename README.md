# Spell Blade

A 2-player pygame fighting game with a **server-authoritative, event-sourced**
backend. Clients connect over a **WebSocket publish/subscribe** channel to a
headless **Match Coordinator** (FastAPI) that owns combat, HP, the match
lifecycle, and an append-only audit log. No external broker — the coordinator
*is* the broker.

> This README covers how to install, start, and play locally. A deeper
> architecture/EIP write-up lives in `DETAILS.md` (and the `sprints/` docs).

---

## How it fits together

```
client.py (pygame)  --player_state / attack-->  ┌── Match Coordinator (FastAPI, one uvicorn worker) ──┐
                                                 │  WebSocket pub/sub hub (channel registry + fan-out) │
client.py (pygame)  <--world_snapshot /          │  Router → Enricher(+combat) → Aggregator            │
                       lifecycle_event-------     │  drives the match lifecycle state chart             │
                                                 │  appends every mutation to SQLite (audit log)        │
                                                 │  HTTP /health, /matches, /matches/{id}/events        │
                                                 └──────────────────────────────────────────────────────┘
```

- **The server is authoritative** for HP, hit resolution, death, and the match
  lifecycle. The **client is authoritative for its own position** (relayed to
  the opponent through the coordinator). The opponent is rendered from snapshots.
- **The render loop never blocks on the network.** A background
  `messaging/ws_client.py::GameClient` (a `websocket-client` daemon thread) fills
  a shared latest-snapshot buffer and lifecycle/attack queues; the 60fps loop
  reads those each frame.

---

## Integration patterns (EIP)

The messaging layer is built around named **Enterprise Integration Patterns** —
each module under `messaging/` implements one pattern (its docstring names it),
and the coordinator wires them into a pipeline. The full write-up is in
`DETAILS.md`; this is the quick map:

| EIP | File | What it does here |
|-----|------|-------------------|
| **[Publish-Subscribe Channel](https://www.enterpriseintegrationpatterns.com/patterns/messaging/PublishSubscribeChannel.html)** | `messaging/pubsub.py` (`PubSubHub`) | The transport core: maps channel keys → subscriber sets and fans each published payload out to all subscribers. *Retains* the last payload per channel and replays it to late joiners. |
| **[Message Router](https://www.enterpriseintegrationpatterns.com/patterns/messaging/MessageRouter.html)** | `messaging/router.py` (`MatchRouter`) | Content-based dispatch of each inbound envelope to a registered async handler keyed by its `type` (handlers registered in `coordinator/match_coordinator.py`). |
| **[Content Enricher](https://www.enterpriseintegrationpatterns.com/patterns/messaging/DataEnricher.html)** | `messaging/enricher.py` (`Enricher`) | Stamps outbound snapshots with a monotonic `seq` + server timestamp, and turns a bare `attack` (just an `action_id`) into a fully resolved combat outcome using live positions/HP, the action table, and the server clock. |
| **[Aggregator](https://www.enterpriseintegrationpatterns.com/patterns/messaging/Aggregator.html)** | `messaging/aggregator.py` (`SnapshotAggregator`) | Correlates the live per-client movement buffer with authoritative match state (hp/alive/hero/stamina) into one `world_snapshot` payload per tick. |
| **[Message Translator](https://www.enterpriseintegrationpatterns.com/patterns/messaging/MessageTranslator.html)** | `messaging/schema.py` (`Envelope`) | Converts between in-memory dicts and the versioned JSON wire format, enforcing `PROTOCOL_VERSION` on decode so components never exchange raw objects. (Also GoF **Strategy**: a pluggable `Codec`.) |
| **Channel naming** | `messaging/channels.py` | Builds per-match namespaced channel keys `spellblade/v1/<matchId>/<topic>` so traffic never crosses matches on the shared transport. |

The **Channel Adapters** that bridge the hub to each side are
`_Inbox` (`coordinator/match_coordinator.py`, funnels fanned-out frames into the
coordinator) and `WsSubscriber` (`coordinator/app.py`, bridges a FastAPI
WebSocket to the hub's `Subscriber` protocol); `messaging/bus.py` wraps an
envelope in the shared `{op, channel, message}` transport frame.

---

## GoF design patterns

| GoF | Where | Role |
|-----|-------|------|
| **State** | `coordinator/lifecycle.py` (match phases), `state.py` (per-player animation), `game.py` (screen states) | Three independent finite-state machines that swap behavior by state object/value. The match FSM is *table-driven* (transitions declared as data); the animation and screen FSMs use one class per state. |
| **Observer** | `coordinator/match_state.py` (Subject) + `audit/observer.py` (Observer) | `MatchState` notifies attached observers on every mutation (`attach`/`_notify`); `AuditObserver` persists each event and back-fills its `seq`. This is what drives the event-sourced audit log. |
| **Strategy** | `messaging/schema.py` (`Codec`/`JsonCodec`) and `messaging/enricher.py` (injected hit resolver) | The wire format is swappable behind `encode`/`decode` without touching call sites; the combat resolver is injected into `Enricher` (defaults to `coordinator.combat.resolve_hit`), keeping the messaging layer free of a hard coordinator import. |

Bonus: the **Adapter** pattern appears as `_Inbox` and `WsSubscriber` (above),
which adapt the coordinator and a FastAPI WebSocket to the hub's `Subscriber`
protocol.

---

## Requirements

- Python 3.11+
- Two dependency sets (the client needs pygame; the server must stay pygame-free):

```bash
pip install -r requirements.txt          # client: pygame-ce, websocket-client
pip install -r requirements-server.txt   # server: fastapi, uvicorn, websockets
```

---

## Play the deployed demo (easiest)

A coordinator is already running in the cloud, so you only need the **client**:

```bash
pip install -r requirements.txt   # client deps: pygame-ce, websocket-client
python client.py
```

That's it — the client connects to the deployed coordinator by default
(`wss://spell-blade-python-game-production.up.railway.app/ws`). Press **SPACE**
on the title to enter the lobby; the first two players are paired into a match
and anyone else waits until a slot opens. Requires **Python 3.11+**.

Check the live server any time:
`https://spell-blade-python-game-production.up.railway.app/health`

---

## Run it locally (no deployment)

Everything runs on `localhost`. You need **three terminals**: one coordinator
and two game clients. Each client opens its own window and needs keyboard focus.

**Terminal 1 — start the coordinator:**

```bash
python -m coordinator.run_server
```

It serves the WebSocket at `ws://localhost:8000/ws` plus the HTTP routes below.
Leave it running. (Set `PORT` to change the port; `DB_PATH` to change where the
audit DB is written — defaults to `audit.db` in the working directory.)

**Terminals 2 and 3 — start two clients:**

```bash
python client.py
```

The client defaults to the **deployed** coordinator, so for local play point it
at your own server first:
`SPELLBLADE_WS_URL=ws://localhost:8000/ws python client.py` (use the matching
port if you changed it).

### Controls

| Keys      | Action                                  |
|-----------|-----------------------------------------|
| `W A S D` | pick a hero (Fire / Magic / Forest / Ice) on the select screen |
| `A` / `D` | move left / right                       |
| `↑` Up    | jump attack (heaviest, most stamina)    |
| `←` Left  | strike 1                                |
| `→` Right | strike 2                                |
| `↓` Down  | sweep                                   |
| `Space`   | block                                   |
| `Esc`     | quit                                    |

All heroes share the **same four-attack moveset** (bound to the arrow keys) with
identical stats; every hero animation is drawn from `assets/effect_sheets/`. Each
attack costs **stamina** (shown as the amber bar under each health bar): you can't
attack without enough, stamina regenerates over time but **not while blocking**,
and **blocking a hit drains the defender's stamina** and plays a parry. The
standardized action/stamina table lives in `coordinator/action_data.py`.

---

## Starting logic (what happens when you launch a client)

The client never decides screen transitions on its own — it **reacts to lifecycle
events** published by the coordinator. The startup sequence:

1. **Connect + join.** On launch, `GameClient` opens the WebSocket, subscribes to
   its private inbox, and publishes a `join` on the global lobby. The coordinator
   places it in any match with < 2 players (creating one if needed) and replies
   `joined` with the assigned `matchId` and `actor` (`p1` or `p2`). The client
   then subscribes to that match's `snapshot`, `lifecycle`, and `lobby` channels
   plus the opponent's input channel.
2. **Wait for an opponent.** Both clients sit on the **title screen** until two
   players are in the match. When the second joins, the coordinator transitions
   `LOBBY → CHARACTER_SELECT` and publishes it; both clients switch to the
   **hero-select screen**.
3. **Pick a hero.** Selecting publishes `hero_select` on the lobby. Once both
   heroes are chosen the server transitions to `LOADING`; clients load their own
   and the opponent's sprite sheets, then publish `assets_loaded`.
4. **Fight.** When both report loaded, the server transitions to `FIGHTING` and
   starts publishing ~20 Hz world snapshots. Movement is local and relayed;
   attacks are sent as discrete events and resolved server-side (distance vs
   reach, facing, block, **stamina cost**). HP, death, and stamina come back in
   snapshots (stamina is server-authoritative but, like position, is kept off the
   audit log).
5. **Match over.** When a player's HP hits 0 the server transitions
   `FIGHTING → ROUND_OVER → MATCH_OVER` (default best-of-1) and publishes a final
   snapshot naming the winner; clients show the **VICTORY/DEFEAT** screen.

The channel keys and message schema are documented in `DETAILS.md`; the lifecycle
state chart is below.

---

## Match-lifecycle state chart

The match workflow is governed by an explicit, **hand-rolled finite-state
machine** (`coordinator/lifecycle.py`, `LifecycleMachine`) — GoF **State**. It is
declared **as data** in `TRANSITIONS`, so it can be documented, introspected
(`transitions_table()`), and unit-tested directly. **Guards** are predicates over
a plain `ctx` dict the coordinator supplies on each fire. Every transition is
published on the match's `…/lifecycle` channel **and** written to the audit log.

**States:** `LOBBY · CHARACTER_SELECT · LOADING · FIGHTING · ROUND_OVER · MATCH_OVER`

| From | Event | Guard | To |
|------|-------|-------|----|
| `LOBBY` | `PLAYER_JOINED` | both players connected | `CHARACTER_SELECT` |
| `CHARACTER_SELECT` | `HERO_SELECTED` | both heroes chosen | `LOADING` |
| `LOADING` | `ASSETS_LOADED` | both clients report loaded | `FIGHTING` |
| `FIGHTING` | `PLAYER_DIED` | a player's hp ≤ 0 | `ROUND_OVER` |
| `ROUND_OVER` | `REMATCH` | both request rematch **and** `rounds_won < N` | `CHARACTER_SELECT` |
| `ROUND_OVER` | `MATCH_DECIDED` | a player's `rounds_won == N` | `MATCH_OVER` |
| *any* | `PLAYER_LEFT` | a player's WebSocket disconnects | `MATCH_OVER` |

`N` is the best-of-`N` round target (`ROUNDS_TO_WIN`, default 1). The wildcard
`PLAYER_LEFT` transition fires from **any** state, so a disconnect always ends the
match (the remaining player wins by forfeit).

---

## Inspect a running match (HTTP)

While the coordinator is up:

```bash
curl http://localhost:8000/health                     # liveness + active match count
curl http://localhost:8000/matches                    # live matches, phase, players, HP
curl http://localhost:8000/matches/<matchId>/events   # append-only audit log (replayable history)
```

The same routes are live on the **deployed** coordinator — no local server needed:

```bash
BASE=https://spell-blade-python-game-production.up.railway.app
curl -s "$BASE/matches"                      # list every match in the deployed audit log
curl -s "$BASE/matches/<matchId>/events"     # full event trail for one match
```

You can also just open `…/matches/<matchId>/events` in a browser.

> **Windows PowerShell:** `curl` is an alias for `Invoke-WebRequest`, which
> doesn't understand `-s` and will prompt you for a `URI`. Use the real curl
> (`curl.exe -s <url>`) or PowerShell-native
> `Invoke-RestMethod "<url>"` instead.

### Audit trail / event sourcing

Persistence is an **append-only SQLite event store** (`audit/event_store.py`, WAL
mode) — the system is **event-sourced**. Every *discrete authoritative state
mutation* writes one immutable row: `join` · `leave` · `hero_select` · `damage` ·
`hp_change` · `transition` · `round_result`. (The ~30 Hz movement stream is
relayed via `player_state` and deliberately **never** logged, to keep the log
meaningful and off the hot path.)

- Each mutation flows through `MatchState` (the Observer **Subject**); the
  `AuditObserver` persists it and back-fills a **monotonic per-match `seq`** that
  is derived from the stored max, so it survives a coordinator restart.
- Events carry **absolute post-values**, and the *same* reducer (`MatchState.apply`)
  serves both the live path and replay — so `replay(match_id, upto_seq)` folds
  events back into a fresh `MatchState` to reconstruct the **exact game state at
  any point in time** (and to recover a live match after a crash).

The result: **every game-state mutation is fully reconstructable** from the log,
inspectable live via `GET /matches/{matchId}/events`.

---

## Perfect Framework concerns addressed

- **Audit trails / point-in-time history** — append-only event store with
  deterministic replay (see above, `audit/`).
- **Reliability / fault-tolerance** — a single WebSocket gives ordered, reliable
  delivery; `seq` survives restarts (crash recovery via replay); a disconnect
  publishes `PLAYER_LEFT → MATCH_OVER`; one bad message can't kill the inbox
  (route handlers are wrapped).
- **Correctness** — server-authoritative combat/stamina with deterministic, pure
  hit resolution (`coordinator/combat.py`) and one-hit-per-swing dedupe.
- **Testability** — pygame-free server core; pure combat + deterministic replay;
  the hub and pipeline are unit-tested without a real socket (`tests/`).

---

## Tests

```bash
python -m pytest tests/ -q          # server core: schema, event store, combat, lifecycle, pipeline, pubsub
```

**Headless end-to-end** (no windows; drives a full match through the real client
transport). Start the coordinator first, then:

```bash
python scripts/m5_smoke.py          # two GameClients auto-pair → LOBBY…→ MATCH_OVER, prints "M5 smoke PASS"
```

---

## Layout

| Path | What |
|---|---|
| `client.py` | pygame client + 60fps loop |
| `game.py`, `state.py`, `player.py`, `anim.py`, `hero.py`, `actions.py` | client rendering, screens, animation, input |
| `messaging/ws_client.py` | client WebSocket transport (`GameClient`) |
| `messaging/` | pub/sub hub, router, enricher, aggregator, schema (EIP components) |
| `coordinator/` | match coordinator, lifecycle state chart, combat/rules, FastAPI app |
| `audit/` | SQLite event store, observer, replay CLI |
| `scripts/` | `m5_smoke.py` (headless end-to-end smoke test) |
| `game_settings.py` / `coordinator/action_data.py` | shared constants (HP, start positions, action table) |
