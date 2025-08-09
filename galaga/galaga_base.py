"""
Galaga-style Arcade Shooter in Python (single-file, no assets)

Requirements:
  pip install pygame

Run:
  python galaga.py

Controls:
  Arrow keys or A/D to move, Space to shoot, P to pause, Esc to quit.

Notes:
- This is a lightweight homage to Galaga: player ship, enemy formation, dive attacks,
  scoring, lives, waves, and simple particle effects. All graphics are drawn with
  pygame primitives (no image/sound assets).
- Designed to fit in one file and be beginner-friendly to tweak.
"""
import math
import random
import sys
from dataclasses import dataclass

import pygame

# --------------------------- Config ---------------------------------
WIDTH, HEIGHT = 520, 700
FPS = 60
MARGIN = 20

PLAYER_SPEED = 5.0
PLAYER_COOLDOWN = 280  # ms between shots
PLAYER_LIVES = 3
PLAYER_HIT_INVULN = 1200  # ms of invulnerability post-hit

BULLET_SPEED = -9
ENEMY_BULLET_SPEED = 5
ENEMY_FORMATION_SPEED = 1.2
ENEMY_STEP_DOWN = 12
DIVE_COOLDOWN = (1700, 3600)  # ms between dive launches per enemy
DIVE_SPEED = 3.4

WAVE_COLS = 10
WAVE_ROWS = 5
WAVE_X_SPACING = 40
WAVE_Y_SPACING = 34

STAR_COUNT = 80

# Colors
BLACK = (10, 10, 18)
WHITE = (235, 235, 235)
GRAY = (100, 110, 120)
YELLOW = (250, 215, 80)
CYAN = (100, 220, 255)
MAGENTA = (255, 120, 200)
RED = (240, 80, 90)
GREEN = (120, 230, 120)
ORANGE = (255, 170, 80)

# --------------------------- Helpers --------------------------------
@dataclass
class Particle:
    x: float
    y: float
    vx: float
    vy: float
    life: int
    color: tuple

    def update(self):
        self.x += self.vx
        self.y += self.vy
        self.life -= 1

    def draw(self, surf):
        if self.life > 0:
            pygame.draw.circle(surf, self.color, (int(self.x), int(self.y)), 2)

class Starfield:
    def __init__(self, w, h, n):
        self.w, self.h = w, h
        self.stars = [(random.randrange(w), random.randrange(h), random.randint(1, 3)) for _ in range(n)]

    def update(self):
        new = []
        for x, y, s in self.stars:
            y = y + s
            if y >= self.h:
                y = 0
                x = random.randrange(self.w)
            new.append((x, y, s))
        self.stars = new

    def draw(self, surf):
        for x, y, s in self.stars:
            c = (min(255, 140 + s * 30),) * 3
            surf.fill(c, (x, y, s, s))

