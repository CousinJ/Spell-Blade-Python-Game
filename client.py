"""Spell Blade client — pygame game over the WebSocket pub/sub coordinator.

Flow: **Title → SPACE → Lobby (waiting) → game → result → SPACE → Lobby**. The
client does not connect at launch; pressing SPACE on the title opens a
``GameClient`` (which auto-publishes the matchmaking ``join``) and shows the
Waiting screen until the coordinator pairs us (a third player simply keeps
waiting). After a match, SPACE reconnects with a fresh ``GameClient`` to
re-enter matchmaking.

The 60fps render loop never blocks on the network. The background
``GameClient`` (websocket-client daemon thread) fills a shared latest-snapshot
buffer and lifecycle/attack queues; each frame the loop drains lifecycle events
to switch screens, applies the latest world snapshot, reads local input
(publishing ``player_state``/``attack``), and renders.

The local player stays client-authoritative for position; the opponent is
rendered entirely from snapshots, and HP/stamina/death/lifecycle come from the
server.
"""
import pygame

import actions
import game
import game_settings
import state as state_mod
from messaging.ws_client import GameClient
from player import Player

WIDTH = game_settings.WIDTH
HEIGHT = game_settings.HEIGHT


def make_player(actor):
    color = game_settings.PLAYER_COLORS[actor]
    p = Player(
        game_settings.START_X[actor],
        game_settings.PLAYER_Y,
        game_settings.PLAYER_W,
        game_settings.PLAYER_H,
        color,
        game_settings.START_DIR[actor],
    )
    p.actor = actor
    return p


def reset_for_fight(p, actor):
    p.x = game_settings.START_X[actor]
    p.direction = game_settings.START_DIR[actor]
    p.vel = 0
    p.moving = False
    p.is_acting = False
    p.is_blocking = False
    p.is_hurt = False
    p.is_parrying = False
    p._blocks_taken = 0
    p.frame_index = 0
    p.hp = p.max_hp
    p.alive = True
    p.stamina = p.max_stamina


def apply_stamina_and_parry(entry, player):
    """Mirror server stamina onto a player and trigger parry on a new blocked hit.

    A blocked hit increments the server's per-actor ``blocks_taken`` counter; the
    rising edge means this player just blocked something, so we play the parry
    animation instead of the hurt clip (the mitigated-damage tick would otherwise
    flag ``is_hurt``). Must run *after* ``apply_health`` so it overrides that flag.
    """
    player.stamina = entry.get("stamina", player.stamina)
    player.max_stamina = entry.get("max_stamina", player.max_stamina)
    blocks = entry.get("blocks_taken", player._blocks_taken)
    if blocks > player._blocks_taken:
        player.is_parrying = True
        player.is_hurt = False
        player.frame_index = 0
    player._blocks_taken = blocks


def apply_snapshot(snap, p, p2, actor, opponent):
    """Apply an authoritative world snapshot to the local/opponent players."""
    for entry in snap.get("players", []):
        if entry.get("actor") == actor:
            # Local player: position is client-authoritative; HP/alive are not.
            p.apply_health(entry.get("hp", p.hp), entry.get("alive", p.alive))
            apply_stamina_and_parry(entry, p)
        elif entry.get("actor") == opponent:
            p2.x = entry.get("x", p2.x)
            if entry.get("direction") is not None:
                p2.direction = entry["direction"]
            p2.is_blocking = bool(entry.get("is_blocking", False))
            p2.moving = entry.get("state") == "running"
            p2.apply_health(entry.get("hp", p2.hp), entry.get("alive", p2.alive))
            apply_stamina_and_parry(entry, p2)
            p2.update()


