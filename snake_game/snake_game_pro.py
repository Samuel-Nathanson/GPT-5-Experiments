#!/usr/bin/env python3
"""
Snake — a clean, fully-commented Pygame implementation.

Controls
- Arrow keys / WASD: move
- P: pause / resume
- R: restart
- Esc or window close: quit

Requirements
- Python 3.8+
- pygame 2.x  ->  pip install pygame

Tips
- To enable wrap-around walls, set WRAP = True below.
- Tweak GRID_W, GRID_H, TILE_SIZE to change the board size.
"""
import sys
import random
from collections import deque

# Try to import pygame with a friendly error if missing.
try:
    import pygame
except Exception as e:
    print("This game requires the 'pygame' package.\n"
          "Install it with:\n\n    pip install pygame\n")
    sys.exit(1)

# ----------------------------- Configuration ------------------------------ #
TILE_SIZE = 20
GRID_W, GRID_H = 32, 24                      # 32x24 tiles -> 640x480 window
WINDOW_W, WINDOW_H = GRID_W * TILE_SIZE, GRID_H * TILE_SIZE

SPEED_START = 7                               # starting moves per second
SPEED_MAX = 20                                # cap the speed
SPEED_INCREASE_EVERY = 5                      # +1 mps every N foods

WRAP = False                                  # set True for wrap-around walls

# Colors (R, G, B)
BG     = (18, 18, 28)
GRID   = (35, 37, 49)
SNAKE  = (80, 200, 120)
HEAD   = (144, 238, 144)
FOOD   = (235, 64, 52)
TEXT   = (240, 240, 240)
UI_DIM = (0, 0, 0, 140)                       # translucent overlay

# ------------------------------ Utilities --------------------------------- #
def grid_to_px(cell):
    """Convert a (x, y) grid coordinate to a pygame.Rect in pixels."""
    x, y = cell
    return pygame.Rect(x * TILE_SIZE, y * TILE_SIZE, TILE_SIZE, TILE_SIZE)

def draw_text(surface, text, size, center, color=TEXT, bold=True):
    """Render text centered at a position."""
    font = pygame.font.SysFont("consolas", size, bold=bold)
    render = font.render(text, True, color)
    rect = render.get_rect(center=center)
    surface.blit(render, rect)

def spawn_food(occupied, width, height):
    """
    Return a random free cell (x, y) not in 'occupied'.
    If the board is full, return None.
    """
    total_cells = width * height
    if len(occupied) >= total_cells:
        return None
    # Rejection sampling is simple and fast for typical snake sizes.
    while True:
        pos = (random.randrange(width), random.randrange(height))
        if pos not in occupied:
            return pos

def opposite(a, b):
    """True if direction a is the opposite of direction b."""
    return a[0] == -b[0] and a[1] == -b[1]

