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

          # Animate the player (all hero animations are rendered from the effect sheet)

        anim_frames = self.e_anims[animation["index"]]
        if p.direction < 0:
            anim_frames = self.reflect_e_anims[animation["index"]]


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
        
    def animate_loop_anim(self, animation, image, p):
        """Loop a single-row state animation (used for hurt / parry).

        Rendered from the effect sheet. Bounds-safe: falls back to the idle row
        if the sheet has fewer rows than the requested index, so missing art can
        never crash the game.
        """
        index = animation["index"]
        if index >= len(self.e_anims):
            index = 0
        anim_frames = self.reflect_e_anims[index] if p.direction < 0 else self.e_anims[index]
        frame_count = min(animation["frames"], len(anim_frames))
        if p.frame_index >= frame_count:
            p.frame_index = 0
        image = anim_frames[p.frame_index]
        p.frame_index += 1
        return image, p.frame_index

    def animate_hold_anim(self, animation, image, p):
        """Play a single-row animation once then hold the last frame (death).

        Rendered from the effect sheet.
        """
        index = animation["index"]
        if index >= len(self.e_anims):
            index = 0
        anim_frames = self.reflect_e_anims[index] if p.direction < 0 else self.e_anims[index]
        frame_count = min(animation["frames"], len(anim_frames))
        last = frame_count - 1
        if p.frame_index >= last:
            p.frame_index = last
            return anim_frames[last], p.frame_index
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
    # NOTE: "frames" values left unchanged for existing anims keep your tuned
    # behaviour; trailing comments flag where the sheet's actual filled-frame
    # count differs. Newly added rows are marked (inferred) -- rename to taste.
            #states
            self.idle_anim = {"index": 0, "frames": 8}
            self.run_anim = {"index": 1, "frames": 8}
            self.walk_anim = {"index": 2, "frames": 8}        
            self.dash_anim = {"index": 3, "frames": 7}        
            self.slide_anim = {"index": 4, "frames": 7}    
            self.roll_anim = {"index": 5, "frames": 7}         

            self.jump_up_anim = {"index": 6, "frames": 3}
            self.jump_air_anim = {"index": 7, "frames": 3}
            self.jump_down_anim = {"index": 8, "frames": 3}
            #attacks
            self.jump_attack_anim = {"index": 9, "frames": 5}
            self.strike_1_anim = {"index": 10, "frames": 4}
            self.strike_2_anim = {"index": 11, "frames": 4}
            self.thrust_anim = {"index": 12, "frames": 4}      # sheet has 5 filled frames
            self.kneel_anim = {"index": 15, "frames": 8}      
            self.sweep_anim =  {"index": 16, "frames": 5}
            #magic
            
            self.orb_anim = {"index": 18, "frames": 9}
            self.breathe_anim = {"index": 19, "frames": 16}
            self.magic_weapon_anim = {"index": 20, "frames": 12}  # sheet has 8 filled frames (EFFEECT SHEET WILL FADE MAGIC WEAPON AT THIS INDEX)
            

            #defense / reactions
            self.block_anim = {"index": 13, "frames": 7}       # sheet has 8 filled frames
            self.parry_anim = {"index": 14, "frames": 6}
            self.hurt_anim = {"index": 23, "frames": 5}        # sheet has 4 filled frames
            self.death_anim = {"index": 24, "frames": 12}      # sheet has 11 filled frames

            #misc
            self.ide_ladder_anim = {"index": 21, "frames": 4}     
            self.hop_off_anim = {"index": 22, "frames": 5}      