# Spell Blade → Sprint 2 (Messaging Patterns) — Implementation Plan

## Context
The repo is a working 2-player pygame fighting game ("Spell Blade") that syncs state over **TCP + pickle** with a one-round-trip-per-frame `Network.send()` call (`client.py:37`). The server (`server.py`) just echoes the opponent's pickled `Player`. There is **no health/damage** (damage values exist in `actions.py` but are never applied), **no persistence**, and the two "state machines" (`state.py`, `game.py` screens) are implicit.

Sprint 2 requires a multi-component, messaging-based system: ≥3 EIPs (one **must** be Publish-Subscribe via MQTT **or WebSockets** — requirements.md line 16), an explicit state chart over a non-trivial workflow, and a persistence layer with a reconstructable audit trail. This plan evolves the game into a **WebSocket publish-subscribe, server-authoritative, event-sourced** system.

**Transport decision:** The class MQTT broker `mqtt.uvucs.org` is unreachable (DNS resolves to 35.174.139.129 but ports 1883/8883/9001 are all closed). The requirement explicitly allows **WebSockets** as the pub-sub transport, so we implement our own **Publish-Subscribe Channel over WebSockets inside the coordinator** — no external broker. (HiveMQ Cloud MQTT is the documented fallback if a literal MQTT broker is ever required.)

**Confirmed scope:** 4 required EIPs + 1 bonus (Aggregator) · no LLM component · solo submission · WebSocket pub-sub (self-hosted in the coordinator) · deploy coordinator to a Railway-class PaaS (Docker) exposing the WebSocket endpoint **and** a read-only HTTP health/spectator endpoint on the same service.

Useful discovery: `anim.py` already defines `hurt_anim` (idx 23) and `death_anim` (idx 24), so adding HP/death needs **no new art**.

---

## Target architecture
Replace TCP+pickle entirely with a **WebSocket pub/sub channel hosted inside the Match Coordinator** (FastAPI). Each client opens one persistent WebSocket to the coordinator's public `wss://` URL, subscribes to its match's channels, and publishes input. The coordinator owns the Pub-Sub registry (`{channel: set(connections)}`), runs the EIP pipeline, drives the match state chart, and writes an append-only audit log. No external broker — the coordinator *is* the broker. Clients stay thin: publish input, render authoritative snapshots.

```
client (pygame, websockets) --player_input--> ┌─ Match Coordinator (FastAPI, single uvicorn worker) ─┐
                                              │  WebSocket Pub-Sub channel registry                  │
                                              │  Translator → Router → Enricher(+combat) → Aggregator│
client (pygame, websockets) <--snapshot /     │  ├─ drives lifecycle state chart                     │
                                lifecycle----  │  └─ appends every mutation to SQLite store (Observer)│
                                              │  + HTTP /health, /matches, /matches/{id}/events       │
                                              └──────────────────────────────────────────────────────┘
```
Because clients connect *out* to the coordinator's HTTPS/WSS URL, there is no inbound-port or NAT problem on the client side, and only the coordinator needs a public URL (which the PaaS provides).

**Server tick:** the coordinator runs one `asyncio` task per match at ~20–30 Hz that aggregates both players' latest reported state into a single `world_snapshot` and publishes it on the snapshot channel. Combat is resolved **event-driven** (on each `attack` message), not on the tick.

---

## New module layout
- `messaging/`
  - `pubsub.py` — `PubSubHub`: WebSocket channel registry (`subscribe`, `unsubscribe`, `publish(channel, msg)` fan-out, send-latest-on-subscribe). **EIP: Publish-Subscribe Channel** (server-side, self-hosted).
  - `ws_client.py` — client-side WebSocket transport using **`websocket-client`** (sync `WebSocketApp.run_forever` in a daemon thread + callbacks — integrates cleanly with the synchronous pygame loop; the server side uses FastAPI/`websockets`).
  - `aggregator.py` — `SnapshotAggregator`: correlate both players' latest reported state into one `world_snapshot` per tick. **EIP: Aggregator (bonus 5th).**
  - `schema.py` — versioned JSON envelope + encode/decode codec (domain object/dict ↔ wire JSON). **EIP: Message Translator** and **GoF: Strategy** (pluggable codec).
  - `channels.py` — channel-key builders (per-match UUID namespacing).
  - `router.py` — `MatchRouter`: dispatch incoming messages by `type`/`matchId`/`actor`. **EIP: Message Router.**
  - `enricher.py` — `Enricher`: add server `ts` + monotonic `seq` + hero metadata; on `attack` messages run event-based combat resolution → apply damage → HP. **EIP: Content Enricher.**
