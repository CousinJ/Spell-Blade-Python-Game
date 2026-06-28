import pygame
import hero
import game_settings
import actions


# Arrow-key -> attack binding for the standardized moveset. A/D stay movement,
# Space stays block (handled separately).
ATTACK_KEYS = {
    pygame.K_UP: actions.jump_attack,
    pygame.K_LEFT: actions.strike_1,
    pygame.K_RIGHT: actions.strike_2,
    pygame.K_DOWN: actions.sweep,
}


class Player():
    def __init__(self, x, y, width, height, color, direction):
        self.x = x
        self.y = y
        self.width = width
        self.height = height
        self.color = color
        self.rect = (x,y,width,height)
        self.acc = .1
        self.vel = 0
        self.max_vel = 1
        self.direction = direction
        self.hero = hero.Hero()
        self.frame_index = 0
        self.state = False
        self.moving = False

        self.is_acting = False
        self.action = False

        self.is_blocking = False

        # --- combat / health (server-authoritative; mirrored locally) ---
        self.max_hp = game_settings.MAX_HP
        self.hp = self.max_hp
        self.alive = True
        self.is_hurt = False
        self.rounds_won = 0

        # --- stamina + parry (server-authoritative; mirrored locally) ---
        self.max_stamina = game_settings.MAX_STAMINA
        self.stamina = self.max_stamina
        self.is_parrying = False
        self._blocks_taken = 0  # mirror of the snapshot counter for parry edges


    def draw(self, win):
        pygame.draw.rect(win, self.color, self.rect)


    def move(self, dt):
        keys = pygame.key.get_pressed()
        dt = dt / 2
        if not self.is_acting:
            # Acceleration based on key press
            if keys[pygame.K_a]:
                self.vel += self.acc
                self.direction = -1
                self.moving = True
            elif keys[pygame.K_d]:
                self.vel += self.acc
                self.direction = 1
                self.moving = True
            else:
                # Slow down if no key pressed

                self.vel = 0
                self.moving = False

            # Limit velocity to max velocity
            if abs(self.vel) > self.max_vel:
                self.vel = self.max_vel


            # Update position
            self.x += self.vel * self.direction * dt
            # Keep the fighter on-screen.
            self.x = max(0, min(game_settings.WIDTH, self.x))

        self.update()

    def attack(self):
        """Read the arrow attack keys. Returns the started action's id, or None.

        The standardized moveset is the same for every hero: Up=jump_attack,
        Left=strike_1, Right=strike_2, Down=sweep. The attack is gated locally on
        stamina (mirrored from the server) so it simply won't fire without enough
        -- the server re-checks and deducts authoritatively.
        """
        keys = pygame.key.get_pressed()
        if not self.is_acting:
            started = None
            for key, action in ATTACK_KEYS.items():
                if keys[key]:
                    started = action
                    break
            if started and self.stamina >= started.stamina_cost:
                self.action = started
                self.is_acting = True
                self.frame_index = 0
                return started.action_id
        return None

    def block(self):
        keys = pygame.key.get_pressed()
        if keys[pygame.K_SPACE]:
               self.is_blocking = True
        else:
            self.is_blocking = False

    def update(self):

        self.rect = (self.x, self.y, self.width, self.height)

    # ----------------------------------------------------------- networking
    def hero_name(self):
        """Class-name string of the selected hero, or None."""
        if self.hero and self.hero.hero:
            return type(self.hero.hero).__name__
        return None

    def to_dict(self):
        """Wire-friendly snapshot of this player's transmissible state."""
        return {
            "x": self.x,
            "direction": self.direction,
            "moving": self.moving,
            "is_blocking": self.is_blocking,
            "hp": self.hp,
            "alive": self.alive,
            "hero": self.hero_name(),
        }

    def apply_health(self, hp, alive):
        """Apply an authoritative HP/alive update from a snapshot.

        Triggers the hurt animation on a damage tick and the death animation on
        the alive -> dead transition (resets frame_index so the clip plays from
        the start).
        """
        if alive and hp < self.hp:
            self.is_hurt = True
            self.frame_index = 0
        if self.alive and not alive:
            self.frame_index = 0
        self.hp = hp
        self.alive = alive
