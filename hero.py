
import actions

class MagicChar():
    def __init__(self):
        self.path_string = "./assets/sprite_sheets/magic-warrior-sheet.png"
        self.effect_path_string = "./assets/effect_sheets/magic-warrior-effect-sheet.png"
        self.name = "Torin"
        self.attack_one = actions.back_slash
        self.attack_two = actions.ice_lance
        self.attack_three = actions.quick_thrust
        
    def special_ability(self):
        print(' magic SPECIAL')


class FireChar():
    def __init__(self):
        self.path_string = "./assets/sprite_sheets/fire_warrior_sheet.png"
        self.effect_path_string = "./assets/effect_sheets/fire-warrior-effect-sheet.png"
        self.name = "Dravin"
        self.attack_one = actions.fire_slash
        self.attack_two = actions.fire_strike
        self.attack_three = actions.thrust
        
    def special_ability(self):
        print(' fire SPECIAL')

class ForestChar():
    def __init__(self):
        self.path_string = "./assets/sprite_sheets/forest-warrior-sheet.png"
        self.effect_path_string = "./assets/effect_sheets/forest-warrior-effect-sheet.png"
        self.name = "Rast"
        self.attack_one = actions.slash
        self.attack_two = actions.back_slash
        self.attack_three = actions.quick_thrust
        
    def special_ability(self):
        print(' air SPECIAL')
    



class IceChar():
    def __init__(self):
        self.path_string = "./assets/sprite_sheets/ice-warrior-sheet.png"
        self.effect_path_string = "./assets/effect_sheets/ice-warrior-effect-sheet.png"
        self.name = "Tyros"
        self.attack_one = actions.ice_lance
        self.attack_two = actions.frost_sweep
        self.attack_three = actions.overhead_strike
        
    def special_ability(self):
        print('ice SPECIAL')



class Hero():
    def __init__(self):
        
        self.hero = False
    def select_hero(self, hero):
        self.hero = hero
    def special_ability(self):
        self.hero.special_ability()