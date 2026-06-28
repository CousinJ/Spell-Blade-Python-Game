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

    def update_anim(self,p,image, animator):
        if not p.action.reverse:
            
            image_plus_frame = animator.animate_player_action(p.action.anim_array, image, p)
        elif p.action.reverse:
            image_plus_frame = animator.animate_reverse_action(p.action.anim_array, image,p)
            
        return image_plus_frame
        


class HurtState():
    def __init__(self, manager):
        self.anim = anim_dict.hurt_anim
        self.manager = manager
    def update(self, p):
        # The hurt clip plays once; clear the flag when it has run its frames.
        if p.frame_index >= self.anim["frames"]:
            p.is_hurt = False
    def update_anim(self, p, image, animator):
        return animator.animate_loop_anim(self.anim, image, p)


class DeadState():
    def __init__(self, manager):
        self.anim = anim_dict.death_anim
        self.manager = manager
    def update(self, p):
        pass  # terminal: the fighter stays down
    def update_anim(self, p, image, animator):
        return animator.animate_hold_anim(self.anim, image, p)


def label_for(p):
    """A wire-friendly string label for a player's current visible state.

    Published in ``player_state`` so the opponent can pick the right looping
    animation (idle / running / blocking). Acting/hurt/dead are driven by
    discrete events (attack messages, snapshot HP) rather than this label.
    """
    if not p.alive:
        return "dead"
    if getattr(p, "is_hurt", False):
        return "hurt"
    if p.is_acting:
        return "acting"
    if p.is_blocking:
        return "blocking"
    if p.moving:
        return "running"
    return "idle"


class Manager():
    def __init__(self):
        self.idle = IdleState(self)
        self.running = RunningState(self)
        self.acting = ActingState(self)
        self.blocking = BlockingState(self)
        self.hurt = HurtState(self)
        self.dead = DeadState(self)
        self.acting_timer = 0

    def update(self, p):
        # Priority: death > hurt > acting > blocking > movement.
        if not p.alive:
            p.state = self.switch_state(p, self.dead)
            p.state.update(p)
            return

        if getattr(p, "is_hurt", False):
            p.state = self.switch_state(p, self.hurt)
            p.state.update(p)
            return

        if p.moving:
            p.state = self.switch_state(p, self.running)
        else:
            p.state = self.switch_state(p, self.idle)

        if p.is_acting:
            p.state = self.switch_state(p, self.acting)
        p.state.update(p)

        if p.is_blocking and not p.is_acting:
            p.state = self.switch_state(p, self.blocking)


    def switch_state(self, p, state):
        
        p.state = state
        return p.state
    
            
    

    
    
    

