# Galaga-like game in Python (Pygame)
# --------------------------------------------------
# Features:
# - Player ship with smooth movement and autofire cooldown
# - Enemy formation (bees, butterflies, bosses) that enter in waves
# - Random "dive" attacks that target the player with wavy motion
# - Enemy bullets, player lives, invulnerability on respawn
# - Level progression with difficulty ramp
# - Minimalist starfield background and on-screen UI
#
# Controls:
#   Left/Right Arrows or A/D  : Move
#   Space                     : Shoot (hold for autofire)
#   P                         : Pause
#   Esc                       : Quit
#   Enter/Space               : Start from Title / Restart at Game Over
#
# Requirements:
#   pip install pygame
#
# Run:
#   python galaga_clone.py
#
# Tested with: Pygame 2.x
# --------------------------------------------------

import math
import os
import json
import random
import sys
from dataclasses import dataclass

import pygame

# ----------------------- Config -----------------------
WIDTH, HEIGHT = 480, 640
FPS = 60

# Colors
WHITE = (240, 240, 240)
GREY = (110, 110, 110)
BLACK = (10, 10, 16)
RED = (220, 80, 80)
YELLOW = (240, 220, 90)
BLUE = (90, 170, 255)
CYAN = (90, 240, 240)
GREEN = (120, 220, 120)
PURPLE = (200, 120, 240)
ORANGE = (255, 170, 90)

FONT_NAME = None  # default pygame font
HIGHSCORE_PATH = "galaga_highscore.json"

# Gameplay tuning
PLAYER_SPEED = 260.0      # px / sec
PLAYER_COOLDOWN = 0.18    # seconds between shots
PLAYER_INVULN_TIME = 1.5  # seconds after respawn
PLAYER_LIVES = 3

BULLET_SPEED = 480.0      # px / sec
ENEMY_BULLET_SPEED = 220.0
ENEMY_BULLET_CHANCE_PER_SEC = 0.30   # per enemy in formation
DIVE_INTERVAL = (1.8, 3.4)           # seconds between dive selections
MAX_SIMULTANEOUS_DIVERS = 3

ENTER_DURATION = 2.2      # seconds to reach formation during entry
RETURN_SPEED = 160.0      # px / sec when returning to formation
DIVE_SPEED = (160.0, 220.0)  # px / sec
DIVE_WAVE_AMP = (40.0, 90.0)  # px
DIVE_WAVE_FREQ = (2.5, 4.5)   # Hz

LEVEL_SPEED_RAMP = 1.06   # multiplier applied to speeds each level
LEVEL_SHOOT_RAMP = 1.08   # enemy fire chance multiplier per level

STAR_COUNT = 120

# Formation
COLUMNS = 10
ROWS = 5
X_GAP = 36
Y_GAP = 32
FORMATION_TOP = 100


# ----------------------- Utilities -----------------------
def clamp(x, lo, hi):
    return max(lo, min(hi, x))


def load_high_score():
    if os.path.exists(HIGHSCORE_PATH):
        try:
            with open(HIGHSCORE_PATH, "r") as f:
                data = json.load(f)
                return int(data.get("highscore", 0))
        except Exception:
            return 0
    return 0


def save_high_score(score):
    try:
        with open(HIGHSCORE_PATH, "w") as f:
            json.dump({"highscore": int(score)}, f)
    except Exception:
        pass


