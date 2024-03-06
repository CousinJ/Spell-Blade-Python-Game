import pygame
import game_settings

class Loader():
    def load_screen(self, format_string, frames):
        images = []
        for i in range(1, frames + 1):
            
            
           
            image = pygame.image.load(f"{format_string}{i}.png").convert_alpha()
            image = pygame.transform.scale(image, (game_settings.WIDTH, game_settings.HEIGHT))
            images.append(image)
        return images
    def load_static_screen(self, path):
        image = pygame.image.load(path)
        image = pygame.transform.scale(image, (game_settings.WIDTH, game_settings.HEIGHT))
        return image
        
    