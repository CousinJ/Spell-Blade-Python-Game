import pygame


class Animate():
    def loop(self, frames, image, index):
        anim_frames = frames
        frame_count = len(frames)
        

        if index >= frame_count:
            
            
            index = 0
        
            
        image = anim_frames[index]
        index += 1
        return image, index
    


class PlayerAnimator():
    def __init__(self):
        self.sprite_sheet = False
        self.effect_sheet = False
       
        self.animate = Animate()
        self.sprite_width = 144
        self.sprite_height = 80
        self.scale_factor = 4

        self.anims = []
        self.reflect_anims = []

        self.e_anims = []
        self.reflect_e_anims = []
    
    
    def calc_position_player(self, p, offset):
        
        x = p.x - self.sprite_width - offset
        
        y = p.y - self.sprite_height 
        
        calc_pos = (x,y)
        return calc_pos


    def load_sprite_sheet(self, path):
        sprite_sheet = pygame.image.load(path)
        self.sprite_sheet = sprite_sheet


    def cut_sprite_sheet(self):
        
        sheet_width, sheet_height = self.sprite_sheet.get_size()
        
      
        rows = sheet_height // self.sprite_height
        cols = sheet_width // self.sprite_width

        for row in range(rows):
            frames = []
            for col in range(cols):
                x = col * self.sprite_width
                y = row * self.sprite_height
                rect = pygame.Rect(x, y, self.sprite_width, self.sprite_height)
                frame = self.sprite_sheet.subsurface(rect)
                frames.append(frame)
            self.anims.append(frames)

    def scale_anim_frames(self, scale_factor=4):
        for row in range(len(self.anims)):
            for col in range(len(self.anims[row])):
                width = int(self.sprite_width * scale_factor)
                height = int(self.sprite_height * scale_factor)
                self.anims[row][col] = pygame.transform.scale(self.anims[row][col], (width, height))

    def create_reflections(self):
        for row in range(len(self.anims)):
            anim_frames = []
            for col in range(len(self.anims[row])):
                anim_frames.append(pygame.transform.flip(self.anims[row][col], True, False))
            self.reflect_anims.append(anim_frames)
