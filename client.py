"""Spell Blade client — pygame game over the WebSocket pub/sub coordinator.

The 60fps render loop never blocks on the network. A background
``GameClient`` (websocket-client daemon thread) fills a shared latest-snapshot
buffer and lifecycle/attack queues; each frame the loop:

  * drains lifecycle events to switch screens (coordinator-authoritative),
  * applies the latest world snapshot (opponent position + authoritative HP),
  * reads local input, publishing ``player_state``/``attack``,
  * renders.

The local player stays client-authoritative for position; the opponent is
rendered entirely from snapshots, and HP/death/lifecycle come from the server.
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
    p.frame_index = 0
    p.hp = p.max_hp
    p.alive = True


def apply_snapshot(snap, p, p2, actor, opponent):
    """Apply an authoritative world snapshot to the local/opponent players."""
    for entry in snap.get("players", []):
        if entry.get("actor") == actor:
            # Local player: position is client-authoritative; HP/alive are not.
            p.apply_health(entry.get("hp", p.hp), entry.get("alive", p.alive))
        elif entry.get("actor") == opponent:
            p2.x = entry.get("x", p2.x)
            if entry.get("direction") is not None:
                p2.direction = entry["direction"]
            p2.is_blocking = bool(entry.get("is_blocking", False))
            p2.moving = entry.get("state") == "running"
            p2.apply_health(entry.get("hp", p2.hp), entry.get("alive", p2.alive))
            p2.update()


def handle_lifecycle(events, this_game, p, p2, actor, opponent):
    for ev in events:
        to = ev.get("to")
        if to == "CHARACTER_SELECT":
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
        # ROUND_OVER is transient for the default best-of-1; MATCH_OVER follows.


def main():
    pygame.init()
    win = pygame.display.set_mode((WIDTH, HEIGHT))
    pygame.display.set_caption("SPELLBLADE")
    this_game = game.Game()

    gc = GameClient(game_settings.WS_URL)
    gc.start()
    if not gc.wait_until_joined(timeout=15):
        print(f"Could not join a match at {game_settings.WS_URL}. Is the coordinator running?")
        pygame.quit()
        return

    actor, opponent = gc.actor, gc.opponent
    this_game.gc = gc
    this_game.actor = actor
    this_game.opponent = opponent

    p = make_player(actor)
    p2 = make_player(opponent)

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
            elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                run = False

        # 1) Coordinator-driven screen transitions.
        handle_lifecycle(gc.poll_lifecycle(), this_game, p, p2, actor, opponent)

        # 2) Authoritative world state (opponent position + HP/death).
        snap = gc.latest_snapshot()
        if snap:
            apply_snapshot(snap, p, p2, actor, opponent)

        # 3) Opponent attack swings (rendered from their input channel).
        for action_id in gc.poll_opponent_attacks():
            act = actions.ACTION_BY_ID.get(action_id)
            if act and p2.alive and not p2.is_acting:
                p2.action = act
                p2.is_acting = True
                p2.frame_index = 0

        # 4) Local input + publish (only while fighting and alive).
        if this_game.state is this_game.fight and p.alive:
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

    gc.close()
    pygame.quit()


if __name__ == "__main__":
    main()
