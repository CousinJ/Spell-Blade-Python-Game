import anim
from coordinator import action_data

anim_dict = anim.AnimDict()


class Action():
    def __init__(self, anim_array, damage, recovery_speed, interuptable, reverse=False, action_id=None, stamina_cost=0):
        self.anim_array = anim_array
        self.damage = damage
        self.recovery_speed = recovery_speed
        self.interuptable = interuptable
        self.reverse = reverse
        # Stable string id keyed into coordinator.action_data (single source of
        # truth shared with the server). Used to publish/resolve attacks.
        self.action_id = action_id
        # Stamina the attacker spends; the client gates locally on this and the
        # server re-checks/deducts authoritatively.
        self.stamina_cost = stamina_cost


def _make(action_id, anim_dict_entry, *, reverse=False):
    """Build a client Action from the standardized anim + the shared data table.

    The anim_array is ``[anim_dict_entry, frames, _, is_effect_sheet]``. Every
    standardized hero animation is rendered from the EFFECT sheet, so the 4th
    element is always ``True``. damage / frames / stamina_cost are read from
    ``coordinator.action_data`` so the client can never drift from the server.
    """
    data = action_data.ACTIONS[action_id]
    anim_array = [anim_dict_entry, data.frames, False, True]
    return Action(
        anim_array,
        data.damage,
        data.frames,
        False,
        reverse=reverse,
        action_id=action_id,
        stamina_cost=data.stamina_cost,
    )


# --- standardized moveset (shared by every hero) ---------------------------
# Arrow-key bindings live in player.py: Up=jump_attack, Left=strike_1,
# Right=strike_2, Down=sweep. Space=block.
block = _make("block", anim_dict.block_anim)
jump_attack = _make("jump_attack", anim_dict.jump_attack_anim)
strike_1 = _make("strike_1", anim_dict.strike_1_anim)
strike_2 = _make("strike_2", anim_dict.strike_2_anim)
sweep = _make("sweep", anim_dict.sweep_anim)

# action_id -> Action, so the client can render an opponent's attack animation
# from the action_id that arrives over the network.
ACTION_BY_ID = {
    a.action_id: a
    for a in (block, jump_attack, strike_1, strike_2, sweep)
}
