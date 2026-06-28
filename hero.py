
# Heroes share one standardized moveset now (see actions.py / arrow-key bindings
# in player.py), so a hero only carries its display name and its sprite/effect
# sheet paths -- no per-hero attack list.

class MagicChar():
    def __init__(self):
        self.path_string = "./assets/sprite_sheets/magic-warrior-sheet.png"
        self.effect_path_string = "./assets/effect_sheets/magic-warrior-effect-sheet.png"
        self.name = "Magic Guy"

    def special_ability(self):
        print(' magic SPECIAL')


class FireChar():
    def __init__(self):
        self.path_string = "./assets/sprite_sheets/fire_warrior_sheet.png"
        self.effect_path_string = "./assets/effect_sheets/fire-warrior-effect-sheet.png"
        self.name = "Fire Guy"

    def special_ability(self):
        print(' fire SPECIAL')

class ForestChar():
    def __init__(self):
        self.path_string = "./assets/sprite_sheets/forest-warrior-sheet.png"
        self.effect_path_string = "./assets/effect_sheets/forest-warrior-effect-sheet.png"
        self.name = "Air Guy"

    def special_ability(self):
        print(' air SPECIAL')




class IceChar():
    def __init__(self):
        self.path_string = "./assets/sprite_sheets/ice-warrior-sheet.png"
        self.effect_path_string = "./assets/effect_sheets/ice-warrior-effect-sheet.png"
        self.name = "Ice Guy"

    def special_ability(self):
        print('ice SPECIAL')



class Hero():
    def __init__(self):

        self.hero = False
    def select_hero(self, hero):
        self.hero = hero
    def special_ability(self):
        self.hero.special_ability()


# Class-name string (as sent over the wire / stored in coordinator.action_data)
# -> hero class, so a client can build the opponent's hero from a snapshot.
HERO_CLASSES = {
    "FireChar": FireChar,
    "MagicChar": MagicChar,
    "ForestChar": ForestChar,
    "IceChar": IceChar,
}


def hero_from_name(name):
    """Instantiate a hero class from its class-name string, or None."""
    cls = HERO_CLASSES.get(name)
    return cls() if cls else None