# ----------------------- Visual helpers -----------------------
def make_player_surface():
    # Make a small triangular ship
    w, h = 28, 22
    surf = pygame.Surface((w, h), pygame.SRCALPHA)
    # Body
    pygame.draw.polygon(surf, WHITE, [(w//2, 0), (0, h-2), (w-1, h-2)])
    # Cockpit
    pygame.draw.polygon(surf, CYAN, [(w//2, 4), (w//2-6, h-6), (w//2+6, h-6)])
    # Outline
    pygame.draw.polygon(surf, GREY, [(w//2, 0), (0, h-2), (w-1, h-2)], 1)
    return surf


def make_enemy_surface(kind):
    # Different shapes/colors for enemy "types": bee, butterfly, boss
    if kind == "bee":
        base = YELLOW
        accent = ORANGE
    elif kind == "butterfly":
        base = BLUE
        accent = CYAN
    else:  # boss
        base = PURPLE
        accent = RED

    w, h = 28, 20
    surf = pygame.Surface((w, h), pygame.SRCALPHA)
    # Wings / body (simple stylistic)
    pygame.draw.rect(surf, base, (2, 6, w-4, 10), border_radius=4)
    pygame.draw.rect(surf, accent, (w//2-3, 2, 6, h-4), border_radius=3)
    pygame.draw.rect(surf, GREY, (0, 0, w, h), 1, border_radius=5)
    return surf


def make_bullet_surface(color=WHITE):
    surf = pygame.Surface((3, 10), pygame.SRCALPHA)
    pygame.draw.rect(surf, color, (0, 0, 3, 10), border_radius=1)
    return surf


# ----------------------- Starfield -----------------------
@dataclass
class Star:
    x: float
    y: float
    speed: float
    size: int

    def update(self, dt):
        self.y += self.speed * dt
        if self.y > HEIGHT + self.size:
            self.y = -self.size
            self.x = random.uniform(0, WIDTH)

    def draw(self, screen):
        pygame.draw.rect(screen, WHITE, (int(self.x), int(self.y), self.size, self.size))


# ----------------------- Sprites -----------------------
class Player(pygame.sprite.Sprite):
    def __init__(self, x, y):
        super().__init__()
        self.base_image = make_player_surface()
        self.image = self.base_image.copy()
        self.rect = self.image.get_rect(center=(x, y))
        self.speed = PLAYER_SPEED
        self.cooldown = PLAYER_COOLDOWN
        self._cooldown_timer = 0.0
        self.alive = True
        self.invuln_timer = 0.0
        self.lives = PLAYER_LIVES

    def reset_position(self):
        self.rect.centerx = WIDTH // 2
        self.rect.bottom = HEIGHT - 16

    def kill_and_respawn(self):
        self.lives -= 1
        self.invuln_timer = PLAYER_INVULN_TIME
        self._cooldown_timer = 0.0
        self.reset_position()

    def update(self, dt, keys):
        # Movement
        dx = 0.0
        if keys[pygame.K_LEFT] or keys[pygame.K_a]:
            dx -= 1.0
        if keys[pygame.K_RIGHT] or keys[pygame.K_d]:
            dx += 1.0
        self.rect.x += int(dx * self.speed * dt)
        self.rect.x = clamp(self.rect.x, 6, WIDTH - self.rect.width - 6)

        # Timers
        self._cooldown_timer = max(0.0, self._cooldown_timer - dt)
        if self.invuln_timer > 0:
            self.invuln_timer = max(0.0, self.invuln_timer - dt)

    def can_shoot(self):
        return self._cooldown_timer <= 0.0

    def shoot(self, player_bullets_group, all_sprites_group):
        if self.can_shoot():
            bullet = PlayerBullet(self.rect.centerx, self.rect.top - 6)
            player_bullets_group.add(bullet)
            all_sprites_group.add(bullet)
            self._cooldown_timer = self.cooldown

    def draw_invulnerability(self, screen, t):
        # Flicker effect
        if int(t * 20) % 2 == 0:
            pygame.draw.circle(screen, CYAN, self.rect.center, self.rect.width, 1)


class PlayerBullet(pygame.sprite.Sprite):
    def __init__(self, x, y):
        super().__init__()
        self.image = make_bullet_surface(WHITE)
        self.rect = self.image.get_rect(center=(x, y))
        self.speed = BULLET_SPEED

    def update(self, dt):
        self.rect.y -= int(self.speed * dt)
        if self.rect.bottom < 0:
            self.kill()


class EnemyBullet(pygame.sprite.Sprite):
    def __init__(self, x, y, vx, vy):
        super().__init__()
        self.image = make_bullet_surface(RED)
        self.rect = self.image.get_rect(center=(x, y))
        self.vx = vx
        self.vy = vy

    def update(self, dt):
        self.rect.x += int(self.vx * dt)
        self.rect.y += int(self.vy * dt)
        if (self.rect.top > HEIGHT + 12 or self.rect.right < -12 or self.rect.left > WIDTH + 12):
            self.kill()


class Enemy(pygame.sprite.Sprite):
    def __init__(self, kind, formation_pos, enter_from_left=True, enter_delay=0.0):
        super().__init__()
        self.kind = kind
        self.base_image = make_enemy_surface(kind)
        self.image = self.base_image.copy()
        self.rect = self.image.get_rect(center=(
            -40 if enter_from_left else WIDTH + 40,
            -30
        ))
        self.formation_pos = pygame.Vector2(formation_pos)
        self.state = "entering"  # entering -> formation -> diving -> returning
        self.t = -enter_delay
        self.enter_from_left = enter_from_left
        # Control point for bezier curve
        ctrl_x = WIDTH * (0.25 if enter_from_left else 0.75)
        self.ctrl = pygame.Vector2(ctrl_x, random.uniform(40, 180))

        # Pos (float) for smooth motion
        self.pos = pygame.Vector2(self.rect.center)
        self.vx = 0.0
        self.phase = random.uniform(0, math.tau)

        # Attributes per kind
        self.hp = 2 if kind == "boss" else 1
        self.score_value = {"bee": 50, "butterfly": 80, "boss": 150}[kind]

        self._shoot_cooldown = random.uniform(0.3, 1.0)

    def set_level_scalers(self, speed_scale=1.0):
        # Not exhaustive; called each level to bump some movement
        self.speed_scale = speed_scale

    def update(self, dt, player, enemy_bullets_group, all_sprites_group,
               shoot_chance_per_sec):
        if self.state == "entering":
            self.update_entering(dt)
        elif self.state == "formation":
            self.update_formation(dt, shoot_chance_per_sec, player,
                                  enemy_bullets_group, all_sprites_group)
        elif self.state == "diving":
            self.update_diving(dt, player, enemy_bullets_group, all_sprites_group)
        elif self.state == "returning":
            self.update_returning(dt)
        self.rect.center = (int(self.pos.x), int(self.pos.y))

    def bezier(self, p0, p1, p2, u):
        # Quadratic bezier
        return (1 - u) * (1 - u) * p0 + 2 * (1 - u) * u * p1 + u * u * p2

    def update_entering(self, dt):
        self.t += dt
        if self.t <= 0.0:
            return
        u = min(self.t / (ENTER_DURATION / getattr(self, "speed_scale", 1.0)), 1.0)
        p0 = pygame.Vector2(-40, -30) if self.enter_from_left else pygame.Vector2(WIDTH + 40, -30)
        p = self.bezier(p0, self.ctrl, self.formation_pos, u)
        self.pos.update(p.x, p.y)
        if u >= 1.0:
            self.state = "formation"
            # snap to formation
            self.pos.update(self.formation_pos.x, self.formation_pos.y)

    def update_formation(self, dt, shoot_chance_per_sec, player,
                         enemy_bullets_group, all_sprites_group):
        # Idle slight bob
        self.phase += dt * 2.0
        offset = math.sin(self.phase * 2.0) * 4.0
        self.pos.x = self.formation_pos.x + math.sin(self.phase) * 6.0
        self.pos.y = self.formation_pos.y + offset

        # Random chance to shoot (low)
        self._shoot_cooldown = max(0.0, self._shoot_cooldown - dt)
        if self._shoot_cooldown <= 0.0:
            if random.random() < shoot_chance_per_sec * dt:
                self.fire_at_player(player, enemy_bullets_group, all_sprites_group, speed=ENEMY_BULLET_SPEED)
                self._shoot_cooldown = random.uniform(0.75, 1.6)

    def start_dive(self, player):
        if self.state != "formation":
            return
        self.state = "diving"
        self.phase = random.uniform(0, math.tau)
        self.wave_amp = random.uniform(*DIVE_WAVE_AMP)
        self.wave_freq = random.uniform(*DIVE_WAVE_FREQ)
        self.base_vx = 0.0
        self.vx = 0.0
        self.vy = random.uniform(*DIVE_SPEED) * getattr(self, "speed_scale", 1.0)
        self.dive_target_x = player.rect.centerx

    def update_diving(self, dt, player, enemy_bullets_group, all_sprites_group):
        # Gradually steer toward the player's x coordinate at dive start
        dx = self.dive_target_x - self.pos.x
        steer = clamp(dx * 0.8, -220, 220)  # px/sec; strong pull early in dive
        self.vx = 0.85 * self.vx + 0.15 * steer
        self.phase += self.wave_freq * dt * math.tau
        wave = math.sin(self.phase) * self.wave_amp
        self.pos.x += (self.vx + wave) * dt
        self.pos.y += self.vy * dt

        # Occasional shot while diving
        if random.random() < 0.65 * dt:
            self.fire_at_player(player, enemy_bullets_group, all_sprites_group, speed=ENEMY_BULLET_SPEED * 1.15)

        # Off-screen => return from top toward formation
        if self.pos.y > HEIGHT + 30:
            self.state = "returning"
            self.pos.y = -20
            # drift roughly toward column
            self.pos.x = clamp(self.formation_pos.x + random.uniform(-60, 60), 10, WIDTH - 10)

    def update_returning(self, dt):
        to_form = self.formation_pos - self.pos
        dist = to_form.length()
        if dist < 6:
            self.pos.update(self.formation_pos.x, self.formation_pos.y)
            self.state = "formation"
            return
        dir_vec = to_form.normalize()
        self.pos += dir_vec * RETURN_SPEED * getattr(self, "speed_scale", 1.0) * dt

    def take_hit(self):
        self.hp -= 1
        if self.hp <= 0:
            self.kill()
            return True  # died
        return False

    def fire_at_player(self, player, enemy_bullets_group, all_sprites_group, speed=ENEMY_BULLET_SPEED):
        # Aim roughly at player
        src = pygame.Vector2(self.rect.centerx, self.rect.bottom)
        dst = pygame.Vector2(player.rect.centerx, player.rect.centery)
        v = (dst - src)
        if v.length_squared() == 0:
            v = pygame.Vector2(0, 1)
        else:
            v = v.normalize()
        vx, vy = v.x * speed, v.y * speed
        bullet = EnemyBullet(src.x, src.y, vx, vy)
        enemy_bullets_group.add(bullet)
        all_sprites_group.add(bullet)


# ----------------------- Fleet (formation manager) -----------------------
class Fleet:
    def __init__(self, level=1):
        self.level = level
        self.speed_scale = (LEVEL_SPEED_RAMP ** (level - 1))
        self.shoot_scale = (LEVEL_SHOOT_RAMP ** (level - 1))
        self.enemies = pygame.sprite.Group()

        # Staggered entry: alternate sides and add delay across formation
        left_first = True
        for r in range(ROWS):
            for c in range(COLUMNS):
                kind = self.kind_for_row(r)
                fx = 60 + c * X_GAP
                fy = FORMATION_TOP + r * Y_GAP
                enter_from_left = left_first if (c % 2 == 0) else (not left_first)
                enter_delay = 0.06 * (r * COLUMNS + c)
                e = Enemy(kind, (fx, fy), enter_from_left=enter_from_left, enter_delay=enter_delay)
                e.set_level_scalers(self.speed_scale)
                self.enemies.add(e)
            left_first = not left_first

        self._dive_timer = random.uniform(*DIVE_INTERVAL)
        self._max_divers = MAX_SIMULTANEOUS_DIVERS + (level // 3)

    def kind_for_row(self, r):
        # Top rows are tougher
        if r == 0:
            return "boss"
        elif r in (1, 2):
            return "butterfly"
        else:
            return "bee"

    def update(self, dt, player, enemy_bullets_group, all_sprites_group):
        # Update every enemy
        for e in list(self.enemies):
            e.update(dt, player, enemy_bullets_group, all_sprites_group,
                     ENEMY_BULLET_CHANCE_PER_SEC * self.shoot_scale)

        # Schedule dives
        self._dive_timer -= dt
        if self._dive_timer <= 0.0:
            self._dive_timer = random.uniform(*DIVE_INTERVAL) / max(0.6, min(1.6, self.speed_scale))
            divers = [e for e in self.enemies if e.state == "diving"]
            if len(divers) < self._max_divers:
                candidates = [e for e in self.enemies if e.state == "formation"]
                if candidates:
                    random.choice(candidates).start_dive(player)

    def alive(self):
        return len(self.enemies)

    def draw(self, screen):
        self.enemies.draw(screen)


# ----------------------- Game -----------------------
class Game:
    def __init__(self):
        pygame.init()
        pygame.display.set_caption("Galaga (Python)")
        self.screen = pygame.display.set_mode((WIDTH, HEIGHT))
        self.clock = pygame.time.Clock()
        self.font_small = pygame.font.Font(FONT_NAME, 18)
        self.font = pygame.font.Font(FONT_NAME, 24)
        self.font_big = pygame.font.Font(FONT_NAME, 36)

        # Starfield
        self.stars = [Star(random.uniform(0, WIDTH),
                           random.uniform(0, HEIGHT),
                           random.uniform(20, 80),
                           random.choice([1, 1, 1, 2])) for _ in range(STAR_COUNT)]

        # Sprites
        self.all_sprites = pygame.sprite.Group()
        self.player_bullets = pygame.sprite.Group()
        self.enemy_bullets = pygame.sprite.Group()

        # Player
        self.player = Player(WIDTH // 2, HEIGHT - 40)
        self.player.reset_position()
        self.all_sprites.add(self.player)

        # Fleet / Level
        self.level = 1
        self.fleet = Fleet(level=self.level)

        self.score = 0
        self.highscore = load_high_score()

        self.state = "TITLE"  # TITLE -> PLAYING -> GAME_OVER
        self.paused = False

    def reboot_level(self):
        # Clear bullets
        for s in list(self.player_bullets):
            s.kill()
        for s in list(self.enemy_bullets):
            s.kill()
        # New fleet
        self.fleet = Fleet(level=self.level)

    def run(self):
        running = True
        while running:
            dt = self.clock.tick(FPS) / 1000.0

            # Events
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        running = False
                    if self.state == "TITLE":
                        if event.key in (pygame.K_RETURN, pygame.K_SPACE):
                            self.state = "PLAYING"
                    elif self.state == "GAME_OVER":
                        if event.key in (pygame.K_RETURN, pygame.K_SPACE):
                            self.reset_game()
                    elif self.state == "PLAYING":
                        if event.key == pygame.K_p:
                            self.paused = not self.paused

            keys = pygame.key.get_pressed()
            if self.state == "PLAYING" and not self.paused:
                # Update world
                self.player.update(dt, keys)
                if keys[pygame.K_SPACE]:
                    self.player.shoot(self.player_bullets, self.all_sprites)

                self.fleet.update(dt, self.player, self.enemy_bullets, self.all_sprites)

                # Update bullets
                for b in list(self.player_bullets):
                    b.update(dt)
                for b in list(self.enemy_bullets):
                    b.update(dt)

                # Collisions: Player bullet -> Enemy
                hits = pygame.sprite.groupcollide(self.fleet.enemies, self.player_bullets,
                                                  False, True)
                for enemy, bullet_list in hits.items():
                    died = enemy.take_hit()
                    if died:
                        self.score += enemy.score_value

                # Collisions: Enemy bullet -> Player
                if self.player.invuln_timer <= 0.0:
                    if pygame.sprite.spritecollideany(self.player, self.enemy_bullets):
                        # Remove bullets that hit
                        for b in pygame.sprite.spritecollide(self.player, self.enemy_bullets, dokill=True):
                            pass
                        self.player.kill_and_respawn()
                        if self.player.lives < 0:
                            self.state = "GAME_OVER"
                            self.highscore = max(self.highscore, self.score)
                            save_high_score(self.highscore)

                # Collisions: Enemy (diving/returning) -> Player
                if self.player.invuln_timer <= 0.0:
                    for e in self.fleet.enemies:
                        if e.state != "formation" and self.player.rect.colliderect(e.rect):
                            self.player.kill_and_respawn()
                            if self.player.lives < 0:
                                self.state = "GAME_OVER"
                                self.highscore = max(self.highscore, self.score)
                                save_high_score(self.highscore)
                            break

                # Level cleared?
                if self.fleet.alive() == 0:
                    self.level += 1
                    self.reboot_level()

            # Update stars every state (nice background)
            for s in self.stars:
                s.update(dt)

            # Draw
            self.draw()

        pygame.quit()
        sys.exit(0)

    def reset_game(self):
        self.score = 0
        self.level = 1
        self.player.lives = PLAYER_LIVES
        self.player.invuln_timer = 0.0
        self.player.reset_position()
        self.fleet = Fleet(level=self.level)
        for b in list(self.player_bullets):
            b.kill()
        for b in list(self.enemy_bullets):
            b.kill()
        self.state = "PLAYING"
        self.paused = False

    # ----------------------- Rendering -----------------------
    def draw(self):
        self.screen.fill(BLACK)
        # Starfield
        for s in self.stars:
            s.draw(self.screen)

        if self.state == "TITLE":
            self.draw_title()
        elif self.state == "GAME_OVER":
            self.draw_game_over()
        else:
            # Draw sprites
            self.fleet.draw(self.screen)
            self.all_sprites.draw(self.screen)

            # Invuln ring
            if self.player.invuln_timer > 0:
                self.player.draw_invulnerability(self.screen, self.player.invuln_timer)

            # UI
            self.draw_ui()

            if self.paused:
                self.draw_paused()

        pygame.display.flip()

    def draw_ui(self):
        # Score / Highscore / Lives / Level
        score_s = self.font.render(f"SCORE  {self.score}", True, WHITE)
        self.screen.blit(score_s, (12, 8))

        hs_s = self.font.render(f"HI  {max(self.highscore, self.score)}", True, YELLOW)
        self.screen.blit(hs_s, (WIDTH - hs_s.get_width() - 12, 8))

        lvl_s = self.font_small.render(f"LEVEL {self.level}", True, GREY)
        self.screen.blit(lvl_s, (12, 32))

        # Lives
        life_icon = make_player_surface()
        y = 36
        for i in range(max(0, self.player.lives)):
            x = 110 + i * (life_icon.get_width() + 6)
            self.screen.blit(life_icon, (x, y))

    def draw_centered_text(self, lines, colors, big=False, y_offset=0):
        y = HEIGHT // 2 + y_offset
        for i, text in enumerate(lines):
            font = self.font_big if (big and i == 0) else self.font
            surface = font.render(text, True, colors[i])
            rect = surface.get_rect(center=(WIDTH // 2, y + i * 36))
            self.screen.blit(surface, rect)

    def draw_title(self):
        title = "GALAGA"
        self.draw_centered_text(
            [title, "Press Enter / Space to Start"],
            [CYAN, WHITE],
            big=True,
            y_offset=-60,
        )
        controls = [
            "Controls:",
            "Left/Right or A/D to move",
            "Space to shoot, P to pause",
            "Esc to quit",
        ]
        for i, line in enumerate(controls):
            surface = self.font.render(line, True, GREY if i == 0 else WHITE)
            rect = surface.get_rect(center=(WIDTH // 2, HEIGHT // 2 + 36 + i * 24))
            self.screen.blit(surface, rect)

    def draw_game_over(self):
        self.draw_centered_text(
            ["GAME OVER", f"Score: {self.score}", "Press Enter / Space to Restart"],
            [RED, WHITE, WHITE],
            big=True,
            y_offset=-20,
        )

    def draw_paused(self):
        surf = self.font_big.render("PAUSED", True, YELLOW)
        rect = surf.get_rect(center=(WIDTH // 2, HEIGHT // 2))
        # subtle box
        box = pygame.Surface((rect.width + 40, rect.height + 20), pygame.SRCALPHA)
        box.fill((0, 0, 0, 130))
        box_rect = box.get_rect(center=(WIDTH // 2, HEIGHT // 2))
        self.screen.blit(box, box_rect)
        self.screen.blit(surf, rect)


# ----------------------- Main -----------------------
def main():
    Game().run()


if __name__ == "__main__":
    main()