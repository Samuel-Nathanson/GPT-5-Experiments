import math
import time
from dataclasses import dataclass

import numpy as np
import pygame


# ---------------------------
# Utility
# ---------------------------

def clamp(x, lo, hi):
    return lo if x < lo else hi if x > hi else x


# ---------------------------
# Stable Fluids Core
# ---------------------------

@dataclass
class Params:
    N: int = 128          # grid size (inner cells are N x N)
    dt: float = 1/60      # base timestep
    diff: float = 2e-5    # diffusion coefficient for dye
    visc: float = 1e-4    # kinematic viscosity for velocity
    iters: int = 20       # Jacobi iterations for linear solves
    buoyancy: float = 0.6 # upward force per unit density
    vorticity: float = 2.0  # vorticity confinement strength


class Fluid:
    """
    Incompressible Navier–Stokes 'Stable Fluids' solver on a staggered-like
    MAC-ish grid (but stored as collocated arrays with boundary treatment).
    Arrays are shape (N+2, N+2) including ghost cells.
    """
    def __init__(self, params: Params):
        self.params = params
        N = params.N
        shape = (N + 2, N + 2)

        # Float32 for speed
        self.u  = np.zeros(shape, dtype=np.float32)
        self.v  = np.zeros(shape, dtype=np.float32)
        self.u0 = np.zeros(shape, dtype=np.float32)
        self.v0 = np.zeros(shape, dtype=np.float32)

        self.dens  = np.zeros(shape, dtype=np.float32)
        self.dens0 = np.zeros(shape, dtype=np.float32)

        # scratch for projection
        self.p   = np.zeros(shape, dtype=np.float32)
        self.div = np.zeros(shape, dtype=np.float32)

        # Precompute index grids for advection (interior cells only)
        I, J = np.meshgrid(np.arange(1, N+1), np.arange(1, N+1), indexing="ij")
        self.I = I.astype(np.float32)
        self.J = J.astype(np.float32)

    # ---- Boundary conditions ----
    def set_bnd(self, b, x):
        N = self.params.N
        # Horizontal boundaries
        if b == 1:
            x[0, 1:-1]   = -x[1, 1:-1]
            x[N+1, 1:-1] = -x[N, 1:-1]
        else:
            x[0, 1:-1]   =  x[1, 1:-1]
            x[N+1, 1:-1] =  x[N, 1:-1]

        # Vertical boundaries
        if b == 2:
            x[1:-1, 0]   = -x[1:-1, 1]
            x[1:-1, N+1] = -x[1:-1, N]
        else:
            x[1:-1, 0]   =  x[1:-1, 1]
            x[1:-1, N+1] =  x[1:-1, N]

        # Corners
        x[0, 0]       = 0.5 * (x[1, 0] + x[0, 1])
        x[0, N+1]     = 0.5 * (x[1, N+1] + x[0, N])
        x[N+1, 0]     = 0.5 * (x[N, 0] + x[N+1, 1])
        x[N+1, N+1]   = 0.5 * (x[N, N+1] + x[N+1, N])

    # ---- Linear diffusion solve ----
    def diffuse(self, b, x, x0, diff, dt):
        N = self.params.N
        a = dt * diff * N * N
        c = 1.0 / (1 + 4 * a)
        for _ in range(self.params.iters):
            x[1:-1, 1:-1] = c * (
                x0[1:-1, 1:-1] + a * (
                    x[0:-2, 1:-1] + x[2:, 1:-1] +
                    x[1:-1, 0:-2] + x[1:-1, 2:]
                )
            )
            self.set_bnd(b, x)

    # ---- Semi-Lagrangian advection ----
    def advect(self, b, d, d0, u, v, dt):
        N = self.params.N
        I = self.I
        J = self.J

        # Backtrace
        x = I - dt * N * u[1:-1, 1:-1]
        y = J - dt * N * v[1:-1, 1:-1]

        # Clamp to interior
        np.clip(x, 0.5, N + 0.5, out=x)
        np.clip(y, 0.5, N + 0.5, out=y)

        i0 = x.astype(np.int32)
        j0 = y.astype(np.int32)
        i1 = i0 + 1
        j1 = j0 + 1

        s1 = x - i0
        s0 = 1.0 - s1
        t1 = y - j0
        t0 = 1.0 - t1

        # Bilinear sample from d0
        d[1:-1, 1:-1] = (
            s0 * (t0 * d0[i0, j0] + t1 * d0[i0, j1]) +
            s1 * (t0 * d0[i1, j0] + t1 * d0[i1, j1])
        )

        self.set_bnd(b, d)

    # ---- Projection to make velocity divergence-free ----
    def project(self, u, v, p, div):
        N = self.params.N
        # Divergence (negative half divergence per cell)
        div[1:-1, 1:-1] = -0.5 * (
            u[2:, 1:-1] - u[0:-2, 1:-1] +
            v[1:-1, 2:] - v[1:-1, 0:-2]
        ) / N
        p.fill(0.0)
        self.set_bnd(0, div)
        self.set_bnd(0, p)

        # Solve Poisson for pressure with Jacobi iterations
        for _ in range(self.params.iters):
            p[1:-1, 1:-1] = 0.25 * (
                div[1:-1, 1:-1] +
                p[0:-2, 1:-1] + p[2:, 1:-1] +
                p[1:-1, 0:-2] + p[1:-1, 2:]
            )
            self.set_bnd(0, p)

        # Subtract pressure gradient
        u[1:-1, 1:-1] -= 0.5 * N * (p[2:, 1:-1] - p[0:-2, 1:-1])
        v[1:-1, 1:-1] -= 0.5 * N * (p[1:-1, 2:] - p[1:-1, 0:-2])
        self.set_bnd(1, u)
        self.set_bnd(2, v)

    # ---- Vorticity confinement (adds swirl) ----
    def vorticity_confinement(self, u, v, eps, dt):
        if eps <= 0.0:
            return
        N = self.params.N
        curl = np.zeros_like(u)
        # Scalar vorticity ω = ∂v/∂x - ∂u/∂y
        curl[1:-1, 1:-1] = (
            (v[2:, 1:-1] - v[0:-2, 1:-1]) -
            (u[1:-1, 2:] - u[1:-1, 0:-2])
        ) * 0.5

        # |ω| gradient
        absw = np.abs(curl)
        Nx = np.zeros_like(u)
        Ny = np.zeros_like(v)
        Nx[1:-1, 1:-1] = (absw[2:, 1:-1] - absw[0:-2, 1:-1]) * 0.5
        Ny[1:-1, 1:-1] = (absw[1:-1, 2:] - absw[1:-1, 0:-2]) * 0.5

        mag = np.sqrt(Nx * Nx + Ny * Ny) + 1e-6
        Nx /= mag
        Ny /= mag

        # Force = ε (N × ω ẑ) => (Fx, Fy) = ε (Ny*ω, -Nx*ω)
        Fx = eps * Ny * curl
        Fy = -eps * Nx * curl

        u[1:-1, 1:-1] += dt * Fx[1:-1, 1:-1]
        v[1:-1, 1:-1] += dt * Fy[1:-1, 1:-1]

        self.set_bnd(1, u)
        self.set_bnd(2, v)

    # ---- Buoyancy (density up) ----
    def buoyancy_force(self, v, dens, coeff, dt):
        if coeff <= 0.0:
            return
        v[1:-1, 1:-1] += dt * coeff * dens[1:-1, 1:-1]
        self.set_bnd(2, v)

    # ---- External sources ----
    def add_source(self, x, s, dt):
        x += dt * s

    # ---- Steps ----
    def vel_step(self, dt):
        p = self.params

        # external forces from u0, v0
        self.add_source(self.u, self.u0, dt)
        self.add_source(self.v, self.v0, dt)
        self.u0.fill(0.0)
        self.v0.fill(0.0)

        # buoyancy & vorticity confinement act directly on velocity
        self.buoyancy_force(self.v, self.dens, p.buoyancy, dt)
        self.vorticity_confinement(self.u, self.v, p.vorticity, dt)

        # diffuse
        self.u0[:, :] = self.u
        self.v0[:, :] = self.v
        self.diffuse(1, self.u, self.u0, p.visc, dt)
        self.diffuse(2, self.v, self.v0, p.visc, dt)

        # project
        self.project(self.u, self.v, self.p, self.div)

        # advect
        self.u0[:, :] = self.u
        self.v0[:, :] = self.v
        self.advect(1, self.u, self.u0, self.u0, self.v0, dt)
        self.advect(2, self.v, self.v0, self.u0, self.v0, dt)

        # project again
        self.project(self.u, self.v, self.p, self.div)

    def dens_step(self, dt):
        p = self.params
        self.add_source(self.dens, self.dens0, dt)
        self.dens0.fill(0.0)

        self.dens0[:, :] = self.dens
        self.diffuse(0, self.dens, self.dens0, p.diff, dt)
        self.dens0[:, :] = self.dens
        self.advect(0, self.dens, self.dens0, self.u, self.v, dt)

    def step(self, dt):
        self.vel_step(dt)
        self.dens_step(dt)

    # ---- Interaction helpers ----
    def add_density_brush(self, i, j, amount, radius):
        N = self.params.N
        i = clamp(i, 1, N)
        j = clamp(j, 1, N)
        r = int(max(1, radius))
        for ii in range(max(1, i - r), min(N, i + r) + 1):
            for jj in range(max(1, j - r), min(N, j + r) + 1):
                if (ii - i) ** 2 + (jj - j) ** 2 <= r * r:
                    self.dens0[ii, jj] += amount

    def add_velocity_brush(self, i, j, vx, vy, radius):
        N = self.params.N
        i = clamp(i, 1, N)
        j = clamp(j, 1, N)
        r = int(max(1, radius))
        for ii in range(max(1, i - r), min(N, i + r) + 1):
            for jj in range(max(1, j - r), min(N, j + r) + 1):
                if (ii - i) ** 2 + (jj - j) ** 2 <= r * r:
                    self.u0[ii, jj] += vx
                    self.v0[ii, jj] += vy

    def clear(self):
        for arr in (self.u, self.v, self.u0, self.v0, self.dens, self.dens0, self.p, self.div):
            arr.fill(0.0)


