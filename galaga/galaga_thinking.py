"""
Galaga-style arcade shooter in Python with pygame
-------------------------------------------------
Controls:
  • Left/Right or A/D = Move
  • Space = Shoot
  • P = Pause
  • R = Restart after game over
  • Esc = Quit

Setup:
  pip install pygame
  python galaga_clone.py

Notes:
  - Pure code: no external assets. All ships are vector-drawn.
  - Inspired by Galaga but not a 1:1 clone.
"""
from __future__ import annotations
import math
import random
import sys
from dataclasses import dataclass

import pygame

# --------------------------- Config --------------------------- #
WIDTH, HEIGHT = 480, 640
FPS = 60

# Gameplay tuning
PLAYER_SPEED = 280
PLAYER_COOLDOWN = 0.22  # seconds between shots
PLAYER_BULLET_SPEED = -520
ENEMY_BULLET_SPEED = 280
ENEMY_FORMATION_SPEED = 45  # horizontal drift speed
ENEMY_DIVE_SPEED = 180
ENEMY_ZIGZAG_FREQ = 3.2
ENEMY_ZIGZAG_AMP = 80
STAR_COUNT = 90

# Colors
BLACK = (10, 10, 16)
WHITE = (240, 240, 240)
GREEN = (65, 255, 160)
RED = (255, 80, 95)
YELLOW = (255, 214, 64)
CYAN = (64, 220, 255)
PURPLE = (190, 120, 255)

# --------------------------- Utilities --------------------------- #
@dataclass
class Timer:
    time: float = 0.0

    def tick(self, dt: float) -> None:
        self.time = max(0.0, self.time - dt)

    def set(self, t: float) -> None:
        self.time = t

    def ready(self) -> bool:
        return self.time <= 0.0

# --------------------------- Sprites --------------------------- #
class Star(pygame.sprite.Sprite):
    def __init__(self):
        super().__init__()
        self.x = random.uniform(0, WIDTH)
        self.y = random.uniform(0, HEIGHT)
        self.speed = random.uniform(20, 120)
        self.size = random.randint(1, 2)

    def update(self, dt: float):
        self.y += self.speed * dt
        if self.y > HEIGHT:
            self.y = -2
            self.x = random.uniform(0, WIDTH)
            self.speed = random.uniform(40, 120)

    def draw(self, surf: pygame.Surface):
        pygame.draw.rect(surf, WHITE, pygame.Rect(int(self.x), int(self.y), self.size, self.size))


