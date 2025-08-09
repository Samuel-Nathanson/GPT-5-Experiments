# Pong (Python + Pygame)
# Controls:
# - Left paddle: W/S
# - Right paddle: Up/Down
# - 1 = toggle right-paddle AI, P = pause, R = restart, Esc = quit

import sys
import math
import random
import pygame

# --- Config ---
WIDTH, HEIGHT = 960, 540
PADDLE_W, PADDLE_H = 12, 100
BALL_SIZE = 16

PADDLE_SPEED = 520      # px/s
BALL_SPEED = 380        # starting speed
BALL_SPEED_INC = 1.05   # speedup per paddle hit
BALL_SPEED_MAX = 1100
WIN_SCORE = 10

BG = (12, 12, 12)
FG = (240, 240, 240)
NET = (60, 60, 60)


class Pong:
    def __init__(self):
        pygame.init()
        pygame.display.set_caption("Pong")
        self.screen = pygame.display.set_mode((WIDTH, HEIGHT))
        self.clock = pygame.time.Clock()
        self.font = pygame.font.Font(None, 64)
        self.small_font = pygame.font.Font(None, 28)

        # Entities
        self.left = pygame.Rect(30, HEIGHT // 2 - PADDLE_H // 2, PADDLE_W, PADDLE_H)
        self.right = pygame.Rect(WIDTH - 30 - PADDLE_W,
                                 HEIGHT // 2 - PADDLE_H // 2,
                                 PADDLE_W, PADDLE_H)
        self.ball = pygame.Rect(WIDTH // 2 - BALL_SIZE // 2,
                                HEIGHT // 2 - BALL_SIZE // 2,
                                BALL_SIZE, BALL_SIZE)

        # Float positions for smooth motion
        self.left_y = float(self.left.y)
        self.right_y = float(self.right.y)
        self.ball_pos = pygame.Vector2(self.ball.center)
        self.ball_vel = pygame.Vector2()

        self.score_l = 0
        self.score_r = 0
        self.paused = False
        self.ai_right = False
        self.serve_timer = 0.0
        self.winner = None

        self.reset(full=True)

    # ----- Game flow -----
    def reset(self, full=False, direction=None):
        """Reset paddles and ball; if full=True also reset scores."""
        self.left_y = HEIGHT / 2 - PADDLE_H / 2
        self.right_y = HEIGHT / 2 - PADDLE_H / 2
        self.left.y = round(self.left_y)
        self.right.y = round(self.right_y)

        self.ball.center = (WIDTH // 2, HEIGHT // 2)
        self.ball_pos.update(self.ball.center)

        # Serve direction: +1 = to the right, -1 = to the left
        dirx = random.choice([-1, 1]) if direction is None else direction
        angle = math.radians(random.uniform(-45, 45))  # shallow launch
        vx = math.cos(angle) * dirx
        vy = math.sin(angle)
        v = pygame.Vector2(vx, vy)
        self.ball_vel = v.normalize() * BALL_SPEED

        self.serve_timer = 1.0 if full else 0.6
        if full:
            self.score_l = self.score_r = 0
            self.winner = None

    # ----- Input & AI -----
    def handle_input(self, dt):
        keys = pygame.key.get_pressed()

        # Left paddle (human)
        if keys[pygame.K_w]:
            self.left_y -= PADDLE_SPEED * dt
        if keys[pygame.K_s]:
            self.left_y += PADDLE_SPEED * dt

        # Right paddle (human unless AI toggled)
        if not self.ai_right:
            if keys[pygame.K_UP]:
                self.right_y -= PADDLE_SPEED * dt
            if keys[pygame.K_DOWN]:
                self.right_y += PADDLE_SPEED * dt

        # Clamp to screen
        self.left_y = max(0, min(HEIGHT - PADDLE_H, self.left_y))
        self.right_y = max(0, min(HEIGHT - PADDLE_H, self.right_y))
        self.left.y = round(self.left_y)
        self.right.y = round(self.right_y)

    def update_ai(self, dt):
        if not self.ai_right:
            return
        # Simple follow-ball AI with small dead zone
        center = self.right_y + PADDLE_H / 2
        if center < self.ball.centery - 6:
            self.right_y += PADDLE_SPEED * dt
        elif center > self.ball.centery + 6:
            self.right_y -= PADDLE_SPEED * dt
        self.right_y = max(0, min(HEIGHT - PADDLE_H, self.right_y))
        self.right.y = round(self.right_y)

    # ----- Physics -----
    def update_ball(self, dt):
        if self.serve_timer > 0:
            self.serve_timer -= dt
            return

        # Move ball
        self.ball_pos += self.ball_vel * dt
        self.ball.center = (round(self.ball_pos.x), round(self.ball_pos.y))

        # Collide with top/bottom
        if self.ball.top <= 0:
            self.ball.top = 0
            self.ball_pos.y = self.ball.centery
            self.ball_vel.y *= -1
        elif self.ball.bottom >= HEIGHT:
            self.ball.bottom = HEIGHT
            self.ball_pos.y = self.ball.centery
            self.ball_vel.y *= -1

        # Collide with paddles
        if self.ball.colliderect(self.left) and self.ball_vel.x < 0:
            self.ball.left = self.left.right
            self.ball_pos.x = self.ball.centerx
            self._reflect_from_paddle(self.left, side='left')
        if self.ball.colliderect(self.right) and self.ball_vel.x > 0:
            self.ball.right = self.right.left
            self.ball_pos.x = self.ball.centerx
            self._reflect_from_paddle(self.right, side='right')

        # Score
        if self.ball.right < 0:
            self.score_r += 1
            if self.score_r >= WIN_SCORE:
                self.winner = "Right"
                self.paused = True
            self.reset(full=False, direction=1)
        elif self.ball.left > WIDTH:
            self.score_l += 1
            if self.score_l >= WIN_SCORE:
                self.winner = "Left"
                self.paused = True
            self.reset(full=False, direction=-1)

    def _reflect_from_paddle(self, paddle, side):
        """Reflect ball from paddle with angle based on impact point, and speed up a bit."""
        offset = (self.ball.centery - paddle.centery) / (PADDLE_H / 2)  # -1..1
        offset = max(-1.0, min(1.0, offset))
        max_angle = math.radians(60)  # max deflection
        angle = offset * max_angle

        speed = min(self.ball_vel.length() * BALL_SPEED_INC, BALL_SPEED_MAX)
        direction = 1 if side == 'left' else -1
        vx = math.cos(angle) * direction
        vy = math.sin(angle)
        v = pygame.Vector2(vx, vy)
        self.ball_vel = (v if v.length() > 0 else pygame.Vector2(direction, 0)).normalize() * speed

    # ----- Render -----
    def draw(self):
        self.screen.fill(BG)

        # Center net
        for y in range(0, HEIGHT, 24):
            pygame.draw.rect(self.screen, NET, (WIDTH // 2 - 2, y + 8, 4, 12))

        # Paddles and ball
        pygame.draw.rect(self.screen, FG, self.left)
        pygame.draw.rect(self.screen, FG, self.right)
        pygame.draw.ellipse(self.screen, FG, self.ball)

        # Score
        score = self.font.render(f"{self.score_l}   {self.score_r}", True, (230, 230, 230))
        self.screen.blit(score, score.get_rect(center=(WIDTH // 2, 40)))

        # UI hints
        help_text = ("W/S = Left   ↑/↓ = Right   1 = Toggle AI   "
                     "P = Pause   R = Restart   Esc = Quit")
        help_surf = self.small_font.render(help_text, True, (180, 180, 180))
        self.screen.blit(help_surf, (WIDTH // 2 - help_surf.get_width() // 2, HEIGHT - 30))

        if self.serve_timer > 0:
            msg = self.small_font.render("Get ready...", True, (180, 180, 180))
            self.screen.blit(msg, msg.get_rect(center=(WIDTH // 2, HEIGHT // 2)))

        if self.paused and self.winner:
            win = self.font.render(f"{self.winner} wins!", True, (255, 215, 0))
            self.screen.blit(win, win.get_rect(center=(WIDTH // 2, HEIGHT // 2 - 26)))
            hint = self.small_font.render("Press R to play again.", True, (200, 200, 200))
            self.screen.blit(hint, hint.get_rect(center=(WIDTH // 2, HEIGHT // 2 + 18)))

        pygame.display.flip()

    # ----- Main loop -----
    def run(self):
        while True:
            dt = self.clock.tick(60) / 1000.0  # seconds since last frame

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    pygame.quit(); sys.exit()
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        pygame.quit(); sys.exit()
                    if event.key == pygame.K_p:
                        self.paused = not self.paused
                    if event.key == pygame.K_r:
                        self.paused = False
                        self.reset(full=True)
                    if event.key == pygame.K_1:
                        self.ai_right = not self.ai_right

            if not self.paused:
                self.handle_input(dt)
                self.update_ai(dt)
                self.update_ball(dt)

            self.draw()


if __name__ == "__main__":
    Pong().run()