- `coordinator/`
  - `lifecycle.py` — hand-rolled match state chart (states/events/transitions/guards). **GoF: State.**
  - `action_data.py` — **zero-import pure-data** table: `action_id → {damage, reach, frames, block_mitigation}`. Imported by BOTH the client's `actions.py` and the server's `rules.py` so the single source of truth never pulls in pygame. (`reach`/`block_mitigation` are **new** values — none exist today.)
  - `combat.py` — pure, pygame-free hit-resolution (distance vs `reach`, facing, block mitigation, one-hit-per-swing) over `action_data.py`. Easy to unit test.
  - `rules.py` — server-side action lookup built on `action_data.py` (never imports `actions.py`/`hero.py`/`anim.py`, which all transitively import pygame).
  - `match_state.py` — authoritative per-match state (players, HP, phase). **Subject** in the Observer pattern: `attach(observer)` / `notify(event)` on every mutation.
  - `match_coordinator.py` — wires PubSub→Router→Enricher→state chart→audit; publishes snapshots. **Pygame-free.**
  - `app.py` — FastAPI app: `WebSocket /ws` endpoint (the pub-sub transport) + HTTP `/health`, `/matches`, `/matches/{id}/events` (read-only audit view). Launches the coordinator on startup.
  - `run_server.py` — entrypoint: `uvicorn app:app --host 0.0.0.0 --port $PORT` (single worker). Replaces `server.py`.
- `audit/`
  - `event_store.py` — SQLite append-only event sourcing + `replay(match_id, upto_seq)`, behind a small interface (swap to Postgres later if needed).
  - `observer.py` — **GoF: Observer**; subscribes to mutations and writes each as an immutable event.
  - `replay_cli.py` — CLI to reconstruct any point-in-time state from the log.
- Deploy: `Dockerfile` (server image, **no pygame**), `requirements-server.txt` (websockets stack), `.dockerignore`, `railway.json`/`fly.toml` (platform config).
- Root: `requirements.txt` (client, includes pygame), updated `README.md`, `sprints/sprint-2-reflection.md`.

## Changed existing files
- `network.py` → replaced by client-side WebSocket transport (`messaging/ws_client.py`; keep a thin `Network` shim if it minimizes `client.py` churn).
- `client.py` → replace synchronous `p2 = n.send(p)` with: publish local input/state each frame; read opponent state from a **shared latest-snapshot buffer** filled by the `websocket-client` daemon-thread callback; drain a `queue.Queue` of lifecycle events to switch screens. No network blocking in the 60fps loop; no pygame calls inside socket callbacks. The **local player stays client-authoritative for position** (keep `p.move(dt)`); the opponent renders from snapshots.
- `player.py` → add `hp`, `max_hp`, `alive`, and `to_dict()/from_dict()` (no more pickling across the wire).
- `state.py` → add `HurtState` and `DeadState` (wired to existing `hurt_anim`/`death_anim`).
- `game.py` → fill `OverScreen` (winner display + rematch), draw HP bars, and switch screens off coordinator `lifecycle_event`s instead of local guesses.

---

