# fluid_sim.py
# 2D Stable Fluids (Jos Stam) in pure NumPy with interactive Matplotlib viz.
# Left-drag: add dye. Right-drag: add velocity. Press 'r' to reset.

import numpy as np
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation

# ------------------------- Core solver (Stable Fluids) -------------------------

def set_bnd(b, x):
    N = x.shape[0] - 2
    # Horizontal edges
    x[0, 1:N+1]     = -x[1, 1:N+1]     if b == 1 else x[1, 1:N+1]
    x[N+1, 1:N+1]   = -x[N, 1:N+1]     if b == 1 else x[N, 1:N+1]
    # Vertical edges
    x[1:N+1, 0]     = -x[1:N+1, 1]     if b == 2 else x[1:N+1, 1]
    x[1:N+1, N+1]   = -x[1:N+1, N]     if b == 2 else x[1:N+1, N]
    # Corners
    x[0,0]          = 0.5 * (x[1,0] + x[0,1])
    x[0,N+1]        = 0.5 * (x[1,N+1] + x[0,N])
    x[N+1,0]        = 0.5 * (x[N,0] + x[N+1,1])
    x[N+1,N+1]      = 0.5 * (x[N,N+1] + x[N+1,N])

def add_source(x, s, dt):
    x += dt * s

def lin_solve(b, x, x0, a, c, iters=20):
    N = x.shape[0] - 2
    inv_c = 1.0 / c
    for _ in range(iters):
        x[1:N+1, 1:N+1] = (
            x0[1:N+1, 1:N+1]
            + a * (x[0:N, 1:N+1] + x[2:N+2, 1:N+1] + x[1:N+1, 0:N] + x[1:N+1, 2:N+2])
        ) * inv_c
        set_bnd(b, x)

def diffuse(b, x, x0, diff, dt):
    N = x.shape[0] - 2
    a = dt * diff * N * N
    lin_solve(b, x, x0, a, 1 + 4 * a)

def advect(b, d, d0, u, v, dt):
    N = d.shape[0] - 2
    dt0 = dt * N
    # For each cell center, trace backwards
    i = np.arange(1, N+1)
    j = np.arange(1, N+1)
    I, J = np.meshgrid(i, j, indexing='ij')  # I -> x, J -> y

    x = I - dt0 * u[I, J]
    y = J - dt0 * v[I, J]

    # Clamp to [0.5, N + 0.5]
    x = np.clip(x, 0.5, N + 0.5)
    y = np.clip(y, 0.5, N + 0.5)

    i0 = np.floor(x).astype(int)
    i1 = i0 + 1
    j0 = np.floor(y).astype(int)
    j1 = j0 + 1

    s1 = x - i0
    s0 = 1.0 - s1
    t1 = y - j0
    t0 = 1.0 - t1

    # Bilinear sample from d0
    d[1:N+1, 1:N+1] = (
        s0 * (t0 * d0[i0, j0] + t1 * d0[i0, j1]) +
        s1 * (t0 * d0[i1, j0] + t1 * d0[i1, j1])
    )
    set_bnd(b, d)

def project(u, v, p, div):
    N = u.shape[0] - 2
    h = 1.0 / N
    div[1:N+1, 1:N+1] = -0.5 * h * (
        u[2:N+2, 1:N+1] - u[0:N, 1:N+1] +
        v[1:N+1, 2:N+2] - v[1:N+1, 0:N]
    )
    p.fill(0.0)
    set_bnd(0, div)
    set_bnd(0, p)
    lin_solve(0, p, div, 1, 4)
    u[1:N+1, 1:N+1] -= 0.5 * (p[2:N+2, 1:N+1] - p[0:N, 1:N+1]) / h
    v[1:N+1, 1:N+1] -= 0.5 * (p[1:N+1, 2:N+2] - p[1:N+1, 0:N]) / h
    set_bnd(1, u)
    set_bnd(2, v)