class Player(pygame.sprite.Sprite):
    def __init__(self, x: int, y: int):
        super().__init__()
        self.image = pygame.Surface((32, 24), pygame.SRCALPHA)
        self.rect = self.image.get_rect(center=(x, y))
        self.cooldown = Timer(0.0)
        self.alive = True
        self._draw()

    def _draw(self):
        surf = self.image
        surf.fill((0, 0, 0, 0))
        w, h = surf.get_size()
        # Draw a simple player ship (triangle + wings)
        nose = (w//2, 2)
        left = (4, h-2)
        right = (w-4, h-2)
        pygame.draw.polygon(surf, CYAN, [left, nose, right])
        pygame.draw.polygon(surf, PURPLE, [(w//2-10, h-6), (w//2, h-14), (w//2+10, h-6)])
        pygame.draw.rect(surf, WHITE, pygame.Rect(w//2-2, h-12, 4, 8))

    def update(self, dt: float, keys, bounds: pygame.Rect):
        if not self.alive:
            return
        vx = 0
        if keys[pygame.K_LEFT] or keys[pygame.K_a]:
            vx -= PLAYER_SPEED
        if keys[pygame.K_RIGHT] or keys[pygame.K_d]:
            vx += PLAYER_SPEED
        self.rect.x += int(vx * dt)
        self.rect.clamp_ip(bounds)
        self.cooldown.tick(dt)

    def can_shoot(self) -> bool:
        return self.cooldown.ready() and self.alive

    def shoot(self) -> 'Bullet':
        self.cooldown.set(PLAYER_COOLDOWN)
        return Bullet(self.rect.centerx, self.rect.top, PLAYER_BULLET_SPEED, owner='player')


class Bullet(pygame.sprite.Sprite):
    def __init__(self, x: int, y: int, vy: float, owner: str):
        super().__init__()
        self.image = pygame.Surface((3, 10), pygame.SRCALPHA)
        color = YELLOW if owner == 'player' else RED
        pygame.draw.rect(self.image, color, pygame.Rect(0, 0, 3, 10))
        self.rect = self.image.get_rect(center=(x, y))
        self.vy = vy
        self.owner = owner

    def update(self, dt: float):
        self.rect.y += int(self.vy * dt)
        if self.rect.bottom < -12 or self.rect.top > HEIGHT + 12:
            self.kill()


class Enemy(pygame.sprite.Sprite):
    FORM_COLORS = [GREEN, YELLOW, CYAN]

    def __init__(self, grid_x: int, grid_y: int, origin: tuple[int, int], level: int):
        super().__init__()
        self.grid_x = grid_x
        self.grid_y = grid_y
        self.origin = origin  # formation anchor
        self.level = level
        self.in_formation = True
        self.state_time = 0.0
        self.image = pygame.Surface((26, 20), pygame.SRCALPHA)
        self.rect = self.image.get_rect()
        self.color = Enemy.FORM_COLORS[(grid_y) % len(Enemy.FORM_COLORS)]
        self._draw_ship()
        self.offset_x = (self.grid_x - 5) * 36
        self.offset_y = (self.grid_y) * 32
        self.rect.center = (self.origin[0] + self.offset_x, self.origin[1] + self.offset_y)
        self.h_dir = 1
        self.next_shot = random.uniform(2.5, 5.0)
        self.diving = False
        self.base_x = float(self.rect.centerx)
        self.base_y = float(self.rect.centery)
        self.dive_angle = 0.0

    def _draw_ship(self):
        surf = self.image
        surf.fill((0, 0, 0, 0))
        w, h = surf.get_size()
        body = pygame.Rect(3, 6, w-6, h-10)
        pygame.draw.rect(surf, self.color, body, border_radius=6)
        pygame.draw.rect(surf, WHITE, pygame.Rect(w//2-2, 2, 4, 8))
        pygame.draw.rect(surf, self.color, pygame.Rect(5, h-8, w-10, 6), border_radius=3)

    def update(self, dt: float, game: 'Game'):
        self.state_time += dt
        if self.in_formation:
            # Horizontal drift for the formation feel
            self.offset_x += game.form_dir * ENEMY_FORMATION_SPEED * dt
            self.rect.centerx = int(self.origin[0] + self.offset_x)
            self.rect.centery = int(self.origin[1] + self.offset_y + 4 * math.sin(self.state_time * 2.0))
            self.next_shot -= dt
            if self.next_shot <= 0:
                self.next_shot = random.uniform(2.5, 5.5) / max(0.6, (1 + 0.08 * game.level))
                if random.random() < 0.25 + min(0.35, 0.04 * game.level):
                    game.spawn_enemy_bullet(self.rect.centerx, self.rect.bottom)
        else:
            # Diving behavior: zig-zag downward, slightly tracking player x
            self.dive_angle += ENEMY_ZIGZAG_FREQ * dt
            track = game.player.rect.centerx if game.player.alive else WIDTH/2
            self.base_x += (track - self.base_x) * 0.8 * dt
            x = self.base_x + math.sin(self.dive_angle) * ENEMY_ZIGZAG_AMP
            y = self.base_y + ENEMY_DIVE_SPEED * self.state_time
            self.rect.center = (int(x), int(y))
            # Occasional shots while diving
            if random.random() < (0.22 * dt):
                game.spawn_enemy_bullet(self.rect.centerx, self.rect.bottom)
            # Remove if off-screen
            if self.rect.top > HEIGHT + 40:
                self.kill()

    def start_dive(self):
        self.in_formation = False
        self.diving = True
        self.state_time = 0.0
        self.base_x = float(self.rect.centerx)
        self.base_y = float(self.rect.centery)


class Particle(pygame.sprite.Sprite):
    def __init__(self, x: int, y: int, color: tuple[int, int, int]):
        super().__init__()
        self.image = pygame.Surface((3, 3), pygame.SRCALPHA)
        pygame.draw.rect(self.image, color, pygame.Rect(0, 0, 3, 3))
        self.rect = self.image.get_rect(center=(x, y))
        ang = random.uniform(0, math.tau)
        spd = random.uniform(80, 220)
        self.vx = math.cos(ang) * spd
        self.vy = math.sin(ang) * spd
        self.life = random.uniform(0.3, 0.7)

    def update(self, dt: float):
        self.life -= dt
        if self.life <= 0:
            self.kill()
            return
        self.rect.x += int(self.vx * dt)
        self.rect.y += int(self.vy * dt)


# --------------------------- Game --------------------------- #
class Game:
    def __init__(self):
        pygame.init()
        pygame.display.set_caption("Space Swarm — Galaga-style")
        self.screen = pygame.display.set_mode((WIDTH, HEIGHT))
        self.clock = pygame.time.Clock()
        self.font_big = pygame.font.Font(None, 54)
        self.font = pygame.font.Font(None, 28)
        self.bounds = pygame.Rect(0, 0, WIDTH, HEIGHT)

        # Groups
        self.all_sprites = pygame.sprite.Group()
        self.player_group = pygame.sprite.GroupSingle()
        self.enemy_group = pygame.sprite.Group()
        self.enemy_bullets = pygame.sprite.Group()
        self.player_bullets = pygame.sprite.Group()
        self.particles = pygame.sprite.Group()
        self.stars = [Star() for _ in range(STAR_COUNT)]

        # State
        self.level = 1
        self.score = 0
        self.lives = 3
        self.form_dir = 1
        self.form_time = 0.0
        self.paused = False
        self.game_over = False
        self.dive_timer = Timer(2.5)

        self.player = Player(WIDTH // 2, HEIGHT - 48)
        self.player_group.add(self.player)
        self.all_sprites.add(self.player)

        self.spawn_wave(self.level)

    # --------------------- Spawning helpers --------------------- #
    def spawn_enemy_bullet(self, x: int, y: int):
        b = Bullet(x, y, ENEMY_BULLET_SPEED, owner='enemy')
        self.enemy_bullets.add(b)
        self.all_sprites.add(b)

    def spawn_explosion(self, x: int, y: int, color=(255, 200, 80)):
        for _ in range(14):
            p = Particle(x, y, color)
            self.particles.add(p)
            self.all_sprites.add(p)

    def spawn_wave(self, level: int):
        self.enemy_group.empty()
        cols = 10
        rows = min(6, 3 + level)  # scale rows with level
        origin = (WIDTH // 2, 120)
        for gy in range(rows):
            for gx in range(cols):
                e = Enemy(gx, gy, origin, level)
                self.enemy_group.add(e)
                self.all_sprites.add(e)
        # Formation drift flips every few seconds
        self.form_time = 0.0
        self.form_dir = 1
        # Stagger first dive a bit
        self.dive_timer.set(max(1.5, 3.5 - level * 0.2))

    # --------------------- Game loop helpers --------------------- #
    def handle_events(self) -> bool:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return False
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    return False
                if event.key == pygame.K_p:
                    if not self.game_over:
                        self.paused = not self.paused
                if event.key == pygame.K_r and self.game_over:
                    self.reset()
        return True

    def reset(self):
        self.level = 1
        self.score = 0
        self.lives = 3
        self.game_over = False
        self.paused = False
        self.all_sprites.empty()
        self.enemy_group.empty()
        self.enemy_bullets.empty()
        self.player_bullets.empty()
        self.particles.empty()
        self.player = Player(WIDTH // 2, HEIGHT - 48)
        self.player_group.empty()
        self.player_group.add(self.player)
        self.all_sprites.add(self.player)
        self.stars = [Star() for _ in range(STAR_COUNT)]
        self.spawn_wave(self.level)

    def player_fire(self):
        if self.player.can_shoot():
            bullet = self.player.shoot()
            self.player_bullets.add(bullet)
            self.all_sprites.add(bullet)

    def choose_diver(self):
        # Prefer top rows so stragglers don't all leave formation
        candidates = [e for e in self.enemy_group if e.in_formation]
        if not candidates:
            return None
        candidates.sort(key=lambda e: (e.grid_y, abs(e.rect.centerx - WIDTH//2)))
        # Weight toward edges for nice arcs
        k = min(len(candidates)-1, random.randint(0, 5))
        return random.choice(candidates[: max(4, k+1)])

    def update(self, dt: float):
        if self.paused or self.game_over:
            return

        # Stars
        for s in self.stars:
            s.update(dt)

        keys = pygame.key.get_pressed()
        self.player.update(dt, keys, self.bounds)
        if keys[pygame.K_SPACE]:
            self.player_fire()

        # Formation drift
        self.form_time += dt
        if self.form_time >= 2.8:
            self.form_time = 0.0
            self.form_dir *= -1

        # Enemy updates
        for e in list(self.enemy_group):
            e.update(dt, self)

        # Trigger a diver every so often
        self.dive_timer.tick(dt)
        if self.dive_timer.ready():
            diver = self.choose_diver()
            if diver:
                diver.start_dive()
            # Next dive sooner on higher levels
            base = max(0.8, 2.4 - self.level * 0.15)
            self.dive_timer.set(base + random.uniform(0.0, 0.7))

        # Bullets & particles
        self.enemy_bullets.update(dt)
        self.player_bullets.update(dt)
        self.particles.update(dt)

        # Collisions: player bullets vs enemies
        hits = pygame.sprite.groupcollide(self.enemy_group, self.player_bullets, dokilla=True, dokillb=True)
        for enemy in hits.keys():
            self.spawn_explosion(enemy.rect.centerx, enemy.rect.centery, color=(255, 200, 60))
            self.score += 150 if enemy.diving else 100

        # Collisions: enemy bullets vs player
        if self.player.alive:
            if pygame.sprite.spritecollideany(self.player, self.enemy_bullets) or \
               pygame.sprite.spritecollideany(self.player, self.enemy_group):
                self.on_player_hit()

        # Wave cleared?
        if len(self.enemy_group) == 0 and not self.game_over:
            self.level += 1
            self.spawn_wave(self.level)

    def on_player_hit(self):
        # Remove bullets that hit
        for b in pygame.sprite.spritecollide(self.player, self.enemy_bullets, dokill=True):
            pass
        self.spawn_explosion(self.player.rect.centerx, self.player.rect.centery, color=(120, 220, 255))
        self.player.alive = False
        self.lives -= 1
        if self.lives < 0:
            self.game_over = True
        else:
            # brief respawn delay & i-frames
            pygame.time.set_timer(pygame.USEREVENT + 1, 900, loops=1)

    def handle_timers(self, event):
        if event.type == pygame.USEREVENT + 1:
            # Respawn
            self.player = Player(WIDTH // 2, HEIGHT - 48)
            self.player_group.empty()
            self.player_group.add(self.player)
            self.all_sprites.add(self.player)

    # --------------------- Rendering --------------------- #
    def draw_hud(self, surf: pygame.Surface):
        score_s = self.font.render(f"SCORE {self.score:06d}", True, WHITE)
        lives_s = self.font.render(f"LIVES {max(0, self.lives)}", True, WHITE)
        level_s = self.font.render(f"WAVE {self.level}", True, WHITE)
        surf.blit(score_s, (10, 8))
        surf.blit(level_s, (WIDTH//2 - level_s.get_width()//2, 8))
        surf.blit(lives_s, (WIDTH - lives_s.get_width() - 10, 8))

    def draw(self):
        self.screen.fill(BLACK)
        # Starfield
        for s in self.stars:
            s.draw(self.screen)

        # Sprites
        for g in (self.enemy_group, self.player_bullets, self.enemy_bullets, self.particles, self.player_group):
            g.draw(self.screen)

        # HUD
        self.draw_hud(self.screen)

        if self.paused and not self.game_over:
            t = self.font_big.render("PAUSED", True, WHITE)
            self.screen.blit(t, (WIDTH//2 - t.get_width()//2, HEIGHT//2 - 20))
        if self.game_over:
            over = self.font_big.render("GAME OVER", True, WHITE)
            hint = self.font.render("Press R to restart", True, WHITE)
            self.screen.blit(over, (WIDTH//2 - over.get_width()//2, HEIGHT//2 - 30))
            self.screen.blit(hint, (WIDTH//2 - hint.get_width()//2, HEIGHT//2 + 18))

        pygame.display.flip()

    # --------------------- Main loop --------------------- #
    def run(self):
        running = True
        while running:
            dt = self.clock.tick(FPS) / 1000.0
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        running = False
                    elif event.key == pygame.K_p and not self.game_over:
                        self.paused = not self.paused
                    elif event.key == pygame.K_r and self.game_over:
                        self.reset()
                else:
                    self.handle_timers(event)

            self.update(dt)
            self.draw()
        pygame.quit()


if __name__ == "__main__":
    Game().run()