## Requirement → exact satisfier (for the README + grader)
| Requirement | Where |
|---|---|
| **EIP 1 – Publish-Subscribe Channel** | `messaging/pubsub.py` (self-hosted WebSocket channel registry + fan-out) |
| **EIP 2 – Message Router** | `messaging/router.py::MatchRouter` |
| **EIP 3 – Content Enricher** | `messaging/enricher.py::Enricher` (ts, seq, hero meta, resolved combat) |
| **EIP 4 – Message Translator** | `messaging/schema.py` (domain object/dict ↔ versioned JSON envelope) |
| **EIP 5 – Aggregator (bonus)** | `messaging/aggregator.py::SnapshotAggregator` (both players → one `world_snapshot`/tick) |
| **State chart** | `coordinator/lifecycle.py` (documented below) |
| **Persistence + point-in-time audit** | `audit/event_store.py` (append-only, `replay()`) |
| **GoF 1 – State** | `state.py` + `coordinator/lifecycle.py` |
| **GoF 2 – Observer** | `match_state.py` is the Subject (`attach`/`notify`); `audit/observer.py` is an Observer that writes each notified mutation as an event |
| **GoF (margin) – Strategy** | `messaging/schema.py` codec |
| **Perfect concerns (≥3)** | Audit Trails (event store); Reliability/Fault-tolerance (ordered reliable WS delivery + crash recovery via replay + WS disconnect → `PLAYER_LEFT`); Correctness (server-authoritative combat); Testability (pure `combat.py` + deterministic replay) — *confirm exact PERFECT acronym from class materials* |

---

## Channel hierarchy (logical pub-sub channel keys, per-match UUID namespacing)
```
spellblade/v1/<matchId>/lobby            # joins / hero selection
spellblade/v1/<matchId>/input/<actor>    # per-player input (actor = p1|p2)
spellblade/v1/<matchId>/snapshot         # authoritative world snapshot (coordinator → clients)
spellblade/v1/<matchId>/lifecycle        # state-chart transitions (coordinator → clients)
```
Channels are logical keys in `PubSubHub`, sent inside each WS frame's envelope (`{"channel": ..., ...}`); a single WebSocket per client multiplexes all channels. A WebSocket connection is already ordered + reliable, so no QoS needed; the client still drops stale snapshots using the monotonic `seq` as a guard.

**Matchmaking handshake** (replaces the unbounded `currentPlayer` counter in `server.py`, which would index-error on a 3rd client): a new client publishes `join` on a well-known lobby; the coordinator places it in any match with < 2 players (creating one — `matchId = uuid4()` — if none), then replies `joined` with that client's `matchId` + assigned `actor` (`p1`/`p2`). The client uses the returned `matchId` for all subsequent channels. Match capacity is 2; a 3rd join opens a new match.

## JSON message schema
Common envelope: `{ "v":1, "type":..., "matchId":..., "actor":..., "client_seq":..., "ts":... }`
- `player_state` (movement, ~30 Hz, client-authoritative position — relayed, **not** audited per-frame): `{ x, direction, moving, is_blocking, state }`.
- `attack` (discrete event, drives combat): `{ action_id }` — stable string keyed into `action_data.py` server-side. Server resolves the hit once (distance vs `reach`, facing, block) and applies damage.
- `hero_select`: `{ hero }`; `assets_loaded`: `{}`; `rematch`: `{}` — lobby/lifecycle inputs.
- `world_snapshot` (aggregated/enriched, server→clients): `{ seq, server_ts, phase, players:[{actor, x, hp, alive, state, action_id}], winner|null }`.
- `lifecycle_event`: `{ from, event, to, server_ts }`.

---

## Combat & authority model (new design — none of this exists today)
The current game has **no HP, no hitboxes, no hit detection**, and attack progress (`frame_index`) lives only in client-side animation code (`anim.py`). So combat must be defined from scratch:
- **Authority split:** position is **client-authoritative** (each client owns its own `x`, relayed through the coordinator); the server is **authoritative for HP, hit resolution, death, and lifecycle**. This mirrors the existing "send my player / receive opponent" model and avoids porting movement physics server-side.
- **Event-based hit resolution:** on an `attack` event the server checks `abs(attacker.x - target.x) <= action_data[action_id].reach`, correct facing (`attacker.direction` toward target), and `not target.is_blocking` (or apply `block_mitigation`); if it lands, subtract `damage` from `target.hp` **once per swing** (dedupe by attack id). No frame-accurate active-window needed for the demo.
- **New data required:** `reach` and `block_mitigation` per action in `action_data.py` (today only `damage`/frames exist). Movement-speed/HP constants go in `game_settings.py`.

