import anim
anim_dict = anim.AnimDict()


class Action():
    def __init__(self, anim_array, damage, recovery_speed, interuptable, reverse=False, action_id=None ):
        self.anim_array = anim_array
        self.damage = damage
        self.recovery_speed = recovery_speed
        self.interuptable = interuptable
        self.reverse = reverse
        # Stable string id keyed into coordinator.action_data (single source of
        # truth shared with the server). Used to publish/resolve attacks.
        self.action_id = action_id

# the anim_array is a 2d array that consists of index of 1. anim 2. frames )
block_anim_array = [anim_dict.block_anim, 7, False, True]
block = Action(block_anim_array, 0, 7, False, True, action_id="block")
        #ice actions
overhead_strike_anim_array = [anim_dict.strike_2_anim, 4, False, False]
ice_lance_anim_array = [anim_dict.thrust_anim, 4, False, True]
frost_sweep_anim_array = [anim_dict.sweep_anim, 5, False, True]
#add reverse flag for a reversed animation action
ice_lance = Action(ice_lance_anim_array, 22, 4, False, action_id="ice_lance")
frost_sweep = Action(frost_sweep_anim_array, 16, 4, False, action_id="frost_sweep")
overhead_strike = Action(overhead_strike_anim_array, 20, 4, False, action_id="overhead_strike")


        #forest actions
slash_anim_array = [anim_dict.strike_1_anim, 4, False, False]
back_slash_anim_array = [anim_dict.strike_1_anim, 4, False, True]
thrust_anim_array = [anim_dict.thrust_anim, 4, False, False]

slash = Action(slash_anim_array, 22, 4, False, action_id="slash")
back_slash = Action(back_slash_anim_array, 16, 4, False, action_id="back_slash")
quick_thrust = Action(thrust_anim_array, 20, 4, False, True, action_id="quick_thrust")
thrust = Action(thrust_anim_array, 20, 4, False, action_id="thrust")

        # fire actions
fire_strike_anim_array = [anim_dict.strike_2_anim, 4, False, True]
fire_slash_anim_array = [anim_dict.strike_1_anim, 4, False, True]
#thust for 3
fire_strike = Action(fire_strike_anim_array, 30, 4, False, action_id="fire_strike")
fire_slash = Action(fire_slash_anim_array, 25, 4, False, action_id="fire_slash")

# action_id -> Action, so the client can render an opponent's attack animation
# from the action_id that arrives over the network.
ACTION_BY_ID = {
    a.action_id: a
    for a in (
        block, ice_lance, frost_sweep, overhead_strike,
        slash, back_slash, quick_thrust, thrust, fire_strike, fire_slash,
    )
}