def vorticity_confinement(u, v, eps=0.002):
    """Tiny swirling force to keep curls lively, with safe indexing."""
    N = u.shape[0] - 2

    # Vorticity ω at cell centers (shape: N x N)
    w = (v[2:N+2, 1:N+1] - v[0:N, 1:N+1]
         - (u[1:N+1, 2:N+2] - u[1:N+1, 0:N])) * 0.5
    absw = np.abs(w)

    # Gradients live in (N+2 x N+2) arrays so they match u,v
    grad_x = np.zeros_like(u)
    grad_y = np.zeros_like(v)

    # Central differences (valid interior only)
    grad_x[2:N,   1:N+1] = 0.5 * (absw[2:,  :] - absw[:-2, :])   # (N-2, N)
    grad_y[1:N+1, 2:N  ] = 0.5 * (absw[:, 2:] - absw[:, :-2])   # (N, N-2)

    # One-sided diffs at the borders (keep it simple)
    grad_x[1,   1:N+1] = absw[1,  :] - absw[0,  :]
    grad_x[N+1, 1:N+1] = absw[-1, :] - absw[-2, :]
    grad_y[1:N+1, 1]   = absw[:, 1] - absw[:, 0]
    grad_y[1:N+1, N+1] = absw[:, -1] - absw[:, -2]

    mag = np.sqrt(grad_x**2 + grad_y**2) + 1e-12
    Nx = grad_x / mag
    Ny = grad_y / mag

    # Apply confinement force on the interior only (shapes match: N x N)
    u[1:N+1, 1:N+1] += eps * (Ny[1:N+1, 1:N+1] * w)
    v[1:N+1, 1:N+1] += eps * (-Nx[1:N+1, 1:N+1] * w)

    set_bnd(1, u)
    set_bnd(2, v)



class Fluid2D:
    def __init__(self, N=128, dt=0.1, diff=0.0001, visc=0.0001, vorticity=True):
        self.N = N
        self.dt = dt
        self.diff = diff
        self.visc = visc
        self.vorticity = vorticity

        shape = (N + 2, N + 2)
        Z = lambda: np.zeros(shape, dtype=np.float32)

        self.u  = Z(); self.v  = Z()
        self.u0 = Z(); self.v0 = Z()
        self.d  = Z(); self.d0 = Z()
        self.p  = Z(); self.div = Z()

    def step(self):
        # Velocity step
        add_source(self.u, self.u0, self.dt); self.u0.fill(0.0)
        add_source(self.v, self.v0, self.dt); self.v0.fill(0.0)

        diffuse(1, self.u0, self.u, self.visc, self.dt)
        diffuse(2, self.v0, self.v, self.visc, self.dt)
        self.u, self.u0 = self.u0, self.u
        self.v, self.v0 = self.v0, self.v

        project(self.u, self.v, self.p, self.div)

        advect(1, self.u0, self.u, self.u, self.v, self.dt)
        advect(2, self.v0, self.v, self.u, self.v, self.dt)
        self.u, self.u0 = self.u0, self.u
        self.v, self.v0 = self.v0, self.v

        if self.vorticity:
            vorticity_confinement(self.u, self.v)

        project(self.u, self.v, self.p, self.div)

        # Density step
        add_source(self.d, self.d0, self.dt); self.d0.fill(0.0)
        diffuse(0, self.d0, self.d, self.diff, self.dt)
        self.d, self.d0 = self.d0, self.d
        advect(0, self.d0, self.d, self.u, self.v, self.dt)
        self.d, self.d0 = self.d0, self.d

    # Add a circular "splat" of dye
    def add_density_splat(self, x, y, amount=50.0, radius=6):
        N = self.N
        cx = int(np.clip(x, 1, N))
        cy = int(np.clip(y, 1, N))
        rr = radius
        yy, xx = np.ogrid[-rr:rr+1, -rr:rr+1]
        mask = xx*xx + yy*yy <= rr*rr
        self.d0[cx-rr:cx+rr+1, cy-rr:cy+rr+1][mask] += amount

    # Add a circular impulse of velocity
    def add_velocity_splat(self, x, y, vx, vy, radius=6, strength=4.0):
        N = self.N
        cx = int(np.clip(x, 1, N))
        cy = int(np.clip(y, 1, N))
        rr = radius
        yy, xx = np.ogrid[-rr:rr+1, -rr:rr+1]
        mask = xx*xx + yy*yy <= rr*rr
        self.u0[cx-rr:cx+rr+1, cy-rr:cy+rr+1][mask] += strength * vx
        self.v0[cx-rr:cx+rr+1, cy-rr:cy+rr+1][mask] += strength * vy

    def reset(self):
        for arr in (self.u, self.v, self.u0, self.v0, self.d, self.d0, self.p, self.div):
            arr.fill(0.0)