## Match-lifecycle state chart (`coordinator/lifecycle.py`)
**States:** `LOBBY`, `CHARACTER_SELECT`, `LOADING`, `FIGHTING`, `ROUND_OVER`, `MATCH_OVER`.

| From | Event | Guard | To |
|---|---|---|---|
| LOBBY | PLAYER_JOINED | both players connected | CHARACTER_SELECT |
| CHARACTER_SELECT | HERO_SELECTED | both heroes chosen | LOADING |
| LOADING | ASSETS_LOADED | both clients report loaded | FIGHTING |
| FIGHTING | PLAYER_DIED | a player hp ≤ 0 | ROUND_OVER |
| ROUND_OVER | REMATCH | both request rematch & rounds_won < N | CHARACTER_SELECT |
| ROUND_OVER | MATCH_DECIDED | a player rounds_won == N | MATCH_OVER |
| any | PLAYER_LEFT | a player's WebSocket disconnects | MATCH_OVER |

Each transition is published on `…/lifecycle` **and** written to the audit log. (Document this exact table in the README; "best-of-N" N is an open decision — default N=1 for a single round if time is short.)

## Audit trail / event store (`audit/event_store.py`)
SQLite, append-only — **event sourcing**:
```sql
CREATE TABLE events (
  id        INTEGER PRIMARY KEY AUTOINCREMENT,
  match_id  TEXT NOT NULL,
  seq       INTEGER NOT NULL,      -- monotonic per match
  ts        REAL NOT NULL,
  type      TEXT NOT NULL,         -- damage | hp_change | hero_select | transition | round_result | join | leave
  actor     TEXT,                  -- p1 | p2 | system
  payload   TEXT NOT NULL          -- JSON
);
CREATE UNIQUE INDEX ux_events_match_seq ON events(match_id, seq);
```
**Audit granularity:** a "mutation" is a *discrete authoritative state change* (damage dealt, HP change, hero selected, lifecycle transition, round/match result, join/leave) — **not** the ~30 Hz movement stream (relayed via `player_state`, never logged) to avoid bloating the log and stalling on SQLite writes. Enable WAL mode. This still makes every game-state mutation reconstructable.
Every audited mutation = one immutable row. **Point-in-time reconstruction:** `replay(match_id, upto_seq)` folds events in `seq` order into a fresh `MatchState`, yielding the exact game state at any past moment. The same function recovers a live match after a coordinator crash. `replay_cli.py` exposes it for the demo.

---

## Milestones (each independently shippable & testable)
Ordered so every milestone produces something you can run/verify on its own. M1–M3 are pure modules with unit tests (no network, no pygame); M4 integrates them into a headless server; M5 reconnects the game; M6–M7 ship it. M1, M2, M3 have no dependencies on each other and could be done in any order or in parallel.

### M0 — Scaffolding & deps  *(~½ day)*
- Create package dirs (`messaging/`, `coordinator/`, `audit/`, `sprints/`); `__init__.py`s.
- `requirements-server.txt` (`fastapi`, `uvicorn[standard]`, `websockets`); `requirements.txt` (client: `pygame-ce`, `websocket-client`); `pip install`.
- **Done when:** both envs install clean; `import` smoke test of empty packages passes.

### M1 — Messaging foundation (transport)  *(~1 day)*
- `schema.py` (versioned envelope + codec, **GoF Strategy / Message Translator**), `channels.py`, `pubsub.py` (`PubSubHub`), minimal FastAPI `WebSocket /ws`.
- **Done when:** two scratch `websocket-client` scripts subscribe to a channel and one's publish is fanned out to the other through a locally-run hub; schema round-trip unit test passes.

