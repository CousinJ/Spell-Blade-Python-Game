import utils
import anim
import hero
import pygame
import game_settings
import state

#//=========================================================

class TitleScreen():
    def __init__(self, game):
        self.game = game

    def update(self, p, p2, dt):
        # Advance is driven by the coordinator lifecycle (both players joined ->
        # CHARACTER_SELECT), handled in client.py. Nothing local to do here.
        pass

    def anim_update(self, p, p2):
        self.game.screen_image, self.game.screen_index = self.game.s_animator.animate.loop(self.game.title_screen, self.game.screen_image, self.game.screen_index )


class WaitingScreen():
    """Lobby / matchmaking wait: shown after a player presses SPACE to enter the
    lobby and while they are queued (joined but not yet paired). Reuses the
    loading-screen animation; screen transitions are driven by lifecycle events
    in client.py, so there is nothing to do in update()."""
    def __init__(self, game):
        self.game = game

    def update(self, p, p2, dt):
        pass

    def anim_update(self, p, p2):
        self.game.screen_image, self.game.screen_index = self.game.s_animator.animate.loop(self.game.loading_screen, self.game.screen_image, self.game.screen_index )


class PlayScreen():
    def __init__(self, game):
        self.game = game
        self.selected = False

    def update(self, p, p2, dt):
        if not self.selected and p.hero.hero == False:
            keys = pygame.key.get_pressed()
            chosen = None
            if keys[pygame.K_w]:
                chosen = hero.FireChar()
            elif keys[pygame.K_a]:
                chosen = hero.MagicChar()
            elif keys[pygame.K_s]:
                chosen = hero.ForestChar()
            elif keys[pygame.K_d]:
                chosen = hero.IceChar()

            if chosen:
                p.hero.select_hero(chosen)
                self.selected = True
                # Tell the coordinator which hero this actor picked. The screen
                # switch to LOADING is driven by the lifecycle event.
                if self.game.gc:
                    self.game.gc.send_hero_select(type(chosen).__name__)

    def anim_update(self, p, p2):
        self.game.screen_image, self.game.screen_index = self.game.s_animator.animate.loop(self.game.select_screen, self.game.screen_image, self.game.screen_index )


class LoadingScreen():
    def __init__(self, game):
        self.game = game
        self.p_loaded = False
        self.p2_loaded = False
        self.reported = False

    def update(self, p, p2, dt):
        # Load our own animator as soon as our hero is chosen.
        if not self.p_loaded and p.hero.hero:
            self.set_player_animators(p, self.game.p1_animator)
            self.p_loaded = True

        # Build the opponent from the hero they announced on the lobby channel.
        if not self.p2_loaded and self.game.gc and self.game.gc.opponent_hero:
            opp = hero.hero_from_name(self.game.gc.opponent_hero)
            if opp:
                p2.hero.select_hero(opp)
                self.set_player_animators(p2, self.game.p2_animator)
                self.p2_loaded = True

        # Once both sides are renderable, report ready. FIGHTING is then entered
        # by the coordinator (both clients loaded) and switched in client.py.
        if self.p_loaded and self.p2_loaded and not self.reported:
            p.state = self.set_player_state(p)
            p2.state = self.set_player_state(p2)
            self.reported = True
            if self.game.gc:
                self.game.gc.send_assets_loaded()

    def anim_update(self, p, p2):
        self.game.screen_image, self.game.screen_index = self.game.s_animator.animate.loop(self.game.loading_screen, self.game.screen_image, self.game.screen_index )

    def set_player_animators(self, p, animator):
        animator.load_sprite_sheet(p.hero.hero.path_string)
        animator.cut_sprite_sheet()
        animator.scale_anim_frames()
        animator.create_reflections()

        animator.load_effect_sheet(p.hero.hero.effect_path_string)
        animator.cut_effect_sheet()
        animator.scale_e_anim_frames()
        animator.create_e_reflections()

    def set_player_state(self, p):
        return self.game.player_state_manager.switch_state(p, self.game.player_state_manager.idle)