# ------------------------- Visualization / Interaction -------------------------

def main():
    N = 128
    fluid = Fluid2D(N=N, dt=0.1, diff=1e-5, visc=1e-5, vorticity=True)

    fig, ax = plt.subplots(figsize=(6, 6))
    ax.set_title("2D Fluid Simulator — LMB: dye, RMB: velocity, R: reset")
    ax.set_xlim(0, N); ax.set_ylim(0, N)
    ax.set_aspect('equal'); ax.set_xticks([]); ax.set_yticks([])

    # We render the interior cells [1:N+1, 1:N+1]; transpose for (x,y) display
    im = ax.imshow(fluid.d[1:N+1, 1:N+1].T, origin='lower', extent=[0, N, 0, N], interpolation='bilinear')

    mouse = {"down_left": False, "down_right": False, "last": None}

    def data_to_grid(event):
        # Convert mouse (x,y) in axes coords to grid indices [1..N]
        if event.xdata is None or event.ydata is None:
            return None
        x = int(np.clip(event.xdata, 0, N-1)) + 1
        y = int(np.clip(event.ydata, 0, N-1)) + 1
        return x, y

    def on_press(event):
        if event.button == 1:
            mouse["down_left"] = True
        elif event.button == 3:
            mouse["down_right"] = True
        mouse["last"] = (event.xdata, event.ydata)

    def on_release(event):
        if event.button == 1:
            mouse["down_left"] = False
        elif event.button == 3:
            mouse["down_right"] = False
        mouse["last"] = None

    def on_motion(event):
        if not (mouse["down_left"] or mouse["down_right"]):
            return
        grid = data_to_grid(event)
        if grid is None:
            return
        x, y = grid

        # Add dye with left button
        if mouse["down_left"]:
            fluid.add_density_splat(x, y, amount=40.0, radius=5)

        # Add velocity with right button (direction = mouse delta)
        if mouse["down_right"] and mouse["last"] is not None:
            lx, ly = mouse["last"]
            if lx is not None and ly is not None and event.xdata is not None and event.ydata is not None:
                vx = (event.xdata - lx) * 2.0
                vy = (event.ydata - ly) * 2.0
                fluid.add_velocity_splat(x, y, vx=vx, vy=vy, radius=6, strength=1.0)

        mouse["last"] = (event.xdata, event.ydata)

    def on_key(event):
        if event.key.lower() == 'r':
            fluid.reset()

    fig.canvas.mpl_connect('button_press_event', on_press)
    fig.canvas.mpl_connect('button_release_event', on_release)
    fig.canvas.mpl_connect('motion_notify_event', on_motion)
    fig.canvas.mpl_connect('key_press_event', on_key)

    def update(_):
        fluid.step()
        # Update the image; transpose for (x,y)
        d = fluid.d[1:N+1, 1:N+1].T
        # Auto-scale for visibility
        im.set_data(d)
        im.set_clim(vmin=0.0, vmax=max(1e-6, d.max()))
        return (im,)

    ani = FuncAnimation(fig, update, interval=16, blit=False, cache_frame_data=False)

    plt.show()

if __name__ == "__main__":
    main()
