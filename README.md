# Abyss — 3D Topology Optimization Visualizer

Cthulhu-themed interactive 3D topology optimization tool. Upload STL models, place boundary conditions via point-and-click markers, run SIMP optimization, and visualize results — all in the browser.

- **Frontend:** Vue 3 + Three.js (procedural stone idol shader, SSAO, bloom, outline)
- **Backend:** FastAPI + PyTopo3D (SIMP solver with CHOLMOD)

---

## PyTopo3D API Reference

### Installed Version (v0.1.0) — Hardcoded BCs

v0.1.0 has **no** custom boundary condition parameters. Forces and supports are hardcoded:

| Function | Default Behavior |
|----------|-----------------|
| `build_force_vector(nelx, nely, nelz, ndof)` | Unit downward load (Fy=-1) along bottom edge of right face |
| `build_supports(nelx, nely, nelz, ndof)` | Left face fully clamped (all 3 DOFs fixed) |

### GitHub Latest — Custom BC Support

#### `top3d()` Main Optimizer

```python
top3d(
    nelx: int,                    # Elements in x direction
    nely: int,                    # Elements in y direction
    nelz: int,                    # Elements in z direction
    volfrac: float,               # Volume fraction target (0.0-1.0)
    penal: float,                 # SIMP penalization exponent (typically 3.0)
    rmin: float,                  # Filter radius for sensitivity filtering
    disp_thres: float,            # Display threshold for visualization
    obstacle_mask=None,           # bool (nely, nelx, nelz) — True = void/obstacle
    force_field=None,             # float (nely, nelx, nelz, 3) — [Fx,Fy,Fz] per element
    support_mask=None,            # bool (nely, nelx, nelz) — True = fixed support
    tolx=0.01,                    # Convergence tolerance
    maxloop=2000,                 # Max iterations
    save_history=False,           # Save density snapshots
    history_frequency=10,         # Save every N iterations
    use_gpu=False,                # CuPy GPU acceleration
)
```

**Returns:**
- `save_history=False`: `np.ndarray` — optimized density `(nely, nelx, nelz)`
- `save_history=True`: `Tuple[np.ndarray, Dict]` — `(density, history_dict)`

#### `force_field` — External Forces

Shape: `(nely, nelx, nelz, 3)` — each element gets `[Fx, Fy, Fz]`, distributed equally to its 8 corner nodes.

```python
# Point load at a single element
force_field = np.zeros((nely, nelx, nelz, 3))
force_field[15, 59, 10, 1] = -1.0         # Fy=-1 at element (y=15, x=59, z=10)

# Distributed load along an edge
force_field[nely-1, nelx-1, :, 1] = -1.0  # Fy=-1 along right face bottom edge

# Gravity (body force)
force_field[:, :, :, 1] = -9.81           # Fy=-9.81 on all elements
```

#### `support_mask` — Boundary Constraints

Shape: `(nely, nelx, nelz)`, dtype `bool`. All 8 corner nodes of `True` elements get 3DOF fixed (full clamp).

```python
# Fix left face
support_mask = np.zeros((nely, nelx, nelz), dtype=bool)
support_mask[:, 0, :] = True

# Fix two corner edges
support_mask[:, 0, 0] = True
support_mask[:, 0, -1] = True
```

> **Limitation:** Always full clamp (3DOF fixed). No roller (1-2 DOF) support.

---

### Obstacle API

```python
create_cube_obstacle(shape, center, size)
create_sphere_obstacle(shape, center, radius)
create_cylinder_obstacle(shape, center, radius, height, axis=2)
```

- `shape`: `(nely, nelx, nelz)`
- `center`: `(x, y, z)` as fractions 0.0-1.0 of domain
- `size` / `radius` / `height`: fractions of domain dimension

JSON config format:

```json
{
  "obstacles": [
    { "type": "cube", "center": [0.5, 0.5, 0.2], "size": 0.15 },
    { "type": "sphere", "center": [0.25, 0.25, 0.6], "radius": 0.1 },
    { "type": "cylinder", "center": [0.75, 0.5, 0.5], "radius": 0.08, "height": 0.7, "axis": 2 },
    { "type": "cube", "center": [0.25, 0.75, 0.5], "size": [0.15, 0.05, 0.3] }
  ]
}
```

---

### Project Custom Solver (`server/solver.py`)

Bypasses pytopo3d defaults entirely. Uses world-coordinate markers from the 3D UI.

#### Fixed Support — `FixedSupportParam`

```python
{ "position": Vec3, "normal": Vec3 }
```

- KD-tree finds all nodes within `1.5 * pitch` radius
- All 3 DOFs fixed (full clamp)
- `normal` field is present but **not currently used**

#### Load Vector — `LoadVectorParam`

```python
{ "position": Vec3, "direction": Vec3, "magnitude": float = 1.0 }
```

- KD-tree finds nearby nodes
- Applies `magnitude * direction` to 3 DOFs of each node
- Falls back to nearest single node if none within radius

#### `custom_top3d()` — Custom Optimization Loop

```python
custom_top3d(
    nelx, nely, nelz,
    volfrac, penal, rmin,
    F: np.ndarray,              # Pre-built force vector
    freedofs0: np.ndarray,      # Pre-built free DOF indices
    fixeddof0: np.ndarray,      # Pre-built fixed DOF indices
    obstacle_mask: np.ndarray,  # Pre-built obstacle mask
    tolx=0.01,
    maxloop=80,
    progress_callback=None,
)
```

---

### Material & Solver Constants

| Parameter | Value | Description |
|-----------|-------|-------------|
| `E0` | `1.0` | Young's modulus (solid) |
| `Emin` | `1e-9` | Young's modulus (void) |
| `nu` | `0.3` | Poisson's ratio |

**Solver priority:** CHOLMOD (scikit-sparse) > PyPardiso > SciPy spsolve

---

### Not Supported by PyTopo3D

| Feature | Status | Workaround |
|---------|--------|------------|
| Roller supports (1-2 DOF) | Not supported | Manually build DOF arrays |
| Pin joints | Not supported | Manual DOF arrays |
| Moment loads | Not supported | Approximate with force couples |
| Pressure loads (surface normal) | Not supported | Use `force_field` with normal vectors |
| Thermal loads | Not supported | Structural only |
| Dynamic / time-varying loads | Not supported | Static only |
| Multiple load cases | Not supported | Run separate optimizations |
| Non-zero displacement BCs | Not supported | All fixed DOFs = zero displacement |
| Spring supports | Not supported | Would require stiffness matrix modification |
