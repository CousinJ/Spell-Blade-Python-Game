import pygame
import hero
class Player():
    def __init__(self, x, y, width, height, color, direction):
        self.x = x
        self.y = y
        self.width = width
        self.height = height
        self.color = color
        self.rect = (x,y,width,height)
        self.acc = .1
        self.vel = 0
        self.max_vel = 1
        self.direction = direction
        self.hero = hero.Hero()
        self.frame_index = 0
        self.state = False
        self.moving = False
        
        self.is_acting = False
        self.action = False

        self.is_blocking = False
        

    def draw(self, win):
        pygame.draw.rect(win, self.color, self.rect)
        
        
    def move(self, dt):
        keys = pygame.key.get_pressed()
        dt = dt / 2
        if not self.is_acting:
            # Acceleration based on key press
            if keys[pygame.K_a]:
                self.vel += self.acc
                self.direction = -1
                self.moving = True
            elif keys[pygame.K_d]:
                self.vel += self.acc
                self.direction = 1
                self.moving = True
            else:
                # Slow down if no key pressed
                
                self.vel = 0
                self.moving = False

            # Limit velocity to max velocity
            if abs(self.vel) > self.max_vel:
                self.vel = self.max_vel
            

            # Update position
            self.x += self.vel * self.direction * dt

        self.update()

    def attack(self):
        keys = pygame.key.get_pressed()
        if not self.is_acting:
            if keys[pygame.K_u]:
                self.action = self.hero.hero.attack_one
                self.is_acting = True
                self.frame_index = 0
            if keys[pygame.K_i]:
                self.action = self.hero.hero.attack_two
                self.is_acting = True
                self.frame_index = 0
            if keys[pygame.K_o]:
                self.action = self.hero.hero.attack_three
                self.is_acting = True
                self.frame_index = 0
            
    
    def block(self):
        keys = pygame.key.get_pressed()
        if keys[pygame.K_SPACE]:
               self.is_blocking = True
        else:
            self.is_blocking = False
        
    def update(self):
        
        self.rect = (self.x, self.y, self.width, self.height)