# effect ----------------------------------------------
    def load_effect_sheet(self, path):
        sprite_sheet = pygame.image.load(path)
        self.effect_sheet = sprite_sheet
    def cut_effect_sheet(self):
        
        sheet_width, sheet_height = self.effect_sheet.get_size()
        
      
        rows = sheet_height // self.sprite_height
        cols = sheet_width // self.sprite_width

        for row in range(rows):
            frames = []
            for col in range(cols):
                print(frames)
                x = col * self.sprite_width
                y = row * self.sprite_height
                rect = pygame.Rect(x, y, self.sprite_width, self.sprite_height)
                frame = self.effect_sheet.subsurface(rect)
                frames.append(frame)
            self.e_anims.append(frames)

    def scale_e_anim_frames(self, scale_factor=4):
        for row in range(len(self.e_anims)):
            for col in range(len(self.e_anims[row])):
                width = int(self.sprite_width * scale_factor)
                height = int(self.sprite_height * scale_factor)
                self.e_anims[row][col] = pygame.transform.scale(self.e_anims[row][col], (width, height))
    def create_e_reflections(self):
        for row in range(len(self.e_anims)):
            anim_frames = []
            for col in range(len(self.e_anims[row])):
                anim_frames.append(pygame.transform.flip(self.e_anims[row][col], True, False))
            self.reflect_e_anims.append(anim_frames)
    def animate_player(self, animation, image, p, reset=0):
        
          # Animate the player
        
        anim_frames = self.anims[animation["index"]]
        if p.direction < 0:
            anim_frames = self.reflect_anims[animation["index"]]
        
        
        frame_count = animation["frames"]
        

        if p.frame_index >= frame_count:
            
            
            p.frame_index = reset
        
            
        image = anim_frames[p.frame_index]
        p.frame_index += 1
        return image, p.frame_index

    def animate_player_action(self, anim_array, image, p, reset=0):

        

        if not anim_array[3]:
            
            anim_frames = self.anims[anim_array[0]["index"]]
            if p.direction < 0:
                anim_frames = self.reflect_anims[anim_array[0]["index"]]
            
            
            frame_count = anim_array[1]
            

            if p.frame_index >= frame_count:
                
                
                p.frame_index = reset
                
            
                
            image = anim_frames[p.frame_index]
            p.frame_index += 1
            return image, p.frame_index
        
        if anim_array[3]:
            anim_frames = self.e_anims[anim_array[0]["index"]]
            if p.direction < 0:
                anim_frames = self.reflect_e_anims[anim_array[0]["index"]]
            
            
            frame_count = anim_array[1]
            

            if p.frame_index >= frame_count:
                
                
                p.frame_index = reset
                
            
                
            image = anim_frames[p.frame_index]
            p.frame_index += 1
            return image, p.frame_index
        
    def animate_block(self, anim, image, p):
        anim_frames = self.e_anims[anim["index"]]
        if p.direction < 0:
            anim_frames = self.reflect_e_anims[anim["index"]]

        frame_count = 7

        if p.frame_index >= frame_count:

            p.frame_index = 2

        image = anim_frames[p.frame_index]
        p.frame_index += 1
        return image, p.frame_index

    def animate_reverse_action(self, anim_array, image, p):
        if not anim_array[3]:
            anim_frames = self.anims[anim_array[0]["index"]]
            if p.direction < 0:
                anim_frames = self.reflect_anims[anim_array[0]["index"]]
            
            frame_count = anim_array[1]
                

            if p.frame_index > frame_count:
                    
                    
                p.frame_index = 0
                    
                #instead of starting at 0 and going toframe count we need to start at frame_count and substract p.frame_index from it.
            reverse_index = frame_count  -1   
            image = anim_frames[reverse_index - p.frame_index]
            p.frame_index += 1
            return image, p.frame_index
        
        if anim_array[3]:
            anim_frames = self.e_anims[anim_array[0]["index"]]
            if p.direction < 0:
                anim_frames = self.reflect_e_anims[anim_array[0]["index"]]
            
            frame_count = anim_array[1]
                

            if p.frame_index > frame_count:
                    
                    
                p.frame_index = 0
                    
                #instead of starting at 0 and going toframe count we need to start at frame_count and substract p.frame_index from it.
            reverse_index = frame_count  -1   
            image = anim_frames[reverse_index - p.frame_index]
            p.frame_index += 1
            return image, p.frame_index
    


class ScreenAnimator():
    def __init__(self):
        self.animate = Animate()



class AnimDict():
        def __init__(self):
    #animations dictionary
            #states
            self.idle_anim = {"index": 0, "frames": 8} 
            self.run_anim = {"index": 1, "frames": 8}

            self.jump_up_anim = {"index": 6, "frames": 3}
            self.jump_air_anim = {"index": 7, "frames": 3}
            self.jump_down_anim = {"index": 8, "frames": 3}
            #attacks
            self.jump_attack_anim = {"index": 9, "frames": 5}
            self.strike_1_anim = {"index": 10, "frames": 4} 
            self.strike_2_anim = {"index": 11, "frames": 4} 
            self.thrust_anim = {"index": 12, "frames": 4}
            self.sweep_anim =  {"index": 16, "frames": 5}
            #magic
            self.orb_anim = {"index": 18, "frames": 9} 
            self.breathe_anim = {"index": 19, "frames": 16} 
            self.magic_weapon_anim = {"index": 20, "frames": 12} 

            self.block_anim = {"index": 13, "frames": 7}
            self.parry_anim = {"index": 14, "frames": 6} 
            self.hurt_anim = {"index": 23, "frames": 5} 
            self.death_anim = {"index": 24, "frames": 12} 