def main():
    pygame.init()
    win = pygame.display.set_mode((WIDTH, HEIGHT))
    pygame.display.set_caption("SPELLBLADE")
    this_game = game.Game()
    this_game.switch_state(this_game.title)

    # Placeholder players until a real game starts (rebuilt on CHARACTER_SELECT).
    # They are never drawn before a fight, so they only spare us None-handling.
    p = make_player("p1")
    p2 = make_player("p2")
    actor = opponent = None
    gc = None
    in_game = False  # True once a match's players are built (CHARACTER_SELECT)

    def connect():
        """Open a fresh connection and enter the lobby. The GameClient auto-
        publishes the matchmaking ``join`` on open; we wait on the Waiting
        screen until the coordinator pairs us (CHARACTER_SELECT)."""
        nonlocal gc
        gc = GameClient(game_settings.WS_URL)
        gc.start()
        this_game.gc = gc
        this_game.switch_state(this_game.waiting)

    animation_refresh = 60
    anim_timer = animation_refresh + 1  # animate on the first eligible frame
    publish_interval = 1000 / game_settings.INPUT_PUBLISH_HZ
    last_publish = 0
    prev_time = pygame.time.get_ticks()

    clock = pygame.time.Clock()
    run = True
    while run:
        clock.tick(60)
        now = pygame.time.get_ticks()
        dt = now - prev_time
        prev_time = now

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                run = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    run = False
                elif event.key == pygame.K_SPACE:
                    if this_game.state is this_game.title and gc is None:
                        connect()  # Title -> Lobby (start matchmaking)
                    elif this_game.state is this_game.over:
                        # Result -> Lobby: reconnect to re-enter matchmaking.
                        if gc is not None:
                            gc.close()
                        in_game = False
                        this_game.reset_for_new_game()
                        connect()

        # If the connection dropped while waiting (e.g. server down), fall back
        # to the title so the player can retry with SPACE.
        if this_game.state is this_game.waiting and gc is not None and gc.closed.is_set():
            gc = None
            this_game.gc = None
            this_game.switch_state(this_game.title)

        if gc is not None:
            # 1) Coordinator-driven screen transitions.
            for ev in gc.poll_lifecycle():
                to = ev.get("to")
                if to == "CHARACTER_SELECT":
                    # A game just started for us: (re)build players for our actor.
                    actor, opponent = gc.actor, gc.opponent
                    this_game.actor = actor
                    this_game.opponent = opponent
                    p = make_player(actor)
                    p2 = make_player(opponent)
                    this_game.reset_for_new_game()
                    in_game = True
                    this_game.switch_state(this_game.play)
                elif to == "LOADING":
                    this_game.switch_state(this_game.loading)
                elif to == "FIGHTING":
                    reset_for_fight(p, actor)
                    reset_for_fight(p2, opponent)
                    this_game.fight.started = False
                    this_game.switch_state(this_game.fight)
                elif to == "MATCH_OVER":
                    this_game.switch_state(this_game.over)
                # ROUND_OVER is transient for best-of-1; MATCH_OVER follows.

            if in_game:
                # 2) Authoritative world state (opponent position + HP/stamina).
                snap = gc.latest_snapshot()
                if snap and this_game.state in (this_game.fight, this_game.over):
                    apply_snapshot(snap, p, p2, actor, opponent)

                if this_game.state is this_game.fight:
                    # 3) Opponent attack swings (rendered from their input channel).
                    for action_id in gc.poll_opponent_attacks():
                        act = actions.ACTION_BY_ID.get(action_id)
                        if act and p2.alive and not p2.is_acting:
                            p2.action = act
                            p2.is_acting = True
                            p2.frame_index = 0

                    # 4) Local input + publish (only while fighting and alive).
                    if p.alive:
                        p.move(dt)
                        started = p.attack()
                        if started:
                            gc.send_attack(started)
                        p.block()

                        if now - last_publish >= publish_interval:
                            gc.send_player_state(
                                p.x, p.direction, p.moving, p.is_blocking, state_mod.label_for(p)
                            )
                            last_publish = now

        # 5) Render.
        win.fill((255, 255, 255))
        if anim_timer > animation_refresh:
            this_game.anim_update(p, p2)
            anim_timer = 0
        else:
            anim_timer += dt

        this_game.update(win, p, p2, dt)
        pygame.display.update()

    if gc is not None:
        gc.close()
    pygame.quit()


if __name__ == "__main__":
    main()
