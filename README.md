# Spell Blade

A 2-player pygame fighting game with a **server-authoritative, event-sourced**
backend. Clients connect over a **WebSocket publish/subscribe** channel to a
headless **Match Coordinator** (FastAPI) that owns combat, HP, the match
lifecycle, and an append-only audit log. No external broker — the coordinator
*is* the broker.

> This README covers how to install, start, and play locally. The pattern/EIP
> write-up and deployment live in `plan.md` (and the eventual `sprints/` docs).

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

## Requirements

- Python 3.11+
- Two dependency sets (the client needs pygame; the server must stay pygame-free):

```bash
pip install -r requirements.txt          # client: pygame-ce, websocket-client
pip install -r requirements-server.txt   # server: fastapi, uvicorn, websockets
```

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

The client connects to `ws://localhost:8000/ws` by default. To point at a
different coordinator, set `SPELLBLADE_WS_URL` first, e.g.
`SPELLBLADE_WS_URL=ws://localhost:9000/ws python client.py`.

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

The lifecycle state chart, channel keys, and message schema are documented in
`plan.md`.

---

## Inspect a running match (HTTP)

While the coordinator is up:

```bash
curl http://localhost:8000/health                     # liveness + active match count
curl http://localhost:8000/matches                    # live matches, phase, players, HP
curl http://localhost:8000/matches/<matchId>/events   # append-only audit log (replayable history)
```

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
| `scripts/` | `m1_ws_smoke.py`, `m4_match_sim.py`, `m5_smoke.py` |
| `game_settings.py` / `coordinator/action_data.py` | shared constants (HP, start positions, action table) |