class FightScreen():
    def __init__(self, game):
        self.game = game
        self.started = False

    def update(self, p, p2, dt):
        if not self.started:
            self.game.screen_image = self.game.scene_bg
            self.started = True
        # Input + networking are handled in client.py; here we only resolve each
        # player's visible animation state from their (local or synced) flags.
        self.game.player_state_manager.update(p)
        self.game.player_state_manager.update(p2)

    def anim_update(self, p, p2):
        self.game.p1_image, p.frame_index = p.state.update_anim(p, self.game.p1_image, self.game.p1_animator)
        self.game.p2_image, p2.frame_index = p2.state.update_anim(p2, self.game.p2_image, self.game.p2_animator)


class OverScreen():
    def __init__(self, game):
        self.game = game

    def update(self, p, p2, dt):
        # Keep resolving animation state so the death/idle clips keep playing.
        self.game.player_state_manager.update(p)
        self.game.player_state_manager.update(p2)

    def anim_update(self, p, p2):
        if self.game.p1_image is not None and self.game.p2_image is not None:
            self.game.p1_image, p.frame_index = p.state.update_anim(p, self.game.p1_image, self.game.p1_animator)
            self.game.p2_image, p2.frame_index = p2.state.update_anim(p2, self.game.p2_image, self.game.p2_animator)

