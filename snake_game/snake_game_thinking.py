"""
Snake — Pygame version
Controls: Arrow keys / WASD to move, P to pause, R to restart, ESC to quit.
"""

import sys
import random
from collections import deque

import pygame

# ---------- Config ----------
TILE = 24                 # pixels per grid cell
GRID_W, GRID_H = 28, 22   # grid size in cells
FPS_START = 9             # starting speed (updates per second)
FPS_MAX = 24              # max speed
SPEEDUP_EVERY = 5         # gain 1 FPS every N apples

WINDOW_W, WINDOW_H = GRID_W * TILE, GRID_H * TILE
BORDER = 0                # set >0 for a framed border

# Colors (R, G, B)
BG      = (18, 18, 18)
SNAKE   = (60, 200, 120)
SNAKE2  = (40, 160, 100)  # alternating body shade
HEAD    = (240, 240, 240)
FOOD    = (220, 80, 80)
TEXT    = (230, 230, 230)
GRID    = (35, 35, 35)

# ---------- Helpers ----------
def add(a, b):
    return (a[0] + b[0], a[1] + b[1])

def inside_grid(cell):
    x, y = cell
    return 0 <= x < GRID_W and 0 <= y < GRID_H

def draw_rect(surface, color, cell):
    x, y = cell
    pygame.draw.rect(surface, color, (x * TILE + BORDER, y * TILE + BORDER, TILE - 2*BORDER, TILE - 2*BORDER), border_radius=6)

def rand_empty_cell(occupied):
    """Pick a random grid cell not in occupied."""
    while True:
        c = (random.randrange(GRID_W), random.randrange(GRID_H))
        if c not in occupied:
            return c

# ---------- Game ----------
class SnakeGame:
    def __init__(self):
        self.reset()

    def reset(self):
        self.direction = (1, 0)  # moving right
        self.pending_dir = self.direction
        mid = (GRID_W // 2, GRID_H // 2)
        self.snake = deque([add(mid, (-2, 0)), add(mid, (-1, 0)), mid])  # 3 long
        self.snake_set = set(self.snake)
        self.food = rand_empty_cell(self.snake_set)
        self.score = 0
        self.fps = FPS_START
        self.grow = False
        self.game_over = False
        self.paused = False

    def set_direction(self, new_dir):
        """Queue a direction change if it isn't an immediate reverse."""
        if self.game_over:
            return
        dx, dy = self.direction
        ndx, ndy = new_dir
        if (dx, dy) == (-ndx, -ndy):  # reverse guard
            return
        self.pending_dir = new_dir

    def step(self):
        if self.game_over or self.paused:
            return

        # apply queued direction
        self.direction = self.pending_dir

        head = self.snake[-1]
        nxt = add(head, self.direction)

        # wall collision
        if not inside_grid(nxt):
            self.game_over = True
            return

        # self collision (tail moves unless we grow)
        tail = self.snake[0]
        will_hit_self = nxt in self.snake_set and (not self.grow or nxt != tail)
        if will_hit_self:
            self.game_over = True
            return

        # move
        self.snake.append(nxt)
        self.snake_set.add(nxt)

        # eat?
        if nxt == self.food:
            self.score += 1
            self.grow = True
            self.food = rand_empty_cell(self.snake_set)
            if self.fps < FPS_MAX and self.score % SPEEDUP_EVERY == 0:
                self.fps += 1
        else:
            if self.grow:
                self.grow = False
            else:
                popped = self.snake.popleft()
                self.snake_set.remove(popped)

    def toggle_pause(self):
        if not self.game_over:
            self.paused = not self.paused

# ---------- Rendering ----------
def draw_grid(surface):
    # subtle grid
    for x in range(GRID_W):
        pygame.draw.line(surface, GRID, (x * TILE, 0), (x * TILE, WINDOW_H))
    for y in range(GRID_H):
        pygame.draw.line(surface, GRID, (0, y * TILE), (WINDOW_W, y * TILE))

def render(surface, game, font):
    surface.fill(BG)
    draw_grid(surface)

    # draw food
    draw_rect(surface, FOOD, game.food)

    # draw snake
    for i, cell in enumerate(list(game.snake)[:-1]):
        draw_rect(surface, SNAKE if i % 2 == 0 else SNAKE2, cell)
    draw_rect(surface, HEAD, game.snake[-1])

    # HUD
    score_surf = font.render(f"Score: {game.score}", True, TEXT)
    surface.blit(score_surf, (10, 8))

    if game.paused:
        msg = "Paused — press P to resume"
        text = font.render(msg, True, TEXT)
        surface.blit(text, (WINDOW_W // 2 - text.get_width() // 2, WINDOW_H // 2 - text.get_height() // 2))

    if game.game_over:
        big = pygame.font.SysFont(None, 64)
        small = pygame.font.SysFont(None, 28)
        over = big.render("Game Over", True, TEXT)
        tip = small.render("Press R to restart or ESC to quit", True, TEXT)
        surface.blit(over, (WINDOW_W // 2 - over.get_width() // 2, WINDOW_H // 2 - over.get_height()))
        surface.blit(tip, (WINDOW_W // 2 - tip.get_width() // 2, WINDOW_H // 2 + 10))

# ---------- Main loop ----------
def main():
    pygame.init()
    pygame.display.set_caption("Snake")
    screen = pygame.display.set_mode((WINDOW_W, WINDOW_H))
    clock = pygame.time.Clock()
    font = pygame.font.SysFont(None, 28)

    game = SnakeGame()

    key_to_dir = {
        pygame.K_UP:    (0, -1),
        pygame.K_w:     (0, -1),
        pygame.K_DOWN:  (0, 1),
        pygame.K_s:     (0, 1),
        pygame.K_LEFT:  (-1, 0),
        pygame.K_a:     (-1, 0),
        pygame.K_RIGHT: (1, 0),
        pygame.K_d:     (1, 0),
    }

    # Timed update event so speed = FPS regardless of frame rate
    UPDATE = pygame.USEREVENT + 1
    pygame.time.set_timer(UPDATE, int(1000 / game.fps))

    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit(); sys.exit()
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    pygame.quit(); sys.exit()
                if event.key == pygame.K_p:
                    game.toggle_pause()
                if event.key == pygame.K_r and game.game_over:
                    game.reset()
                    pygame.time.set_timer(UPDATE, int(1000 / game.fps))
                if event.key in key_to_dir:
                    game.set_direction(key_to_dir[event.key])
            elif event.type == UPDATE:
                # refresh timer in case speed changed
                pygame.time.set_timer(UPDATE, int(1000 / game.fps))
                game.step()

        render(screen, game, font)
        pygame.display.flip()
        clock.tick(60)  # render at up to 60 FPS; logic is driven by UPDATE timer

if __name__ == "__main__":
    main()
