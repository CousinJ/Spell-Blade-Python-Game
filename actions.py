import anim
anim_dict = anim.AnimDict()


class Action():
    def __init__(self, anim_array, damage, recovery_speed, interuptable, reverse=False ):
        self.anim_array = anim_array
        self.damage = damage
        self.recovery_speed = recovery_speed
        self.interuptable = interuptable
        self.reverse = reverse
        
# the anim_array is a 2d array that consists of index of 1. anim 2. frames )
block_anim_array = [anim_dict.block_anim, 7, False, True]
block = Action(block_anim_array, 0, 7, False, True)
        #ice actions
overhead_strike_anim_array = [anim_dict.strike_2_anim, 4, False, False]
ice_lance_anim_array = [anim_dict.thrust_anim, 4, False, True]  
frost_sweep_anim_array = [anim_dict.sweep_anim, 5, False, True]  
#add reverse flag for a reversed animation action
ice_lance = Action(ice_lance_anim_array, 22, 4, False)
frost_sweep = Action(frost_sweep_anim_array, 16, 4, False)
overhead_strike = Action(overhead_strike_anim_array, 20, 4, False)


        #forest actions
slash_anim_array = [anim_dict.strike_1_anim, 4, False, False]
back_slash_anim_array = [anim_dict.strike_1_anim, 4, False, True]
thrust_anim_array = [anim_dict.thrust_anim, 4, False, False]

slash = Action(slash_anim_array, 22, 4, False)
back_slash = Action(back_slash_anim_array, 16, 4, False)
quick_thrust = Action(thrust_anim_array, 20, 4, False, True)
thrust = Action(thrust_anim_array, 20, 4, False)

        # fire actions 
fire_strike_anim_array = [anim_dict.strike_2_anim, 4, False, True]
fire_slash_anim_array = [anim_dict.strike_1_anim, 4, False, True]
#thust for 3
fire_strike = Action(fire_strike_anim_array, 30, 4, False)
fire_slash = Action(fire_slash_anim_array, 25, 4, False)