# --------------------------- Game Objects ----------------------------
class Player:
    def __init__(self, x, y):
        self.rect = pygame.Rect(x - 16, y - 12, 32, 24)
        self.cooldown = 0
        self.lives = PLAYER_LIVES
        self.invuln_until = 0
        self.flash = False

    def update(self, dt, keys):
        dx = 0
        if keys[pygame.K_LEFT] or keys[pygame.K_a]:
            dx -= PLAYER_SPEED
        if keys[pygame.K_RIGHT] or keys[pygame.K_d]:
            dx += PLAYER_SPEED
        self.rect.x += dx
        self.rect.x = max(MARGIN, min(WIDTH - MARGIN - self.rect.width, self.rect.x))
        if self.cooldown > 0:
            self.cooldown -= dt
        self.flash = (pygame.time.get_ticks() // 120) % 2 == 0

    def can_shoot(self):
        return self.cooldown <= 0

    def shoot(self):
        self.cooldown = PLAYER_COOLDOWN
        tip = (self.rect.centerx, self.rect.top - 6)
        return Bullet(tip[0], tip[1], BULLET_SPEED, 'player')

    def draw(self, surf):
        # Simple ship: triangle + wings
        cx, cy = self.rect.center
        points = [(cx, self.rect.top - 6), (self.rect.left, self.rect.bottom), (self.rect.right, self.rect.bottom)]
        color = CYAN if self.is_vulnerable() or self.flash else GRAY
        pygame.draw.polygon(surf, color, points)
        # cockpit
        pygame.draw.circle(surf, WHITE, (cx, cy - 2), 3)

    def hit(self):
        now = pygame.time.get_ticks()
        if now < self.invuln_until:
            return False
        self.lives -= 1
        self.invuln_until = now + PLAYER_HIT_INVULN
        return True

    def is_dead(self):
        return self.lives <= 0

    def is_vulnerable(self):
        return pygame.time.get_ticks() >= self.invuln_until

class Bullet:
    def __init__(self, x, y, vy, owner):
        self.rect = pygame.Rect(x - 2, y - 8, 4, 12)
        self.vy = vy
        self.owner = owner  # 'player' or 'enemy'

    def update(self):
        self.rect.y += self.vy

    def offscreen(self):
        return self.rect.bottom < 0 or self.rect.top > HEIGHT

    def draw(self, surf):
        color = YELLOW if self.owner == 'player' else ORANGE
        pygame.draw.rect(surf, color, self.rect)

class Enemy:
    SIZE = 24

    def __init__(self, gx, gy, kind='grunt'):
        self.kind = kind
        self.grid_x = gx
        self.grid_y = gy
        self.x = 0
        self.y = 0
        self.mode = 'formation'  # 'formation' or 'dive' or 'return'
        self.path_t = 0.0
        self.alive = True
        base = 10 if kind == 'grunt' else 20
        self.score = base + (gy * 2)
        self.last_dive = random.randint(*DIVE_COOLDOWN)
        self.dive_delay = random.randint(*DIVE_COOLDOWN)

    def formation_pos(self, origin):
        ox, oy = origin
        return (
            ox + self.grid_x * WAVE_X_SPACING,
            oy + self.grid_y * WAVE_Y_SPACING,
        )

    def rect(self):
        return pygame.Rect(int(self.x - self.SIZE/2), int(self.y - self.SIZE/2), self.SIZE, self.SIZE)

    def update(self, dt, origin, player_pos):
        if not self.alive:
            return
        if self.mode == 'formation':
            self.x, self.y = self.formation_pos(origin)
            self.last_dive += dt
            if self.last_dive >= self.dive_delay and random.random() < 0.01:
                self.mode = 'dive'
                self.path_t = 0.0
        elif self.mode == 'dive':
            self.path_t += dt / 1000.0
            px, py = player_pos
            # Spiral-ish dive path toward player
            radius = 80
            self.x += math.cos(self.path_t * 4) * 2
            self.y += DIVE_SPEED * 1.8
            # Slight homing
            self.x += (px - self.x) * 0.01
            if self.y > HEIGHT + 40:
                self.mode = 'return'
        elif self.mode == 'return':
            fx, fy = self.formation_pos(origin)
            dx, dy = fx - self.x, fy - self.y
            dist = math.hypot(dx, dy)
            if dist < 4:
                self.mode = 'formation'
                self.last_dive = 0
                self.dive_delay = random.randint(*DIVE_COOLDOWN)
            else:
                self.x += dx * 0.03
                self.y += dy * 0.03

    def draw(self, surf):
        if not self.alive:
            return
        r = self.rect()
        color = MAGENTA if self.kind == 'elite' else GREEN
        if self.mode == 'dive':
            color = RED
        pygame.draw.rect(surf, color, r, border_radius=6)
        # "eyes"
        pygame.draw.circle(surf, BLACK, (r.centerx - 5, r.centery - 2), 3)
        pygame.draw.circle(surf, BLACK, (r.centerx + 5, r.centery - 2), 3)

    def try_fire(self):
        if self.mode != 'formation' or random.random() > 0.006:
            return None
        r = self.rect()
        return Bullet(r.centerx, r.bottom + 4, ENEMY_BULLET_SPEED, 'enemy')

# --------------------------- Game State ------------------------------
class Game:
    def __init__(self):
        pygame.init()
        pygame.display.set_caption("Galaga (Python)")
        self.screen = pygame.display.set_mode((WIDTH, HEIGHT))
        self.clock = pygame.time.Clock()
        self.font = pygame.font.SysFont("consolas", 20)
        self.big = pygame.font.SysFont("consolas", 40, bold=True)
        self.formation_origin = [MARGIN + 40, 90]
        self.formation_bounds = [MARGIN + 20, WIDTH - MARGIN - 20]
        self.reset()

    def reset(self):
        self.player = Player(WIDTH // 2, HEIGHT - 60)
        self.bullets = []
        self.enemy_bullets = []
        self.particles = []
        self.starfield = Starfield(WIDTH, HEIGHT, STAR_COUNT)
        self.score = 0
        self.wave = 1
        self.spawn_wave(self.wave)
        self.running = True
        self.paused = False
        self.game_over = False
        self.formation_dir = 1
        self.formation_origin = [MARGIN + 40, 90]
        self.formation_bounds = [MARGIN + 20, WIDTH - MARGIN - 20]

    def spawn_wave(self, n):
        self.enemies = []
        kinds = ['grunt', 'grunt', 'grunt', 'grunt', 'elite']
        for gy in range(WAVE_ROWS):
            for gx in range(WAVE_COLS):
                kind = kinds[gy % len(kinds)]
                e = Enemy(gx, gy, kind)
                fx = self.formation_origin[0] + gx * WAVE_X_SPACING
                fy = self.formation_origin[1] + gy * WAVE_Y_SPACING
                e.x, e.y = fx, fy
                self.enemies.append(e)

    def handle_events(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit(); sys.exit(0)
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    pygame.quit(); sys.exit(0)
                if event.key == pygame.K_p:
                    self.paused = not self.paused
                if event.key == pygame.K_SPACE and not self.game_over and not self.paused:
                    if self.player.can_shoot():
                        self.bullets.append(self.player.shoot())
                if event.key == pygame.K_RETURN and self.game_over:
                    self.reset()

    def update(self, dt):
        if self.paused or self.game_over:
            return
        keys = pygame.key.get_pressed()
        self.player.update(dt, keys)

        # Formation horizontal sweep
        leftmost = min(e.formation_pos(self.formation_origin)[0] for e in self.enemies if e.alive)
        rightmost = max(e.formation_pos(self.formation_origin)[0] for e in self.enemies if e.alive)
        self.formation_origin[0] += self.formation_dir * ENEMY_FORMATION_SPEED
        if rightmost >= self.formation_bounds[1] or leftmost <= self.formation_bounds[0]:
            self.formation_dir *= -1
            self.formation_origin[1] += ENEMY_STEP_DOWN

        # Enemies
        alive_any = False
        player_pos = (self.player.rect.centerx, self.player.rect.centery)
        for e in self.enemies:
            if not e.alive:
                continue
            alive_any = True
            e.update(dt, self.formation_origin, player_pos)
            bullet = e.try_fire()
            if bullet:
                self.enemy_bullets.append(bullet)

        if not alive_any:
            self.wave += 1
            self.formation_origin = [MARGIN + 40, 90]
            self.spawn_wave(self.wave)

        # Bullets
        for b in self.bullets:
            b.update()
        for b in self.enemy_bullets:
            b.update()
        self.bullets = [b for b in self.bullets if not b.offscreen()]
        self.enemy_bullets = [b for b in self.enemy_bullets if not b.offscreen()]

        # Collisions: player bullets vs enemies
        for b in list(self.bullets):
            if b.owner != 'player':
                continue
            for e in self.enemies:
                if e.alive and e.rect().colliderect(b.rect):
                    e.alive = False
                    self.score += 50 if e.kind == 'elite' else 30
                    self.spawn_explosion(e.x, e.y, MAGENTA if e.kind == 'elite' else GREEN)
                    if b in self.bullets:
                        self.bullets.remove(b)
                    break

        # Collisions: enemy bullets vs player
        if self.player.is_vulnerable():
            for b in list(self.enemy_bullets):
                if b.owner == 'enemy' and self.player.rect.colliderect(b.rect):
                    if self.player.hit():
                        self.spawn_explosion(self.player.rect.centerx, self.player.rect.centery, CYAN)
                    if b in self.enemy_bullets:
                        self.enemy_bullets.remove(b)

        # Collisions: diving enemy vs player
        if self.player.is_vulnerable():
            for e in self.enemies:
                if e.alive and e.mode in ('dive',) and e.rect().colliderect(self.player.rect):
                    if self.player.hit():
                        self.spawn_explosion(self.player.rect.centerx, self.player.rect.centery, CYAN)
                    e.alive = False
                    self.spawn_explosion(e.x, e.y, RED)

        # Particles & stars
        self.starfield.update()
        for p in list(self.particles):
            p.update()
            if p.life <= 0:
                self.particles.remove(p)

        if self.player.is_dead():
            self.game_over = True

    def spawn_explosion(self, x, y, base_color):
        for _ in range(18):
            ang = random.random() * math.tau
            spd = random.uniform(1.5, 4.0)
            vx, vy = math.cos(ang) * spd, math.sin(ang) * spd
            life = random.randint(18, 30)
            col = tuple(min(255, int(c * random.uniform(0.8, 1.1))) for c in base_color)
            self.particles.append(Particle(x, y, vx, vy, life, col))

    def draw_hud(self):
        s = self.font.render(f"Score: {self.score}", True, WHITE)
        w = self.font.render(f"Wave: {self.wave}", True, WHITE)
        l = self.font.render(f"Lives: {self.player.lives}", True, WHITE)
        self.screen.blit(s, (MARGIN, 8))
        self.screen.blit(w, (WIDTH//2 - w.get_width()//2, 8))
        self.screen.blit(l, (WIDTH - l.get_width() - MARGIN, 8))

    def draw(self):
        self.screen.fill(BLACK)
        self.starfield.draw(self.screen)
        # Entities
        for e in self.enemies:
            e.draw(self.screen)
        for b in self.bullets:
            b.draw(self.screen)
        for b in self.enemy_bullets:
            b.draw(self.screen)
        self.player.draw(self.screen)
        for p in self.particles:
            p.draw(self.screen)
        self.draw_hud()

        if self.paused and not self.game_over:
            txt = self.big.render("PAUSED", True, WHITE)
            self.screen.blit(txt, (WIDTH//2 - txt.get_width()//2, HEIGHT//2 - txt.get_height()//2))

        if self.game_over:
            over = self.big.render("GAME OVER", True, WHITE)
            tip = self.font.render("Press Enter to restart", True, GRAY)
            self.screen.blit(over, (WIDTH//2 - over.get_width()//2, HEIGHT//2 - 40))
            self.screen.blit(tip, (WIDTH//2 - tip.get_width()//2, HEIGHT//2 + 6))

        pygame.display.flip()

    def start_screen(self):
        blink = 0
        while True:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    pygame.quit(); sys.exit(0)
                elif event.type == pygame.KEYDOWN:
                    if event.key in (pygame.K_RETURN, pygame.K_SPACE):
                        return
            self.screen.fill(BLACK)
            self.starfield.update()
            self.starfield.draw(self.screen)
            title = self.big.render("GALAGA (Python)", True, WHITE)
            tip = self.font.render("Arrow keys / A,D to move  •  Space to shoot  •  P to pause", True, GRAY)
            press = self.font.render("Press Enter or Space to start", True, YELLOW if (blink//30)%2==0 else GRAY)
            self.screen.blit(title, (WIDTH//2 - title.get_width()//2, HEIGHT//2 - 80))
            self.screen.blit(tip, (WIDTH//2 - tip.get_width()//2, HEIGHT//2 - 20))
            self.screen.blit(press, (WIDTH//2 - press.get_width()//2, HEIGHT//2 + 20))
            pygame.display.flip()
            blink = (blink + 1) % 120
            self.clock.tick(FPS)

    def run(self):
        self.start_screen()
        while self.running:
            dt = self.clock.tick(FPS)
            self.handle_events()
            self.update(dt)
            self.draw()


if __name__ == "__main__":
    Game().run()
