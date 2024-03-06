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
        keys = pygame.key.get_pressed()
        if keys[pygame.K_SPACE]:
            self.game.switch_state(self.game.play)
        
            
    def anim_update(self, p, p2):
        self.game.screen_image, self.game.screen_index = self.game.s_animator.animate.loop(self.game.title_screen, self.game.screen_image, self.game.screen_index )
        

        

    

class PlayScreen():
    def __init__(self, game):
        self.game = game
    def update(self, p, p2,dt):
        if p.hero.hero == False:

            keys = pygame.key.get_pressed()

            if keys[pygame.K_w]:
                print(p.hero.hero)
                p.hero.select_hero(hero.FireChar())
                print(p.hero.hero)
                self.game.switch_state(self.game.loading)


            elif keys[pygame.K_a]:
                print(p.hero.hero)
                p.hero.select_hero(hero.MagicChar())
                print(p.hero.hero)
                self.game.switch_state(self.game.loading)

            elif keys[pygame.K_s]:
                print(p.hero.hero)
                p.hero.select_hero(hero.ForestChar())
                print(p.hero.hero)
                self.game.switch_state(self.game.loading)


            elif keys[pygame.K_d]:
                print(p.hero.hero)
                p.hero.select_hero(hero.IceChar())
                print(p.hero.hero)
                self.game.switch_state(self.game.loading)
                
        
    def anim_update(self, p, p2):
        self.game.screen_image, self.game.screen_index = self.game.s_animator.animate.loop(self.game.select_screen, self.game.screen_image, self.game.screen_index )


        





class LoadingScreen():
    def __init__(self, game):
        self.game = game
        self.p_loaded = False
        self.p2_loaded = False

    def update(self, p, p2,dt):
        #load player animator first then check p2 for a hero and then set the set its animator
        if self.p_loaded == False:
            
            self.set_player_animators(p, self.game.p1_animator)
            self.p_loaded = True
        
        if self.p2_loaded == False:
            if p2.hero.hero == False:
                print("waiting...")
            else:
                    #switch to game screen here.
                self.p2_loaded = True
                
                self.set_player_animators(p2, self.game.p2_animator)
                print('GAME starting....!')
                #switch to game!
                
                
        if self.p2_loaded == True and self.p_loaded == True:
            p.state = self.set_player_state(p)
            
            if p.state and p2.state:
                self.game.switch_state(self.game.fight)
                print("switched to game")

    def anim_update(self, p,p2):
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
        p.state = self.game.player_state_manager.switch_state(p, self.game.player_state_manager.idle)
        return p.state
        





class FightScreen():
    def __init__(self, game):
        self.game = game
        self.started = False

    

    def update(self, p, p2, dt):
        
        if not self.started:
            self.game.screen_image = self.game.scene_bg
            self.started = True
        self.game.player_state_manager.update(p)
        p.attack()
        p.block()


    def anim_update(self, p, p2):
        #remember that you are checking if p1 image is none to no longer draw the players. (or player 2)
        
        self.game.p1_image, p.frame_index = p.state.update_anim(p, self.game.p1_image, self.game.p1_animator)
        self.game.p2_image, p2.frame_index = p2.state.update_anim(p2, self.game.p2_image, self.game.p2_animator)

        
        
    

class OverScreen():
    def __init__(self, game):
        self.game = game
    def update(self, p, p2,dt):
        pass
    def anim_update(self):
        pass

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
       
       
        

    def update(self,win, p, p2, dt):
        self.draw_screen(win)
        self.draw_players(win,p,p2)
        self.state.update(p,p2,dt)
        
        
        
    def switch_state(self, new_state):
        self.state = new_state


    def calc_draw_offset(self,p, draw_offset):
        if p.direction < 0:
            draw_offset = 160
        else:
            draw_offset = 40
        return draw_offset


    def anim_update(self, p, p2):
        self.state.anim_update(p,p2)
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
            win.blit(self.p2_image, self.p2_animator.calc_position_player(p2,self.p2_draw_offset))