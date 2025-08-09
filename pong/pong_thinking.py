"""
Pong — Python (Pygame)

How to run:
1) Install Python 3.9+.
2) Install pygame:  pip install pygame
3) Save this file as pong.py and run:  python pong.py

Controls:
- Left Paddle:  W (up), S (down)
- Right Paddle (2P mode):  Up/Down arrows
- Toggle 1P/2P:  Tab
- Difficulty (1P mode): Keys 1=Easy, 2=Normal, 3=Hard
- Serve ball / Start round: Space
- Pause: P
- Restart scores: R
- Quit: Esc

Notes:
- The ball speeds up slightly on every paddle hit.
- In 1P mode the right paddle is AI; difficulty adjusts its tracking speed.
"""

import math
import random
import sys
from dataclasses import dataclass

import pygame

# --- Config ---
WIDTH, HEIGHT = 900, 600
FPS = 60
BG_COLOR = (16, 18, 23)
FG_COLOR = (235, 235, 235)
ACCENT = (100, 160, 255)
SHADOW = (0, 0, 0)

PADDLE_W, PADDLE_H = 12, 110
BALL_SIZE = 14

PADDLE_SPEED = 460.0  # px/s
AI_BASE_SPEED = 400.0 # px/s at Normal
BALL_START_SPEED = 430.0
BALL_MAX_SPEED = 1000.0
BALL_SPEEDUP = 1.035  # per paddle hit
MAX_BOUNCE_DEG = 50  # max deflection from horizontal
WIN_SCORE = 10
SERVE_DELAY = 450  # ms after reset before serve allowed

CENTER_LINE_SEG = 24
CENTER_LINE_GAP = 16

@dataclass
class Score:
    left: int = 0
    right: int = 0

