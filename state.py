import anim
import actions
anim_dict = anim.AnimDict()
class IdleState():
    def __init__(self, manager):
        self.anim = anim_dict.idle_anim
        self.manager = manager
    def update(self, p):
        pass
            
                
    def update_anim(self, p, image, animator):
         image_plus_frame = animator.animate_player(self.anim, image, p )
         return image_plus_frame

class BlockingState():
    def __init__(self, manager):
        self.anim = anim_dict.block_anim
        self.manager = manager
    def update(self, p):
        pass
            
                
    def update_anim(self, p, image, animator):
         image_plus_frame = animator.animate_block(self.anim, image, p )
         
            
         return image_plus_frame


class RunningState():
    def __init__(self, manager):
        self.anim = anim_dict.run_anim
        self.manager = manager
    def update(self, p):
        
        pass
    def update_anim(self, p, image, animator):
        image_plus_frame = animator.animate_player(self.anim, image, p )
        return image_plus_frame

class ActingState():
    def __init__(self, manager):
        self.manager = manager
        
    def update(self,p):
        

        if p.frame_index >= p.action.anim_array[1]:
            
            p.is_acting = False
        print("ACTING")
        
    def update_anim(self,p,image, animator):
        if not p.action.reverse:
            
            image_plus_frame = animator.animate_player_action(p.action.anim_array, image, p)
        elif p.action.reverse:
            image_plus_frame = animator.animate_reverse_action(p.action.anim_array, image,p)
            
        return image_plus_frame
        


class Manager():
    def __init__(self):
        self.idle = IdleState(self)
        self.running = RunningState(self)
        self.acting = ActingState(self)
        self.blocking = BlockingState(self)
        self.acting_timer = 0
        
    def update(self, p):
        if p.moving:
            p.state = self.switch_state(p, self.running)
        else:
            p.state = self.switch_state(p, self.idle)

        if p.is_acting:
            p.state = self.switch_state(p, self.acting)
        p.state.update(p)

        if p.is_blocking:
            p.state = self.switch_state(p, self.blocking)


    def switch_state(self, p, state):
        
        p.state = state
        return p.state
    
            
    

    
    
    