# ------------------------------ Game Setup -------------------------------- #
def new_game():
    """Initialize a fresh game state."""
    snake = deque()
    start = (GRID_W // 2, GRID_H // 2)
    snake.append(start)
    snake_set = {start}
    direction = (1, 0)     # moving right initially
    next_dir = direction
    food = spawn_food(snake_set, GRID_W, GRID_H)
    score = 0
    paused = False
    dead = False
    victory = False
    return {
        "snake": snake,
        "snake_set": snake_set,
        "direction": direction,
        "next_dir": next_dir,
        "food": food,
        "score": score,
        "paused": paused,
        "dead": dead,
        "victory": victory,
    }

def current_speed(score):
    """Moves per second based on score progression."""
    mps = SPEED_START + (score // SPEED_INCREASE_EVERY)
    return min(mps, SPEED_MAX)

# ------------------------------ Main Loop --------------------------------- #
def main():
    pygame.init()
    screen = pygame.display.set_mode((WINDOW_W, WINDOW_H))
    pygame.display.set_caption("Snake — Arrow keys/WASD | P: Pause | R: Restart | Esc: Quit")
    clock = pygame.time.Clock()

    state = new_game()

    # Movement timing (frame-rate independent)
    move_timer_ms = 0.0
    running = True

    while running:
        dt = clock.tick(60)  # limit to ~60 FPS and get elapsed ms
        # ------------------------- Event handling ------------------------- #
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False

            elif event.type == pygame.KEYDOWN:
                if event.key in (pygame.K_ESCAPE,):
                    running = False

                # Direction changes
                elif event.key in (pygame.K_UP, pygame.K_w):
                    if not opposite((0, -1), state["direction"]):
                        state["next_dir"] = (0, -1)
                elif event.key in (pygame.K_DOWN, pygame.K_s):
                    if not opposite((0, 1), state["direction"]):
                        state["next_dir"] = (0, 1)
                elif event.key in (pygame.K_LEFT, pygame.K_a):
                    if not opposite((-1, 0), state["direction"]):
                        state["next_dir"] = (-1, 0)
                elif event.key in (pygame.K_RIGHT, pygame.K_d):
                    if not opposite((1, 0), state["direction"]):
                        state["next_dir"] = (1, 0)

                # Pause / restart
                elif event.key == pygame.K_p:
                    if not state["dead"] and not state["victory"]:
                        state["paused"] = not state["paused"]
                elif event.key == pygame.K_r:
                    state = new_game()
                    move_timer_ms = 0.0

        # ------------------------- Update logic --------------------------- #
        if not state["paused"] and not state["dead"] and not state["victory"]:
            move_timer_ms += dt
            mps = current_speed(state["score"])
            step_every_ms = 1000.0 / mps

            while move_timer_ms >= step_every_ms:
                move_timer_ms -= step_every_ms

                # Apply queued direction
                state["direction"] = state["next_dir"]

                # Compute next head
                hx, hy = state["snake"][0]
                dx, dy = state["direction"]
                nx, ny = hx + dx, hy + dy

                if WRAP:
                    nx %= GRID_W
                    ny %= GRID_H
                else:
                    if nx < 0 or nx >= GRID_W or ny < 0 or ny >= GRID_H:
                        state["dead"] = True
                        break

                new_head = (nx, ny)
                ate = (new_head == state["food"])

                # If not eating, we advance tail first (so moving into the previous tail is allowed)
                if not ate:
                    tail = state["snake"].pop()
                    state["snake_set"].remove(tail)

                # Self-collision check after potential tail removal
                if new_head in state["snake_set"]:
                    state["dead"] = True
                    break

                # Advance head
                state["snake"].appendleft(new_head)
                state["snake_set"].add(new_head)

                if ate:
                    state["score"] += 1
                    state["food"] = spawn_food(state["snake_set"], GRID_W, GRID_H)
                    if state["food"] is None:
                        state["victory"] = True
                        break

        # ------------------------- Rendering ------------------------------ #
        screen.fill(BG)

        # Optional grid
        for x in range(GRID_W + 1):
            px = x * TILE_SIZE
            pygame.draw.line(screen, GRID, (px, 0), (px, WINDOW_H), 1)
        for y in range(GRID_H + 1):
            py = y * TILE_SIZE
            pygame.draw.line(screen, GRID, (0, py), (WINDOW_W, py), 1)

        # Food
        if state["food"] is not None:
            r = grid_to_px(state["food"]).inflate(-TILE_SIZE * 0.2, -TILE_SIZE * 0.2)
            pygame.draw.ellipse(screen, FOOD, r)

        # Snake body
        for i, (x, y) in enumerate(state["snake"]):
            rect = grid_to_px((x, y)).inflate(-4, -4)
            color = HEAD if i == 0 else SNAKE
            pygame.draw.rect(screen, color, rect, border_radius=4)

        # HUD
        mps = current_speed(state["score"])
        draw_text(screen, f"Score: {state['score']}   Speed: {int(mps)} mps", 20, (110, 14))
        draw_text(screen, f"{'WRAP' if WRAP else 'WALLS'}", 16, (WINDOW_W - 50, 14))

        # Overlays
        if state["paused"]:
            overlay = pygame.Surface((WINDOW_W, WINDOW_H), pygame.SRCALPHA)
            overlay.fill(UI_DIM)
            screen.blit(overlay, (0, 0))
            draw_text(screen, "PAUSED", 48, (WINDOW_W // 2, WINDOW_H // 2 - 10))
            draw_text(screen, "Press P to resume", 24, (WINDOW_W // 2, WINDOW_H // 2 + 28))

        if state["dead"]:
            overlay = pygame.Surface((WINDOW_W, WINDOW_H), pygame.SRCALPHA)
            overlay.fill(UI_DIM)
            screen.blit(overlay, (0, 0))
            draw_text(screen, "GAME OVER", 48, (WINDOW_W // 2, WINDOW_H // 2 - 18))
            draw_text(screen, "Press R to restart", 24, (WINDOW_W // 2, WINDOW_H // 2 + 20))

        if state["victory"]:
            overlay = pygame.Surface((WINDOW_W, WINDOW_H), pygame.SRCALPHA)
            overlay.fill(UI_DIM)
            screen.blit(overlay, (0, 0))
            draw_text(screen, "YOU WIN!", 48, (WINDOW_W // 2, WINDOW_H // 2 - 18))
            draw_text(screen, "Press R to play again", 24, (WINDOW_W // 2, WINDOW_H // 2 + 20))

        pygame.display.flip()

    pygame.quit()

if __name__ == "__main__":
    main()