class Paddle:
    def __init__(self, x: int):
        self.rect = pygame.Rect(x, HEIGHT // 2 - PADDLE_H // 2, PADDLE_W, PADDLE_H)
        self._y = float(self.rect.y)
        self.speed = PADDLE_SPEED

    def move(self, dy: float):
        self._y += dy
        self._y = max(0, min(self._y, HEIGHT - self.rect.height))
        self.rect.y = int(self._y)

    def center(self):
        return self.rect.centery

class Ball:
    def __init__(self):
        self.rect = pygame.Rect(WIDTH // 2 - BALL_SIZE // 2, HEIGHT // 2 - BALL_SIZE // 2, BALL_SIZE, BALL_SIZE)
        self.pos = pygame.Vector2(self.rect.centerx, self.rect.centery)
        self.vel = pygame.Vector2(0, 0)
        self.speed = BALL_START_SPEED
        self.last_paddle_hit = None  # 'L' or 'R'

    def reset(self, direction: int):
        # direction: +1 moves right, -1 moves left
        self.pos.update(WIDTH / 2, HEIGHT / 2)
        self.rect.center = (int(self.pos.x), int(self.pos.y))
        self.speed = BALL_START_SPEED
        # Choose a random angle not too vertical
        angle = math.radians(random.uniform(-25, 25))
        vx = math.cos(angle) * self.speed * direction
        vy = math.sin(angle) * self.speed
        self.vel.update(vx, vy)
        self.last_paddle_hit = None

    def update(self, dt: float):
        self.pos += self.vel * dt
        self.rect.center = (int(self.pos.x), int(self.pos.y))
        # Wall collisions (top/bottom)
        if self.rect.top <= 0:
            self.rect.top = 0
            self.pos.y = self.rect.centery
            self.vel.y *= -1
        elif self.rect.bottom >= HEIGHT:
            self.rect.bottom = HEIGHT
            self.pos.y = self.rect.centery
            self.vel.y *= -1

    def collide_with_paddle(self, paddle: Paddle, is_left: bool):
        if not self.rect.colliderect(paddle.rect):
            return False
        # Determine deflection based on where it hit the paddle
        offset = (self.rect.centery - paddle.rect.centery) / (paddle.rect.height / 2)
        offset = max(-1.0, min(1.0, offset))
        angle = math.radians(offset * MAX_BOUNCE_DEG)
        # Ensure horizontal direction away from the paddle
        direction = 1 if is_left else -1
        self.speed = min(self.speed * BALL_SPEEDUP, BALL_MAX_SPEED)
        new_vx = math.cos(angle) * self.speed * direction
        new_vy = math.sin(angle) * self.speed
        self.vel.update(new_vx, new_vy)
        # Nudge the ball outside the paddle to avoid sticking
        if is_left:
            self.rect.left = paddle.rect.right
        else:
            self.rect.right = paddle.rect.left
        self.pos.update(self.rect.centerx, self.rect.centery)
        self.last_paddle_hit = 'L' if is_left else 'R'
        return True

# --- Helpers ---
def draw_center_line(surface):
    y = 0
    while y < HEIGHT:
        seg = pygame.Rect(WIDTH // 2 - 2, y, 4, CENTER_LINE_SEG)
        pygame.draw.rect(surface, (70, 72, 80), seg)
        y += CENTER_LINE_SEG + CENTER_LINE_GAP


def draw_text(surface, text, size, x, y, color=FG_COLOR, center=True):
    font = pygame.font.SysFont("consolas", size, bold=True)
    surf = font.render(text, True, color)
    rect = surf.get_rect()
    if center:
        rect.center = (x, y)
    else:
        rect.topleft = (x, y)
    surface.blit(surf, rect)


class AIController:
    def __init__(self):
        self.skill = 1.0  # 0.6=Easy, 0.85=Normal, 1.0=Hard

    def set_difficulty(self, level: int):
        if level == 1:
            self.skill = 0.65
        elif level == 2:
            self.skill = 0.85
        else:
            self.skill = 1.0

    def update(self, paddle: Paddle, ball: Ball, dt: float):
        # Only track hard when ball is moving towards AI; otherwise drift toward center
        moving_towards_ai = ball.vel.x > 0
        target_y = ball.rect.centery if moving_towards_ai else HEIGHT // 2
        # Predict a bit ahead to make it feel smarter
        lead = min(0.18, 0.06 + (ball.speed / BALL_MAX_SPEED) * 0.12)
        predicted = target_y + ball.vel.y * lead
        # Move toward predicted location with clamped speed
        max_speed = AI_BASE_SPEED * self.skill
        dy = predicted - paddle.center()
        step = max(-max_speed * dt, min(max_speed * dt, dy))
        paddle.move(step)


def main():
    pygame.init()
    pygame.display.set_caption("Pong — Python (Pygame)")
    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    clock = pygame.time.Clock()

    left = Paddle(40)
    right = Paddle(WIDTH - 40 - PADDLE_W)
    ball = Ball()

    scores = Score()
    ai = AIController()
    two_player = False
    paused = False

    state = "serve"  # "serve" | "play" | "gameover"
    serve_dir = random.choice([-1, 1])
    ball.reset(serve_dir)
    last_score_time = pygame.time.get_ticks()

    # Pre-render instructions (lightweight)
    small_font = pygame.font.SysFont("consolas", 18)

    while True:
        dt = clock.tick(FPS) / 1000.0
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    pygame.quit()
                    sys.exit()
                if event.key == pygame.K_p:
                    paused = not paused
                if event.key == pygame.K_r:
                    scores = Score()
                    state = "serve"
                    serve_dir = random.choice([-1, 1])
                    ball.reset(serve_dir)
                    last_score_time = pygame.time.get_ticks()
                if event.key == pygame.K_SPACE:
                    if state == "serve":
                        state = "play"
                if event.key == pygame.K_TAB:
                    two_player = not two_player
                if event.key in (pygame.K_1, pygame.K_2, pygame.K_3):
                    level = {pygame.K_1: 1, pygame.K_2: 2, pygame.K_3: 3}[event.key]
                    ai.set_difficulty(level)

        # Input for paddles
        keys = pygame.key.get_pressed()
        if not paused and state != "gameover":
            # Left paddle (W/S)
            dy = 0.0
            if keys[pygame.K_w]:
                dy -= left.speed * dt
            if keys[pygame.K_s]:
                dy += left.speed * dt
            left.move(dy)

            # Right paddle: player or AI
            if two_player:
                dy2 = 0.0
                if keys[pygame.K_UP]:
                    dy2 -= right.speed * dt
                if keys[pygame.K_DOWN]:
                    dy2 += right.speed * dt
                right.move(dy2)
            else:
                ai.update(right, ball, dt)

        # Update ball
        if not paused and state == "play":
            ball.update(dt)
            # Paddle collisions
            if ball.vel.x < 0 and ball.rect.left <= left.rect.right:
                ball.collide_with_paddle(left, is_left=True)
            elif ball.vel.x > 0 and ball.rect.right >= right.rect.left:
                ball.collide_with_paddle(right, is_left=False)

            # Scoring
            if ball.rect.right < 0:
                scores.right += 1
                if scores.right >= WIN_SCORE:
                    state = "gameover"
                else:
                    state = "serve"
                serve_dir = 1
                ball.reset(serve_dir)
                last_score_time = pygame.time.get_ticks()
            elif ball.rect.left > WIDTH:
                scores.left += 1
                if scores.left >= WIN_SCORE:
                    state = "gameover"
                else:
                    state = "serve"
                serve_dir = -1
                ball.reset(serve_dir)
                last_score_time = pygame.time.get_ticks()

        # Auto-serve unlock after delay
        if state == "serve":
            if pygame.time.get_ticks() - last_score_time > SERVE_DELAY:
                # show "Press Space" prompt; actual state change on keypress
                pass

        # --- Drawing ---
        screen.fill(BG_COLOR)
        draw_center_line(screen)

        # Scoreboard
        draw_text(screen, str(scores.left), 64, WIDTH * 0.25, 60, FG_COLOR)
        draw_text(screen, str(scores.right), 64, WIDTH * 0.75, 60, FG_COLOR)

        # Paddles + Ball
        # Soft shadows for a little depth
        for r in (left.rect, right.rect, ball.rect):
            shadow = pygame.Rect(r.x + 3, r.y + 3, r.width, r.height)
            pygame.draw.rect(screen, SHADOW, shadow, border_radius=3)
        pygame.draw.rect(screen, FG_COLOR, left.rect, border_radius=4)
        pygame.draw.rect(screen, FG_COLOR, right.rect, border_radius=4)
        pygame.draw.rect(screen, ACCENT, ball.rect, border_radius=3)

        # Status banners
        if paused:
            draw_text(screen, "PAUSED", 36, WIDTH // 2, HEIGHT // 2 - 40, color=ACCENT)
            draw_text(screen, "Press P to resume", 22, WIDTH // 2, HEIGHT // 2 + 4, color=(200, 200, 200))
        elif state == "serve":
            draw_text(screen, "Press SPACE to serve", 28, WIDTH // 2, HEIGHT // 2 - 20, color=ACCENT)
            mode = "2P" if two_player else "1P vs AI"
            diff = "(AI: Easy)" if ai.skill <= 0.66 else ("(AI: Normal)" if ai.skill < 0.95 else "(AI: Hard)")
            info = f"Mode: {mode}   {diff}   [Tab to toggle, 1/2/3 to set difficulty]"
            label = small_font.render(info, True, (200, 200, 200))
            screen.blit(label, label.get_rect(center=(WIDTH // 2, HEIGHT // 2 + 16)))
        elif state == "gameover":
            winner = "Left" if scores.left > scores.right else "Right"
            draw_text(screen, f"{winner} Player Wins!", 36, WIDTH // 2, HEIGHT // 2 - 24, color=ACCENT)
            draw_text(screen, "Press R to restart", 22, WIDTH // 2, HEIGHT // 2 + 18, color=(200, 200, 200))

        # Footer controls
        footer = small_font.render("W/S & ↑/↓ to move • Space=Serve • P=Pause • R=Reset • Tab=1P/2P • Esc=Quit", True, (150, 150, 150))
        screen.blit(footer, footer.get_rect(center=(WIDTH // 2, HEIGHT - 20)))

        pygame.display.flip()


if __name__ == "__main__":
    main()