### M2 — Persistence & audit  *(~1 day)*
- `audit/event_store.py` (SQLite append-only + `replay()`, WAL), `MatchState` as **Subject** (`attach`/`notify`), `audit/observer.py` as **Observer**, `replay_cli.py`.
- **Done when:** unit test feeds synthetic mutations through `notify` → rows persisted → `replay(match_id, upto_seq)` reconstructs the exact state at an arbitrary point.

### M3 — Game-rules engine (pygame-free core)  *(~1–1.5 days)*
- `coordinator/action_data.py` (zero-import data: damage/reach/frames/block_mitigation), `rules.py`, `combat.py` (event-based hit resolution), `lifecycle.py` (state chart).
- **Done when:** `combat.py` unit tests cover reach/facing/block/one-hit dedupe; `lifecycle.py` tests accept valid and reject invalid transitions and enforce guards. **No pygame import anywhere in this milestone.**

### M4 — EIP pipeline + coordinator (headless server)  *(~1.5–2 days)*
- `messaging/router.py`, `enricher.py`, `aggregator.py`; `coordinator/match_coordinator.py` (wires PubSub→Router→Enricher→state chart→audit; per-match snapshot tick); `coordinator/app.py` + `run_server.py` (WS `/ws` + HTTP `/health`, `/matches`, `/matches/{id}/events`); matchmaking auto-pair handshake.
- **Done when:** a script that simulates two players over WS drives a full LOBBY→MATCH_OVER run; events land in SQLite; snapshots/lifecycle publish; `/health` and `/matches/{id}/events` return live data. **No real game client yet.**

### M5 — Client integration (real game over WS)  *(~2 days)*
- `player.py` (`hp`/`max_hp`/`alive`/`to_dict`), `state.py` (Hurt/Dead states), `ws_client.py` (threaded `websocket-client` → shared snapshot buffer + lifecycle queue), `client.py` (async loop, publish input/`attack`, render opponent from snapshots), `game.py` (HP bars, `OverScreen`, lifecycle-driven screen switches).
- **Done when:** two `client.py` instances auto-pair and play a full match locally against the coordinator — movement, attacks, HP/death, and `OverScreen` all sync.

### M6 — Deploy  *(~½–1 day; can start right after M4 to de-risk)*
- `Dockerfile` (server only, **no pygame**), `.dockerignore`, `railway.json`/`fly.toml`, persistent volume at `/data`, env vars.
- **Done when:** the public `wss://<app-url>/ws` + `/health` are reachable; two laptops play a match against the deployed coordinator.

### M7 — Docs & submission  *(~1 day)*
- `README.md` (EIPs w/ enterpriseintegrationpatterns.com citations, state-chart table, audit mechanism, run + deploy instructions, public URL), `sprints/sprint-2-reflection.md`, confirm PERFECT acronym, `git tag sprint-2-final`.
- **Done when:** README pattern names map 1:1 to code; tag pushed; reflection committed (due 24h after demo).

---

