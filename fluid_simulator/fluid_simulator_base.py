import cupy as cp
import pygame

# =====================
# SIMULATION PARAMETERS
# =====================
N = 128
DT = 0.1
DIFF = 0.0001
VISC = 0.0001
FORCE = 8.0
SOURCE = 150.0
ITER = 20

# =====================
# FLUID FUNCTIONS (GPU)
# =====================
def add_source(x, s):
    x += DT * s

def set_bnd(b, x):
    x[0, 1:-1] = -x[1, 1:-1] if b == 1 else x[1, 1:-1]
    x[-1, 1:-1] = -x[-2, 1:-1] if b == 1 else x[-2, 1:-1]
    x[1:-1, 0] = -x[1:-1, 1] if b == 2 else x[1:-1, 1]
    x[1:-1, -1] = -x[1:-1, -2] if b == 2 else x[1:-1, -2]
    x[0, 0] = 0.5 * (x[1, 0] + x[0, 1])
    x[0, -1] = 0.5 * (x[1, -1] + x[0, -2])
    x[-1, 0] = 0.5 * (x[-2, 0] + x[-1, 1])
    x[-1, -1] = 0.5 * (x[-2, -1] + x[-1, -2])

def diffuse(b, x, x0, diff):
    a = DT * diff * N * N
    for _ in range(ITER):
        x[1:-1, 1:-1] = (x0[1:-1, 1:-1] + a * (
            x[2:, 1:-1] + x[:-2, 1:-1] +
            x[1:-1, 2:] + x[1:-1, :-2])) / (1 + 4 * a)
        set_bnd(b, x)

def advect(b, d, d0, u, v):
    dt0 = DT * N
    i = cp.arange(1, N+1)
    j = cp.arange(1, N+1)
    I, J = cp.meshgrid(i, j, indexing='ij')

    x = I - dt0 * u[1:-1, 1:-1]
    y = J - dt0 * v[1:-1, 1:-1]

    x = cp.clip(x, 0.5, N + 0.5)
    y = cp.clip(y, 0.5, N + 0.5)

    i0 = cp.floor(x).astype(cp.int32)
    i1 = i0 + 1
    j0 = cp.floor(y).astype(cp.int32)
    j1 = j0 + 1

    s1 = x - i0
    s0 = 1 - s1
    t1 = y - j0
    t0 = 1 - t1

    d[1:-1, 1:-1] = (s0 * (t0 * d0[i0, j0] + t1 * d0[i0, j1]) +
                     s1 * (t0 * d0[i1, j0] + t1 * d0[i1, j1]))
    set_bnd(b, d)

def project(u, v, p, div):
    div[1:-1, 1:-1] = -0.5 * (
        u[2:, 1:-1] - u[:-2, 1:-1] +
        v[1:-1, 2:] - v[1:-1, :-2]) / N
    p.fill(0)
    set_bnd(0, div)
    set_bnd(0, p)

    for _ in range(ITER):
        p[1:-1, 1:-1] = (div[1:-1, 1:-1] +
                         p[2:, 1:-1] + p[:-2, 1:-1] +
                         p[1:-1, 2:] + p[1:-1, :-2]) / 4
        set_bnd(0, p)

    u[1:-1, 1:-1] -= 0.5 * (p[2:, 1:-1] - p[:-2, 1:-1]) * N
    v[1:-1, 1:-1] -= 0.5 * (p[1:-1, 2:] - p[1:-1, :-2]) * N
    set_bnd(1, u)
    set_bnd(2, v)

def vel_step(u, v, u0, v0):
    add_source(u, u0)
    add_source(v, v0)
    u0, u = u, u0
    diffuse(1, u, u0, VISC)
    v0, v = v, v0
    diffuse(2, v, v0, VISC)
    project(u, v, u0, v0)
    u0, u = u, u0
    v0, v = v, v0
    advect(1, u, u0, u0, v0)
    advect(2, v, v0, u0, v0)
    project(u, v, u0, v0)

def dens_step(x, x0, u, v):
    add_source(x, x0)
    x0, x = x, x0
    diffuse(0, x, x0, DIFF)
    x0, x = x, x0
    advect(0, x, x0, u, v)

# =====================
# INITIALIZATION
# =====================
size = (N+2, N+2)
u = cp.zeros(size)
v = cp.zeros(size)
u_prev = cp.zeros(size)
v_prev = cp.zeros(size)
dens = cp.zeros(size)
dens_prev = cp.zeros(size)

pygame.init()
scale = 6
screen = pygame.display.set_mode((N*scale, N*scale))
clock = pygame.time.Clock()

# =====================
# MAIN LOOP
# =====================
running = True
while running:
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False

    mouse = pygame.mouse.get_pressed()
    if mouse[0]:
        mx, my = pygame.mouse.get_pos()
        i, j = mx // scale, my // scale
        dens_prev[i, j] = SOURCE
    if mouse[2]:
        mx, my = pygame.mouse.get_pos()
        i, j = mx // scale, my // scale
        u_prev[i, j] = FORCE
        v_prev[i, j] = FORCE

    vel_step(u, v, u_prev, v_prev)
    dens_step(dens, dens_prev, u, v)

    arr = cp.asnumpy(dens)
    arr = cp.clip(arr, 0, 255).astype(cp.uint8)
    surf = pygame.surfarray.make_surface(cp.repeat(cp.repeat(arr.T, scale, axis=0), scale, axis=1))
    screen.blit(surf, (0, 0))

    pygame.display.flip()
    clock.tick(60)

    u_prev.fill(0)
    v_prev.fill(0)
    dens_prev.fill(0)

pygame.quit()