# ---------------------------
# Pygame App
# ---------------------------

class App:
    def __init__(self, N=128, window=800):
        pygame.init()
        pygame.display.set_caption("Interactive Fluid Simulator (Stable Fluids)")
        self.screen = pygame.display.set_mode((window, window))
        self.clock = pygame.time.Clock()
        self.font = pygame.font.SysFont("consolas", 16)

        self.params = Params(N=N)
        self.fluid = Fluid(self.params)

        # UI state
        self.running = True
        self.paused = False
        self.show_vectors = False
        self.show_pressure = False
        self.auto_exposure = True

        self.brush_radius = 6
        self.dye_amount = 200.0  # per second (scaled by dt)
        self.vel_scale = 50.0    # how strong mouse drag maps to velocity
        self.vec_skip = max(1, N // 24)  # spacing for velocity vectors

        self.prev_mouse = None

    def grid_from_screen(self, pos):
        x, y = pos
        w, h = self.screen.get_size()
        N = self.params.N
        col = int((x / w) * N) + 1  # x → column
        row = int((y / h) * N) + 1  # y → row
        return row, col             # IMPORTANT: return (y, x)


    def handle_input(self, dt):
        keys = pygame.key.get_pressed()
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
            elif event.type == pygame.KEYDOWN:
                if event.key in (pygame.K_ESCAPE,):
                    self.running = False
                elif event.key == pygame.K_v:
                    self.show_vectors = not self.show_vectors
                elif event.key == pygame.K_p:
                    self.show_pressure = not self.show_pressure
                elif event.key == pygame.K_a:
                    self.auto_exposure = not self.auto_exposure
                elif event.key == pygame.K_c:
                    self.fluid.clear()
                elif event.key == pygame.K_SPACE:
                    self.paused = not self.paused

                elif event.key == pygame.K_LEFTBRACKET:
                    self.brush_radius = max(1, self.brush_radius - 1)
                elif event.key == pygame.K_RIGHTBRACKET:
                    self.brush_radius = min(64, self.brush_radius + 1)
                elif event.key == pygame.K_MINUS:
                    self.dye_amount = max(1.0, self.dye_amount * 0.8)
                elif event.key == pygame.K_EQUALS:
                    self.dye_amount = min(5000.0, self.dye_amount * 1.25)

                elif event.key == pygame.K_1:
                    self.params.visc = max(1e-6, self.params.visc * 0.5)
                elif event.key == pygame.K_2:
                    self.params.visc = min(1e-2, self.params.visc * 1.5)
                elif event.key == pygame.K_3:
                    self.params.diff = max(1e-7, self.params.diff * 0.5)
                elif event.key == pygame.K_4:
                    self.params.diff = min(1e-2, self.params.diff * 1.5)
                elif event.key == pygame.K_5:
                    self.params.vorticity = max(0.0, self.params.vorticity * 0.8)
                elif event.key == pygame.K_6:
                    self.params.vorticity = min(10.0, self.params.vorticity * 1.25)
                elif event.key == pygame.K_7:
                    self.params.buoyancy = max(0.0, self.params.buoyancy * 0.8)
                elif event.key == pygame.K_8:
                    self.params.buoyancy = min(5.0, self.params.buoyancy * 1.25)

        # Mouse brushes
        buttons = pygame.mouse.get_pressed(3)
        pos = pygame.mouse.get_pos()
        i, j = self.grid_from_screen(pos)

        if buttons[0]:  # left: dye
            self.fluid.add_density_brush(i, j, self.dye_amount, self.brush_radius)

        if buttons[2]:  # right: velocity
            if self.prev_mouse is None:
                self.prev_mouse = pos
            pmx, pmy = self.prev_mouse
            mx, my = pos
            dx = (mx - pmx) / max(self.screen.get_width(), 1)
            dy = (my - pmy) / max(self.screen.get_height(), 1)
            # Map to grid-scale velocity (drag speed * scale)
            vx = dx * self.vel_scale
            vy = dy * self.vel_scale
            self.fluid.add_velocity_brush(i, j, vx, vy, self.brush_radius)

        self.prev_mouse = pos if (buttons[0] or buttons[2]) else None

    # ---- Rendering ----
    def render(self):
        w, h = self.screen.get_size()
        N = self.params.N

        # Dye (density) to grayscale
        field = self.fluid.dens[1:-1, 1:-1]
        if self.auto_exposure:
            mx = field.max()
            scale = 255.0 / (mx + 1e-6)
            scale = clamp(scale, 1.0, 255.0)
        else:
            scale = 2.0  # lower if too bright

        img = np.clip(field * scale, 0, 255).astype(np.uint8)
        rgb = np.stack([img, img, img], axis=2)  # (N, N, 3)
        surf = pygame.surfarray.make_surface(np.transpose(rgb, (1, 0, 2)))
        surf = pygame.transform.smoothscale(surf, (w, h))
        self.screen.blit(surf, (0, 0))

        # Pressure overlay (optional): blue=low, red=high
        if self.show_pressure:
            p = self.fluid.p[1:-1, 1:-1]
            pmin, pmax = float(p.min()), float(p.max())
            if abs(pmax - pmin) > 1e-6:
                pn = (p - pmin) / (pmax - pmin)  # 0..1
                r = (pn * 255).astype(np.uint8)
                g = np.zeros_like(r)
                b = ((1.0 - pn) * 255).astype(np.uint8)
                prgb = np.stack([r, g, b], axis=2)
                psurf = pygame.surfarray.make_surface(np.transpose(prgb, (1, 0, 2)))
                psurf = pygame.transform.smoothscale(psurf, (w, h))
                psurf.set_alpha(96)  # translucent
                self.screen.blit(psurf, (0, 0))

        # Velocity vectors (optional)
        if self.show_vectors:
            step = self.vec_skip
            u = self.fluid.u
            v = self.fluid.v
            for ii in range(1, N, step):
                for jj in range(1, N, step):
                    cx = (ii - 0.5) / N * w
                    cy = (jj - 0.5) / N * h
                    vx = float(u[ii, jj])
                    vy = float(v[ii, jj])
                    # visual scale:
                    sx = cx + vx * 8.0
                    sy = cy + vy * 8.0
                    pygame.draw.line(self.screen, (0, 255, 0), (cx, cy), (sx, sy), 1)
                    # tiny arrow head
                    pygame.draw.circle(self.screen, (0, 255, 0), (int(sx), int(sy)), 1)

        # HUD text
        self.draw_hud()

        pygame.display.flip()

    def draw_hud(self):
        p = self.params
        lines = [
            f"[LMB] dye  [RMB] velocity   radius=[{self.brush_radius}]  dye={self.dye_amount:.1f}/s",
            f"visc={p.visc:.2e}  diff={p.diff:.2e}  vort={p.vorticity:.2f}  buoy={p.buoyancy:.2f}",
            "[V] vectors  [P] pressure  [A] auto exposure  [C] clear  [Space] pause",
            "[ ] radius   [-/=] dye   [1/2] visc   [3/4] diff   [5/6] vorticity   [7/8] buoyancy",
            f"FPS: {self.clock.get_fps():.0f}   paused: {self.paused}"
        ]
        y = 6
        for s in lines:
            surf = self.font.render(s, True, (255, 255, 255))
            self.screen.blit(surf, (8, y))
            y += 18

    def run(self):
        # Basic fixed timestep with frame-time cap for stability
        base_dt = self.params.dt
        while self.running:
            frame_ms = self.clock.tick(120)  # cap to 120 fps
            # Use a modest dt for stability, but don’t exceed 2*base
            dt = min(base_dt * 2.0, frame_ms / 1000.0)
            # Input
            self.handle_input(dt)
            # Update
            if not self.paused:
                # Substep if we fell behind
                steps = max(1, int(round(dt / base_dt)))
                sub_dt = dt / steps
                for _ in range(steps):
                    self.fluid.step(sub_dt)
            # Render
            self.render()
        pygame.quit()


if __name__ == "__main__":
    # Tweak N or window size if you want more/less detail or speed.
    App(N=128, window=900).run()
