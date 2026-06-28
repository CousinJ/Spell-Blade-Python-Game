"""Match Coordinator — orchestrates the EIP pipeline + state chart + audit.

Data flow (all over the WebSocket pub/sub hub):

    client --publish--> input/lobby/global channels
                         -> coordinator inbox (a hub Subscriber)
                         -> Message Router (by type)
                         -> handler: Content Enricher (combat) / Aggregator
                         -> MatchState mutation (audited via Observer)
                         -> Lifecycle state chart
    coordinator --publish--> snapshot + lifecycle channels -> clients

Pygame-free. One asyncio task per match publishes the aggregated snapshot tick.
"""
from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from typing import Optional

from audit.observer import AuditObserver
from coordinator import action_data, combat, rules
from coordinator.lifecycle import (
    DEFAULT_ROUNDS_TO_WIN,
    Event,
    LifecycleMachine,
    State,
)
from coordinator.match_state import MatchState
from messaging import bus, channels
from messaging.aggregator import SnapshotAggregator
from messaging.enricher import CombatView, Enricher
from messaging.router import MatchRouter
from messaging.schema import Envelope, MessageType

ACTORS = ("p1", "p2")
_START_X = action_data.START_X
_START_DIR = action_data.START_DIR


@dataclass
class MatchContext:
    match_id: str
    state: MatchState
    machine: LifecycleMachine
    aggregator: SnapshotAggregator
    enricher: Enricher
    swings: combat.SwingTracker
    rounds_to_win: int
    clients: dict[str, str] = field(default_factory=dict)  # actor -> client_id
    inbox_channels: set[str] = field(default_factory=set)
    assets_loaded: set[str] = field(default_factory=set)
    rematch: set[str] = field(default_factory=set)
    tick_task: Optional[asyncio.Task] = None
    # Stamina is fast/continuous (like position) and is NOT written to the audit
    # log -- it lives here on the live match context and is mirrored to clients
    # via the snapshot. ``blocks_taken`` is a per-actor counter the client uses
    # to detect a freshly-blocked hit and play the parry animation.
    stamina: dict[str, float] = field(default_factory=dict)
    blocks_taken: dict[str, int] = field(default_factory=dict)

    def opponent(self, actor: str) -> str:
        return "p2" if actor == "p1" else "p1"


class _Inbox:
    """A hub Subscriber that funnels fanned-out frames into the coordinator."""

    def __init__(self, coordinator: "MatchCoordinator") -> None:
        self._c = coordinator
        self.id = "coordinator-inbox"

    async def send(self, text: str) -> None:
        await self._c._on_frame(text)

    def __hash__(self) -> int:
        return hash(self.id)

    def __eq__(self, other: object) -> bool:
        return getattr(other, "id", None) == self.id