#//=========================================================
class Game():
    def __init__(self):
        self.loader = utils.Loader()
        #states and screens for each game state
        self.title = TitleScreen(self)
        self.title_screen = self.loader.load_screen("./assets/title_screen/title-screen-spirtesheet", 24)
        self.select_screen = self.loader.load_screen("./assets/select_screen/play_select_screen", 21)
        self.loading_screen = self.loader.load_screen("./assets/loading_screen/loading_waiting_screen", 9)
        self.scene_bg = self.loader.load_static_screen("./assets/scene/castle_bg.png")
        self.loading = LoadingScreen(self)
        self.play = PlayScreen(self)
        self.fight = FightScreen(self)
        self.over = OverScreen(self)
        self.waiting = WaitingScreen(self)
        #this state
        self.state = self.title
        #anims
        self.p1_animator = anim.PlayerAnimator()
        self.p2_animator = anim.PlayerAnimator()
        self.p1_image = None
        self.p2_image = None
        self.s_animator = anim.ScreenAnimator()
        self.anim_dict = anim.AnimDict()
        self.player_state_manager = state.Manager()
        self.screen_index = 0
        self.screen_image = None
        self.p1_draw_offset = 0
        self.p2_draw_offset = 0

        # M5: WebSocket client + this client's identity (set by client.py).
        self.gc = None
        self.actor = None
        self.opponent = None

        pygame.font.init()
        self.font = pygame.font.SysFont("arial", 28)
        self.big_font = pygame.font.SysFont("arial", 72, bold=True)

    def update(self, win, p, p2, dt):
        self.draw_screen(win)
        self.draw_players(win, p, p2)
        self.state.update(p, p2, dt)
        if self.state in (self.fight, self.over) and self.actor:
            self.draw_hud(win, p, p2)
        if self.state is self.waiting:
            self.draw_center_text(win, "WAITING FOR AN OPPONENT…", self.font, (240, 240, 240), dy=-20)
        elif self.state is self.over:
            self.draw_over(win, p, p2)

    def reset_for_new_game(self):
        """Wipe per-game render state so a fresh match starts cleanly.

        The animator cut/scale methods *append* into their frame lists, so each
        game needs fresh animators; the persistent screen flags must reset too so
        hero-select, asset-loading, and the fight intro all run again.
        """
        self.p1_animator = anim.PlayerAnimator()
        self.p2_animator = anim.PlayerAnimator()
        self.p1_image = None
        self.p2_image = None
        self.play.selected = False
        self.loading.p_loaded = False
        self.loading.p2_loaded = False
        self.loading.reported = False
        self.fight.started = False

    def draw_center_text(self, win, text, font, color, dy=0):
        surf = font.render(text, True, color)
        rect = surf.get_rect(center=(game_settings.WIDTH // 2, game_settings.HEIGHT // 2 + dy))
        win.blit(surf, rect)

    def switch_state(self, new_state):
        self.state = new_state

    def calc_draw_offset(self, p, draw_offset):
        if p.direction < 0:
            draw_offset = 160
        else:
            draw_offset = 40
        return draw_offset

    def anim_update(self, p, p2):
        self.state.anim_update(p, p2)
        self.p1_draw_offset = self.calc_draw_offset(p, self.p1_draw_offset)
        self.p2_draw_offset = self.calc_draw_offset(p2, self.p2_draw_offset)

    def draw_screen(self, win):
        if self.screen_image != None:
            win.blit(self.screen_image, (0,0))
#called in game state
    def draw_players(self, win, p, p2):
        if self.p1_image == None or self.p2_image == None:
            pass
        else:
            win.blit(self.p1_image, self.p1_animator.calc_position_player(p, self.p1_draw_offset))
            win.blit(self.p2_image, self.p2_animator.calc_position_player(p2, self.p2_draw_offset))

    # ------------------------------------------------------------------ HUD
    def _left_right(self, p, p2):
        """Return (p1_player, p2_player) regardless of which one is local.

        Bound directly to each player's ``actor`` (set in client.py) rather than
        to ``self.actor`` so the bars are deterministic and always track the
        correct fighter: p1 spawns on the left, p2 on the right.
        """
        by_actor = {getattr(p, "actor", None): p, getattr(p2, "actor", None): p2}
        left = by_actor.get("p1", p)
        right = by_actor.get("p2", p2)
        return left, right

    def draw_hud(self, win, p, p2):
        left, right = self._left_right(p, p2)
        lx, rx = 40, game_settings.WIDTH - 40 - 420
        self._draw_health_bar(win, left, x=lx, align_left=True)
        self._draw_health_bar(win, right, x=rx, align_left=False)
        self._draw_stamina_bar(win, left, x=lx, align_left=True)
        self._draw_stamina_bar(win, right, x=rx, align_left=False)

    def _draw_health_bar(self, win, player, x, align_left):
        w, h, y = 420, 28, 40
        frac = max(0.0, min(1.0, player.hp / player.max_hp)) if player.max_hp else 0.0
        pygame.draw.rect(win, (40, 40, 40), (x, y, w, h))
        fill_w = int(w * frac)
        fill_x = x if align_left else x + (w - fill_w)
        color = (0, 200, 0) if frac > 0.3 else (200, 40, 40)
        pygame.draw.rect(win, color, (fill_x, y, fill_w, h))
        pygame.draw.rect(win, (255, 255, 255), (x, y, w, h), 2)
        name = "?"
        if player.hero and player.hero.hero:
            name = player.hero.hero.name
        label = self.font.render(f"{name}  {player.hp}/{player.max_hp}", True, (255, 255, 255))
        win.blit(label, (x, y + h + 34))  # below the stamina bar drawn under this

    def _draw_stamina_bar(self, win, player, x, align_left):
        w, h, y = 420, 14, 74  # thinner bar just under the health bar
        max_stam = getattr(player, "max_stamina", 0)
        stam = getattr(player, "stamina", 0)
        frac = max(0.0, min(1.0, stam / max_stam)) if max_stam else 0.0
        pygame.draw.rect(win, (40, 40, 40), (x, y, w, h))
        fill_w = int(w * frac)
        fill_x = x if align_left else x + (w - fill_w)
        pygame.draw.rect(win, (230, 190, 40), (fill_x, y, fill_w, h))  # amber
        pygame.draw.rect(win, (255, 255, 255), (x, y, w, h), 2)

    def draw_over(self, win, p, p2):
        overlay = pygame.Surface((game_settings.WIDTH, game_settings.HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 120))
        win.blit(overlay, (0, 0))

        winner = None
        if self.gc:
            snap = self.gc.latest_snapshot()
            if snap:
                winner = snap.get("winner")
        if winner == self.actor:
            text, color = "VICTORY", (80, 220, 80)
        elif winner is None:
            text, color = "MATCH OVER", (230, 230, 230)
        else:
            text, color = "DEFEAT", (220, 80, 80)

        banner = self.big_font.render(text, True, color)
        rect = banner.get_rect(center=(game_settings.WIDTH // 2, game_settings.HEIGHT // 2 - 40))
        win.blit(banner, rect)

        self.draw_center_text(win, "Press SPACE to return to the lobby", self.font, (230, 230, 230), dy=40)
        self.draw_center_text(win, "Press ESC to quit", self.font, (180, 180, 180), dy=80)
