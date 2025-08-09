import pygame
import random
import sys
from collections import deque

# ---------------------------
# Config
# ---------------------------
TILE_SIZE = 24
GRID_W, GRID_H = 24, 20  # 24x20 tiles -> 576x480 window
WIDTH, HEIGHT = GRID_W * TILE_SIZE, GRID_H * TILE_SIZE
FPS_START = 10
FPS_STEP = 0.75  # how much to speed up per apple
BORDERLESS = False
SHOW_GRID = False

# Colors
BLACK = (0, 0, 0)
WHITE = (255, 255, 255)
GRAY = (40, 40, 40)
GREEN = (80, 200, 120)
DARK_GREEN = (50, 160, 90)
RED = (220, 70, 70)
ORANGE = (255, 165, 0)

# Directions
UP = (0, -1)
DOWN = (0, 1)
LEFT = (-1, 0)
RIGHT = (1, 0)
OPPOSITE = {UP: DOWN, DOWN: UP, LEFT: RIGHT, RIGHT: LEFT}


class Snake:
    def __init__(self, start_pos):
        self.body = deque([start_pos, (start_pos[0] - 1, start_pos[1]), (start_pos[0] - 2, start_pos[1])])
        self.dir = RIGHT
        self.grow_pending = 0
        self.just_turned = False  # prevent multiple turns per tick

    def head(self):
        return self.body[0]

    def change_dir(self, new_dir):
        if self.just_turned:
            return
        if new_dir and new_dir != OPPOSITE[self.dir]:
            self.dir = new_dir
            self.just_turned = True

    def step(self):
        hx, hy = self.head()
        dx, dy = self.dir
        new_head = (hx + dx, hy + dy)
        self.body.appendleft(new_head)
        if self.grow_pending > 0:
            self.grow_pending -= 1
        else:
            self.body.pop()
        self.just_turned = False

    def grow(self, n=1):
        self.grow_pending += n

    def hits_self(self):
        return self.head() in list(self.body)[1:]


def random_empty_cell(occupied):
    while True:
        pos = (random.randrange(GRID_W), random.randrange(GRID_H))
        if pos not in occupied:
            return pos


def draw_grid(surf):
    for x in range(GRID_W):
        pygame.draw.line(surf, GRAY, (x * TILE_SIZE, 0), (x * TILE_SIZE, HEIGHT))
    for y in range(GRID_H):
        pygame.draw.line(surf, GRAY, (0, y * TILE_SIZE), (WIDTH, y * TILE_SIZE))


def draw_rect_tile(surf, color, pos, inset=2, radius=6):
    x, y = pos
    rect = pygame.Rect(x * TILE_SIZE + inset, y * TILE_SIZE + inset, TILE_SIZE - 2 * inset, TILE_SIZE - 2 * inset)
    pygame.draw.rect(surf, color, rect, border_radius=radius)


def game_loop():
    pygame.init()
    flags = pygame.NOFRAME if BORDERLESS else 0
    screen = pygame.display.set_mode((WIDTH, HEIGHT), flags)
    pygame.display.set_caption("Snake • Pygame")
    clock = pygame.time.Clock()
    font = pygame.font.SysFont("consolas", 20)
    big_font = pygame.font.SysFont("consolas", 40, bold=True)

    reset = True
    running = True

    while running:
        if reset:
            reset = False
            # init state
            snake = Snake((GRID_W // 2, GRID_H // 2))
            score = 0
            apples_eaten = 0
            speed = FPS_START
            food = random_empty_cell(set(snake.body))
            paused = False
            game_over = False

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key in (pygame.K_ESCAPE,):
                    running = False
                if event.key in (pygame.K_p,):
                    paused = not paused and not game_over
                if event.key in (pygame.K_r,):
                    reset = True
                # Direction controls
                if event.key in (pygame.K_UP, pygame.K_w):
                    snake.change_dir(UP)
                elif event.key in (pygame.K_DOWN, pygame.K_s):
                    snake.change_dir(DOWN)
                elif event.key in (pygame.K_LEFT, pygame.K_a):
                    snake.change_dir(LEFT)
                elif event.key in (pygame.K_RIGHT, pygame.K_d):
                    snake.change_dir(RIGHT)

        if not paused and not game_over:
            snake.step()
            hx, hy = snake.head()

            # Wall collision (wrap or die) — here we choose die
            if not (0 <= hx < GRID_W and 0 <= hy < GRID_H) or snake.hits_self():
                game_over = True

            # Eat food
            if not game_over and snake.head() == food:
                snake.grow()
                score += 10
                apples_eaten += 1
                speed = FPS_START + apples_eaten * FPS_STEP
                food = random_empty_cell(set(snake.body))

        # Draw
        screen.fill(BLACK)
        if SHOW_GRID:
            draw_grid(screen)

        # Food
        draw_rect_tile(screen, ORANGE, food, inset=4, radius=8)

        # Snake
        for i, segment in enumerate(snake.body):
            color = GREEN if i == 0 else DARK_GREEN
            draw_rect_tile(screen, color, segment)

        # HUD
        hud = font.render(f"Score: {score}", True, WHITE)
        screen.blit(hud, (8, 6))
        if paused:
            t = big_font.render("PAUSED", True, WHITE)
            screen.blit(t, t.get_rect(center=(WIDTH // 2, HEIGHT // 2)))
        if game_over:
            over = big_font.render("GAME OVER", True, RED)
            tip = font.render("Press R to restart, Esc to quit", True, WHITE)
            screen.blit(over, over.get_rect(center=(WIDTH // 2, HEIGHT // 2 - 10)))
            screen.blit(tip, tip.get_rect(center=(WIDTH // 2, HEIGHT // 2 + 24)))

        pygame.display.flip()
        clock.tick(speed)

    pygame.quit()
    sys.exit()


if __name__ == "__main__":
    try:
        game_loop()
    except SystemExit:
        pass