class MatchCoordinator:
    def __init__(
        self,
        hub,
        event_store,
        *,
        rounds_to_win: int = DEFAULT_ROUNDS_TO_WIN,
        tick_interval: float = 0.05,
    ) -> None:
        self._hub = hub
        self._store = event_store
        self._rounds_to_win = rounds_to_win
        self._tick_interval = tick_interval
        self._matches: dict[str, MatchContext] = {}
        self._pending: Optional[str] = None
        self._inbox = _Inbox(self)
        self._router = MatchRouter()
        self._router.register(MessageType.JOIN, self._on_join)
        self._router.register(MessageType.HERO_SELECT, self._on_hero_select)
        self._router.register(MessageType.ASSETS_LOADED, self._on_assets_loaded)
        self._router.register(MessageType.PLAYER_STATE, self._on_player_state)
        self._router.register(MessageType.ATTACK, self._on_attack)
        self._router.register(MessageType.REMATCH, self._on_rematch)

    async def start(self) -> None:
        await self._hub.subscribe(channels.GLOBAL_LOBBY, self._inbox)

    # ----------------------------------------------------------- inbox / route
    async def _on_frame(self, raw: str) -> None:
        parsed = bus.parse_message_frame(raw)
        if parsed is None:
            return
        channel, env = parsed
        if not self._router.has_route(env.type):
            return
        try:
            await self._router.route(env, channel)
        except Exception as exc:  # noqa: BLE001 - one bad message must not kill the inbox
            print(f"[coordinator] route error for {env.type!r}: {exc}")

    # ------------------------------------------------------------- publishing
    async def _publish(self, channel: str, env: Envelope) -> None:
        await self._hub.publish(channel, bus.message_frame(channel, env))

    # ------------------------------------------------------------ matchmaking
    async def _ensure_pending(self) -> MatchContext:
        if (
            self._pending
            and self._pending in self._matches
            and len(self._matches[self._pending].clients) < 2
        ):
            return self._matches[self._pending]

        match_id = "M" + uuid.uuid4().hex[:8]
        state = MatchState(match_id)
        state.attach(AuditObserver(self._store))  # persist every mutation
        mc = MatchContext(
            match_id=match_id,
            state=state,
            machine=LifecycleMachine(),
            aggregator=SnapshotAggregator(),
            enricher=Enricher(),
            swings=combat.SwingTracker(),
            rounds_to_win=self._rounds_to_win,
        )
        self._matches[match_id] = mc
        self._pending = match_id
        for ch in (
            channels.lobby(match_id),
            channels.player_input(match_id, "p1"),
            channels.player_input(match_id, "p2"),
        ):
            await self._hub.subscribe(ch, self._inbox)
            mc.inbox_channels.add(ch)
        return mc

    async def _on_join(self, env: Envelope, channel: str) -> None:
        client_id = env.payload.get("clientId")
        if not client_id:
            return
        mc = await self._ensure_pending()
        actor = ACTORS[len(mc.clients)]
        mc.clients[actor] = client_id
        mc.state.join(actor, x=_START_X[actor])
        mc.stamina[actor] = float(action_data.MAX_STAMINA)
        mc.blocks_taken[actor] = 0

        await self._publish(
            channels.client_inbox(client_id),
            Envelope(
                type=MessageType.JOINED,
                match_id=mc.match_id,
                actor=actor,
                payload={"clientId": client_id, "matchId": mc.match_id, "actor": actor},
            ),
        )
        if len(mc.clients) == 2:
            self._pending = None
            await self._fire(mc, Event.PLAYER_JOINED)

    # ----------------------------------------------------------- disconnects
    async def on_disconnect(self, client_id: str) -> None:
        """Handle a dropped WebSocket connection (called by the WS endpoint).

        * Already-finished match -> nothing to do (the normal post-match
          reconnect path lands here).
        * Still waiting alone in the lobby -> discard the pending match so the
          slot frees and no "ghost" remains for the next joiner to pair with.
        * Mid-match -> the opponent wins by forfeit (PLAYER_LEFT -> MATCH_OVER).
        """
        found = None
        for mc in self._matches.values():
            for actor, cid in mc.clients.items():
                if cid == client_id:
                    found = (mc, actor)
                    break
            if found:
                break
        if found is None:
            return

        mc, actor = found
        if mc.machine.state == State.MATCH_OVER:
            return  # match already finished; normal post-game disconnect
        if mc.machine.state == State.LOBBY:
            await self._discard_pending(mc, actor)
            return

        # Active match: award the remaining player the win, then end the match.
        opponent = mc.opponent(actor)
        if opponent in mc.state.players:
            mc.state.leave(actor)  # audited departure
            mc.state.round_result(round_winner=opponent, match_winner=opponent)
        await self._fire(mc, Event.PLAYER_LEFT)

    async def _discard_pending(self, mc: MatchContext, actor: str) -> None:
        """Tear down a pending (not-yet-started) match a lone player left."""
        mc.state.leave(actor)  # audit join -> leave for the abandoned match
        mc.clients.pop(actor, None)
        if not mc.clients:
            for ch in list(mc.inbox_channels):
                await self._hub.unsubscribe(ch, self._inbox)
            self._matches.pop(mc.match_id, None)
            if self._pending == mc.match_id:
                self._pending = None

    # --------------------------------------------------------------- handlers
    async def _on_hero_select(self, env: Envelope, channel: str) -> None:
        mc = self._matches.get(env.match_id)
        if not mc or env.actor not in mc.state.players:
            return
        hero = env.payload.get("hero")
        if not rules.is_valid_hero(hero):
            return
        mc.state.select_hero(env.actor, hero)
        if sum(1 for p in mc.state.players.values() if p.hero) == 2:
            await self._fire(mc, Event.HERO_SELECTED)

    async def _on_assets_loaded(self, env: Envelope, channel: str) -> None:
        mc = self._matches.get(env.match_id)
        if not mc:
            return
        mc.assets_loaded.add(env.actor)
        if len(mc.assets_loaded) == 2:
            await self._fire(mc, Event.ASSETS_LOADED)

    async def _on_player_state(self, env: Envelope, channel: str) -> None:
        mc = self._matches.get(env.match_id)
        if not mc:
            return
        mc.aggregator.update(env.actor, env.payload)

    async def _on_attack(self, env: Envelope, channel: str) -> None:
        mc = self._matches.get(env.match_id)
        if not mc or mc.machine.state != State.FIGHTING:
            return
        attacker = env.actor
        if attacker not in mc.state.players:
            return
        action_id = env.payload.get("action_id")
        if not rules.is_attack(action_id):
            return
        cost = rules.get_action(action_id).stamina_cost
        # Gate on stamina: an attack the attacker can't afford simply never fires.
        if mc.stamina.get(attacker, 0.0) < cost:
            return
        swing_id = env.client_seq if env.client_seq is not None else id(env)
        if not mc.swings.register(attacker, swing_id):
            return  # one hit per swing

        mc.stamina[attacker] = mc.stamina.get(attacker, 0.0) - cost
        target = mc.opponent(attacker)
        enriched = mc.enricher.enrich_attack(env, self._combat_view(mc, attacker, target))
        hit = enriched["hit"]
        if hit["hit"]:
            if hit["blocked"]:
                # The defender pays stamina to absorb the hit and plays a parry.
                mc.stamina[target] = max(
                    0.0, mc.stamina.get(target, 0.0) - action_data.BLOCK_STAMINA_DRAIN
                )
                mc.blocks_taken[target] = mc.blocks_taken.get(target, 0) + 1
            if hit["damage"] > 0:
                mc.state.apply_damage(target, hit["damage"], attacker=attacker, blocked=hit["blocked"])
                if not mc.state.players[target].alive:
                    await self._end_round(mc, winner=attacker)

    async def _on_rematch(self, env: Envelope, channel: str) -> None:
        mc = self._matches.get(env.match_id)
        if not mc:
            return
        mc.rematch.add(env.actor)
        if len(mc.rematch) == 2:
            mc.rematch.clear()
            await self._fire(mc, Event.REMATCH)

    def _combat_view(self, mc: MatchContext, attacker: str, target: str) -> CombatView:
        a = mc.aggregator.latest(attacker)
        t = mc.aggregator.latest(target)
        return CombatView(
            attacker=attacker,
            target_actor=target,
            attacker_x=float(a.get("x", _START_X[attacker])),
            attacker_dir=int(a.get("direction", _START_DIR[attacker])),
            target_x=float(t.get("x", _START_X[target])),
            target_blocking=bool(t.get("is_blocking", False)),
            target_alive=mc.state.players[target].alive,
            attacker_hero=mc.state.players[attacker].hero,
        )

    # ------------------------------------------------------- lifecycle / round
    def _lifecycle_ctx(self, mc: MatchContext) -> dict:
        players = mc.state.players
        return {
            "players_connected": len(mc.clients),
            "heroes_selected": sum(1 for p in players.values() if p.hero),
            "assets_loaded": len(mc.assets_loaded),
            "any_player_dead": any(not p.alive for p in players.values()),
            "rematch_requests": len(mc.rematch),
            "max_rounds_won": max((p.rounds_won for p in players.values()), default=0),
            "rounds_to_win": mc.rounds_to_win,
        }

    async def _fire(self, mc: MatchContext, event: str, extra: Optional[dict] = None):
        ctx = self._lifecycle_ctx(mc)
        t = mc.machine.allowed(event, ctx)
        if t is None:
            return None
        frm = mc.machine.state
        mc.machine.fire(event, ctx)
        mc.state.transition(frm, t.target, event)  # audited
        payload = {"from": frm, "event": event, "to": t.target}
        if extra:
            payload.update(extra)
        await self._publish(
            channels.lifecycle(mc.match_id),
            Envelope(type=MessageType.LIFECYCLE_EVENT, match_id=mc.match_id, payload=payload),
        )
        await self._on_enter_state(mc, t.target)
        return t

    async def _on_enter_state(self, mc: MatchContext, state: str) -> None:
        if state == State.FIGHTING:
            self._reset_round(mc)
            if mc.tick_task is None:
                mc.tick_task = asyncio.create_task(self._snapshot_loop(mc))
        elif state == State.MATCH_OVER:
            if mc.tick_task is not None:
                mc.tick_task.cancel()
                mc.tick_task = None
            await self._publish_snapshot(mc)  # final authoritative snapshot

    def _reset_round(self, mc: MatchContext) -> None:
        mc.swings.reset()
        for actor, ps in mc.state.players.items():
            if ps.hp != ps.max_hp or not ps.alive:
                mc.state.set_hp(actor, ps.max_hp)
            mc.stamina[actor] = float(action_data.MAX_STAMINA)
            mc.blocks_taken[actor] = 0
            mc.aggregator.update(
                actor,
                {"x": _START_X.get(actor, 0.0), "direction": _START_DIR.get(actor, 1), "is_blocking": False},
            )

    async def _end_round(self, mc: MatchContext, winner: str) -> None:
        await self._fire(mc, Event.PLAYER_DIED)  # FIGHTING -> ROUND_OVER
        will_decide = (mc.state.players[winner].rounds_won + 1) >= mc.rounds_to_win
        mc.state.round_result(winner, match_winner=winner if will_decide else None)
        if will_decide:
            await self._fire(mc, Event.MATCH_DECIDED)  # -> MATCH_OVER

    # ----------------------------------------------------------- snapshot tick
    async def _snapshot_loop(self, mc: MatchContext) -> None:
        try:
            while True:
                self._regen_stamina(mc)
                await self._publish_snapshot(mc)
                await asyncio.sleep(self._tick_interval)
        except asyncio.CancelledError:
            pass

    def _regen_stamina(self, mc: MatchContext) -> None:
        """Refill stamina each tick, paused for any actor currently blocking."""
        gain = action_data.STAMINA_REGEN_PER_SEC * self._tick_interval
        for actor, ps in mc.state.players.items():
            if not ps.alive:
                continue
            if mc.aggregator.latest(actor).get("is_blocking"):
                continue  # holding block stops regen
            mc.stamina[actor] = min(
                float(action_data.MAX_STAMINA), mc.stamina.get(actor, 0.0) + gain
            )

    async def _publish_snapshot(self, mc: MatchContext) -> None:
        payload = mc.enricher.enrich_snapshot(
            mc.aggregator.build(mc.state, stamina=mc.stamina, blocks_taken=mc.blocks_taken)
        )
        await self._publish(
            channels.snapshot(mc.match_id),
            Envelope(type=MessageType.WORLD_SNAPSHOT, match_id=mc.match_id, payload=payload),
        )

    # ------------------------------------------------------ HTTP introspection
    def match_summaries(self) -> list[dict]:
        return [
            {
                "matchId": mc.match_id,
                "phase": mc.machine.state,
                "players": {
                    a: {"hp": p.hp, "alive": p.alive, "hero": p.hero, "rounds_won": p.rounds_won}
                    for a, p in mc.state.players.items()
                },
            }
            for mc in self._matches.values()
        ]

    def events_for(self, match_id: str, upto: Optional[int] = None) -> list[dict]:
        return self._store.events_for(match_id, upto)
