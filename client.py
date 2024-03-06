import pygame
from network import Network
from player import Player
import game_settings
import game

width = game_settings.WIDTH
height = game_settings.HEIGHT
win = pygame.display.set_mode((width, height))
pygame.display.set_caption("SPELLBLADE")
this_game = game.Game()

def redrawWindow(win,player, player2):
    #HITBOX drawing
    # player.draw(win)
    # player2.draw(win)
    pygame.display.update()


def main():

    animation_refresh = 60
    anim_timer = 0
    prev_time = pygame.time.get_ticks()
    run = True
    n = Network()
    p = n.getP()
    
    clock = pygame.time.Clock()

    while run:
        clock.tick(60)
        now = pygame.time.get_ticks()
        dt = now - prev_time 
        prev_time = pygame.time.get_ticks()

        p2 = n.send(p)
#animation update=================
        win.fill((255,255,255))
        if anim_timer > animation_refresh:
        
            
            this_game.anim_update(p, p2)
        
        
            anim_timer = 0

        else:
           anim_timer += dt
#end of update====================   
        
        
        this_game.update(win, p, p2, dt)
        
        #all player class data is available on client
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                run = False
                pygame.quit()

        p.move(dt)
        redrawWindow(win, p, p2)

main()