## Verification
- **Unit**: schema round-trip; `event_store.replay()` reconstructs known state; `combat.py` damage math; `lifecycle.py` rejects illegal transitions / enforces guards.
- **WS transport**: two scratch `websocket-client` scripts pub/sub on a UUID channel against a locally-running coordinator.
- **End-to-end**: run `coordinator/run_server.py`, then two `client.py` instances; each `join`s, gets auto-paired into one match; play a full LOBBY→…→MATCH_OVER round; confirm HP/death sync and the `OverScreen`.
- **Audit demo**: after a match, run `audit/replay_cli.py <matchId> --upto <seq>` and show the reconstructed mid-match state — proves every mutation is reconstructable (the live demo's "message-flow scenario").
- **Grader-readiness**: README pattern names map 1:1 to the modules above.

## Risks / edge cases
- **You own the pub-sub now** → a bug in `PubSubHub` fan-out is yours; keep it tiny and unit-test subscribe/publish/disconnect. (Upside: a concrete, citable Pub-Sub Channel implementation for the grader.)
- **Single uvicorn worker required** → the in-memory channel registry isn't shared across workers; run `--workers 1` (fine for a 2-player demo).
- **Server must stay pygame-free** → ⚠️ `actions.py`, `hero.py`, and `state.py` all transitively `import pygame` (via `anim.py`). The coordinator must import **only** `action_data.py`/`rules.py`/`combat.py`/plain dicts — never `actions.py`/`hero.py`/`player.py`/`anim.py`. Keeps the Docker image slim (no SDL) and avoids import-time crashes on a headless host.
- **Combat is net-new** → HP, hitboxes, reach, and hit detection do not exist; the event-based model + `reach`/`block_mitigation` data must be designed and tuned. Budget time for this — it's the largest new gameplay piece.
- **Matchmaking** → don't reuse `server.py`'s unbounded `currentPlayer` (3rd client → index error); use the capacity-2 auto-pair handshake.
- **Audit write volume** → never log the ~30 Hz movement stream; audit discrete mutations only, WAL mode on.
- **Ordering** → a single WS connection is ordered + reliable, so no Resequencer needed; client still guards with monotonic `seq`. (Resequencer remains an optional 5th EIP if you want one.)
- **Disconnects** → WS disconnect event server-side → publish `PLAYER_LEFT` → MATCH_OVER (simpler/faster than MQTT LWT).
- **Removing pickle** → only `client.py`/`server.py`/`network.py` touch it; `Player.to_dict()` replaces it cleanly.
- **Authoritative vs local** → server-authoritative **HP/combat/lifecycle only**; position stays client-authoritative (relayed). The opponent renders from snapshots (minor lag/rubber-banding acceptable for the demo).
- **PaaS idle-sleep / ephemeral disk** → Render free sleeps after ~15 min and has no free persistent disk (breaks always-on + audit); prefer **Railway or Fly** with a mounted volume for the SQLite file.

## Deployment (Railway-class PaaS, Docker)
**One container, one process, two jobs.** The PaaS keeps the container alive because something binds the injected `$PORT`. We make the **FastAPI/uvicorn server the main process** (it serves both the `WebSocket /ws` pub-sub endpoint and the HTTP health/spectator routes); the **match-coordinator logic runs in the app's async tasks / startup hook**, sharing the in-memory state and event store.

```
run_server.py → uvicorn app:app --host 0.0.0.0 --port $PORT --workers 1
  on startup: open event store at $DB_PATH (mounted volume) → init PubSubHub + coordinator
  WebSocket /ws            → clients connect (wss://<app-url>/ws), the pub-sub transport
  GET /health              → ok + uptime + active match count   (the reachable proof URL)
  GET /matches             → live matches & phases
  GET /matches/{id}/events → read-only audit-log view (demo of point-in-time history)
```

- **Image**: `python:3.x-slim` + `requirements-server.txt` only (**no pygame / no SDL**). Clients are *not* deployed — they run on demo laptops via the `websockets` lib and connect to the public `wss://` URL.
- **Persistence**: mount a **persistent volume** at `/data`, set `DB_PATH=/data/audit.db`. Do **not** leave the audit DB on ephemeral container disk (wiped on redeploy). `event_store.py` stays behind an interface so a swap to managed Postgres is trivial if the platform lacks volumes.
- **Config (env vars)**: `DB_PATH=/data/audit.db`, platform-injected `PORT`; no broker creds needed (no external broker).
- **Platform**: **Railway** (deploy-from-git, no idle sleep, supports volumes) or **Fly.io**. Avoid Render free tier (idle sleep + no free disk).
- **WSS**: Railway/Fly serve WebSockets over the same HTTPS domain with no extra config — clients use `wss://<app-url>/ws`.

## Open decisions for you
- **Combat model** — event-based hit resolution (default, recommended) vs frame-accurate active-window hit detection (much more work).
- **Authority scope** — server authoritative for HP/combat only with client-authoritative position (default) vs full server-authoritative simulation (port physics + server tick).
- **Aggregator as bonus 5th EIP** — include it (default, ~free) or keep the headline at 4.
- Best-of-N rounds (default **N=1** to limit scope).
- Resequencer as another EIP — keep as contingency only (WS already gives ordered delivery).
- Railway vs Fly.io for the coordinator host (default **Railway**).
- SQLite-on-volume (default) vs managed Postgres for the event store.
- Confirm the exact **PERFECT** acronym letters from your class materials before writing that README section.

---

## To do
Deferred work, not blocking the M5 demo (default best-of-1 plays a full match end to end).

### Rematch flow (best-of-N rounds + post-match rematch)
Currently `ROUNDS_TO_WIN` defaults to **1**, so a death goes `FIGHTING → ROUND_OVER → MATCH_OVER` and the client lands on `OverScreen` with no way back. The lifecycle chart, audit log, and `rematch` plumbing already exist on the **server** (`coordinator/lifecycle.py` has the `ROUND_OVER --REMATCH--> CHARACTER_SELECT` and `--MATCH_DECIDED--> MATCH_OVER` transitions; `MatchCoordinator._on_rematch` counts requests and re-fires; `_reset_round` already restores HP and start positions). What's missing is the **client** side and exercising N>1.

- **Server (mostly done — verify):**
  - Run with `ROUNDS_TO_WIN > 1` (env var) so `_end_round` fires `ROUND_OVER` and stays there until both players request a rematch (or one side reaches N → `MATCH_OVER`).
  - Confirm `_reset_round` is invoked on re-entering `FIGHTING` (it is, via `_on_enter_state`), resetting HP/positions/swing-dedupe; confirm `round_result` audit rows carry `rounds_won`.
  - Decide rematch semantics after a **decided match** (`MATCH_OVER`): either leave `MATCH_OVER` terminal (current chart) or add a `MATCH_OVER --REMATCH--> CHARACTER_SELECT` transition (with HP/round reset) so two players can start a fresh match without reconnecting. Pick one and document it in the chart table.

- **Client (`game.py` / `client.py`) — the actual work:**
  - In `OverScreen` (and a new round-break view for `ROUND_OVER` when N>1): show round score (`rounds_won`) and a "Press R to rematch / waiting for opponent…" prompt; on `R` call `gc.send_rematch()`.
  - Handle the `ROUND_OVER` lifecycle event in `handle_lifecycle` instead of ignoring it (today only `MATCH_OVER` switches screens) — switch to the round-break screen and surface the per-round winner.
  - On the `CHARACTER_SELECT` transition that follows a `REMATCH`, **reset client per-screen flags** that are currently one-shot: `PlayScreen.selected`, `LoadingScreen.p_loaded/p2_loaded/reported`, and clear `gc.opponent_hero`. Without this the loading screen will think assets are already loaded and skip straight through. Easiest fix: give those screens a `reset()` method and call them when entering `CHARACTER_SELECT`.
  - On re-entering `FIGHTING`, `reset_for_fight(p/p2)` already restores HP/positions client-side (works today) — just make sure `OverScreen`/round-break state is cleared and `fight.started` is reset (already done).
  - Optional: a rematch **timeout** (if one player doesn't request within N seconds → `PLAYER_LEFT`/`MATCH_OVER`) so a client stuck on `OverScreen` doesn't hang the other.

- **Verification:**
  - Extend `scripts/m5_smoke.py` (or add `scripts/m5_rematch_smoke.py`) to run with `ROUNDS_TO_WIN=2`: drive round 1 to a death → both `send_rematch()` → confirm lifecycle returns to `CHARACTER_SELECT`, heroes re-selected, `FIGHTING` resumes with full HP, and `rounds_won` increments in `/matches`. Reuse the `Driver` thread — it already reacts to lifecycle, so it mainly needs to send `rematch` on `ROUND_OVER`.
  - Manual: two `client.py` windows, `ROUNDS_TO_WIN=2`, play to a `MATCH_OVER` across two rounds and confirm the score display + rematch prompt.
