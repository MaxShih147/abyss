"""
Custom topology optimization solver that accepts arbitrary boundary conditions
from user-placed markers, wrapping pytopo3d internals.
"""

import time
from io import BytesIO
from typing import Callable, Optional

import numpy as np
import scipy.sparse as sp
import trimesh
from scipy.spatial import cKDTree
from skimage import measure

from pytopo3d.core.compliance import element_compliance
from pytopo3d.utils.assembly import build_edof
from pytopo3d.utils.filter import build_filter
from pytopo3d.utils.oc_update import optimality_criteria_update

# Use CHOLMOD (multi-threaded supernodal Cholesky) if available, else scipy
try:
    from sksparse.cholmod import cholesky as cholmod_cholesky
    def _solve_sparse(K, f):
        factor = cholmod_cholesky(K.tocsc())
        return factor(f)
    _solver_name = "CHOLMOD"
except ImportError:
    from scipy.sparse.linalg import spsolve as _solve_sparse
    _solver_name = "SciPy spsolve"

print(f"Abyss solver: using {_solver_name}")
from pytopo3d.utils.stiffness import lk_H8

from server.models import FixedSupportParam, LoadVectorParam


def _transform_mesh(mesh: trimesh.Trimesh) -> trimesh.Trimesh:
    """Replicate the frontend's STL transform (AbyssCanvas.vue lines 391-406):
    center at origin, uniform scale to 3.0/max_dim, shift bottom to y=0."""
    bounds = mesh.bounds  # (2, 3): min, max
    center = (bounds[0] + bounds[1]) / 2.0
    mesh.vertices -= center

    size = bounds[1] - bounds[0]
    max_dim = max(size)
    if max_dim > 0:
        scale = 3.0 / max_dim
        mesh.vertices *= scale

    # Shift bottom to y=0
    new_min_y = mesh.vertices[:, 1].min()
    mesh.vertices[:, 1] -= new_min_y
    return mesh


def prepare_optimization(
    stl_bytes: bytes,
    fixed_supports: list[FixedSupportParam],
    load_vectors: list[LoadVectorParam],
    nelx: int,
    nely: int,
    nelz: int,
) -> dict:
    """
    Prepare optimization inputs from STL + markers.

    Returns dict with: obstacle_mask, F, freedofs0, fixeddof0, grid_bounds
    """
    # 1. Load and transform mesh
    mesh = trimesh.load(BytesIO(stl_bytes), file_type="stl")
    mesh = _transform_mesh(mesh)

    bbox_min = mesh.vertices.min(axis=0)  # (x, y, z)
    bbox_max = mesh.vertices.max(axis=0)

    # Cell dimensions
    dx = (bbox_max[0] - bbox_min[0]) / nelx
    dy = (bbox_max[1] - bbox_min[1]) / nely
    dz = (bbox_max[2] - bbox_min[2]) / nelz
    pitch = min(dx, dy, dz)

    # 2. Build voxel grid and obstacle mask
    # Element centers in world coords
    # density[ey, ex, ez] — axes: y(inverted), x, z
    ex_range = np.arange(nelx)
    ey_range = np.arange(nely)
    ez_range = np.arange(nelz)

    # Grid of element centers
    ex_grid, ey_grid, ez_grid = np.meshgrid(ex_range, ey_range, ez_range, indexing="ij")
    # Shape: (nelx, nely, nelz)

    # World coords for cell centers
    # y-axis is inverted: ey=0 is top (ymax), ey=nely-1 is bottom (ymin)
    cx = bbox_min[0] + (ex_grid + 0.5) * dx
    cy = bbox_max[1] - (ey_grid + 0.5) * dy
    cz = bbox_min[2] + (ez_grid + 0.5) * dz

    centers = np.column_stack([cx.ravel(), cy.ravel(), cz.ravel()])
    inside = mesh.contains(centers)  # (nelx * nely * nelz,)
    inside_3d = inside.reshape(nelx, nely, nelz)

    # obstacle_mask needs shape (nely, nelx, nelz) to match density array
    # inside_3d is (nelx, nely, nelz), transpose to (nely, nelx, nelz)
    inside_density = inside_3d.transpose(1, 0, 2)  # (nely, nelx, nelz)
    obstacle_mask = ~inside_density

    # 3. Build node coordinate KD-tree for marker mapping
    ndof = 3 * (nelx + 1) * (nely + 1) * (nelz + 1)

    # All node positions in world coords
    ix_all, iy_all, iz_all = np.meshgrid(
        np.arange(nelx + 1), np.arange(nely + 1), np.arange(nelz + 1), indexing="ij"
    )
    # Shape: (nelx+1, nely+1, nelz+1)

    node_wx = bbox_min[0] + ix_all * dx
    node_wy = bbox_max[1] - iy_all * dy  # y inverted
    node_wz = bbox_min[2] + iz_all * dz

    node_positions = np.column_stack([
        node_wx.ravel(), node_wy.ravel(), node_wz.ravel()
    ])
    # Corresponding grid indices
    ix_flat = ix_all.ravel()
    iy_flat = iy_all.ravel()
    iz_flat = iz_all.ravel()

    tree = cKDTree(node_positions)

    # 4. Build custom force vector
    F = np.zeros(ndof)
    bc_radius = 1.5 * pitch

    for lv in load_vectors:
        marker_pos = np.array([lv.position.x, lv.position.y, lv.position.z])
        direction = np.array([lv.direction.x, lv.direction.y, lv.direction.z])
        mag = lv.magnitude

        # Find nearby nodes within bc_radius
        nearby_indices = tree.query_ball_point(marker_pos, bc_radius)
        if not nearby_indices:
            # Fallback: nearest single node
            _, nearest_idx = tree.query(marker_pos)
            nearby_indices = [nearest_idx]

        for idx in nearby_indices:
            ix, iy, iz = int(ix_flat[idx]), int(iy_flat[idx]), int(iz_flat[idx])
            # 1-based node ID
            nid = iz * (nelx + 1) * (nely + 1) + ix * (nely + 1) + (nely + 1 - iy)
            # 0-based DOFs: x = 3*nid-3, y = 3*nid-2, z = 3*nid-1
            dof_x = 3 * nid - 3
            dof_y = 3 * nid - 2
            dof_z = 3 * nid - 1
            F[dof_x] += mag * direction[0]
            F[dof_y] += mag * direction[1]
            F[dof_z] += mag * direction[2]

    # 5. Build custom supports (fixed DOFs)
    fixed_dofs = set()

    for fs in fixed_supports:
        marker_pos = np.array([fs.position.x, fs.position.y, fs.position.z])

        nearby_indices = tree.query_ball_point(marker_pos, bc_radius)
        if not nearby_indices:
            _, nearest_idx = tree.query(marker_pos)
            nearby_indices = [nearest_idx]

        for idx in nearby_indices:
            ix, iy, iz = int(ix_flat[idx]), int(iy_flat[idx]), int(iz_flat[idx])
            nid = iz * (nelx + 1) * (nely + 1) + ix * (nely + 1) + (nely + 1 - iy)
            dof_x = 3 * nid - 3
            dof_y = 3 * nid - 2
            dof_z = 3 * nid - 1
            fixed_dofs.update([dof_x, dof_y, dof_z])

    fixeddof0 = np.array(sorted(fixed_dofs), dtype=int)
    all_dofs = np.arange(ndof)
    freedofs0 = np.setdiff1d(all_dofs, fixeddof0)

    grid_bounds = {
        "bbox_min": bbox_min.tolist(),
        "bbox_max": bbox_max.tolist(),
        "dx": dx,
        "dy": dy,
        "dz": dz,
    }

    return {
        "obstacle_mask": obstacle_mask,
        "F": F,
        "freedofs0": freedofs0,
        "fixeddof0": fixeddof0,
        "grid_bounds": grid_bounds,
    }


def custom_top3d(
    nelx: int,
    nely: int,
    nelz: int,
    volfrac: float,
    penal: float,
    rmin: float,
    F: np.ndarray,
    freedofs0: np.ndarray,
    fixeddof0: np.ndarray,
    obstacle_mask: np.ndarray,
    tolx: float = 0.01,
    maxloop: int = 80,
    progress_callback: Optional[Callable] = None,
) -> np.ndarray:
    """
    Adapted topology optimization loop from pytopo3d's top3d(),
    accepting custom force vector and boundary conditions.
    """
    E0 = 1.0
    Emin = 1e-9
    nu = 0.3

    nele = nelx * nely * nelz
    ndof = 3 * (nelx + 1) * (nely + 1) * (nelz + 1)

    design_nele = nele - np.count_nonzero(obstacle_mask)

    U = np.zeros(ndof)

    # Element stiffness matrix
    KE = lk_H8(nu)
    KE_flat = KE.ravel()  # 576 values, precompute once

    # Element DOF mapping
    edofMat, iK, jK = build_edof(nelx, nely, nelz)
    iK0, jK0 = iK - 1, jK - 1

    # Filter matrix
    H, Hs = build_filter(nelx, nely, nelz, rmin)

    # Initialize design variables
    x = np.full((nely, nelx, nelz), volfrac)
    x[obstacle_mask] = 0.0
    xPhys = (H * x.ravel(order="F") / Hs).reshape((nely, nelx, nelz), order="F")

    loop = 0
    change = 1.0
    c = 0.0
    t_global_start = time.time()

    while change > tolx and loop < maxloop:
        loop += 1

        # Assemble stiffness (fast: repeat+multiply instead of kron)
        xFlat = xPhys.ravel(order="F")
        stiff_vals = Emin + (xFlat**penal) * (E0 - Emin)
        sK_full = np.repeat(stiff_vals, 576) * np.tile(KE_flat, nele)

        K = sp.csr_matrix((sK_full, (iK0, jK0)), shape=(ndof, ndof))

        # Solve
        K_ff = K[freedofs0, :][:, freedofs0]
        F_f = F[freedofs0]
        U_f = _solve_sparse(K_ff, F_f)
        U[:] = 0.0
        U[freedofs0] = U_f

        # Compliance and sensitivities
        ce_flat = element_compliance(U, edofMat, KE)
        ce = ce_flat.reshape(nely, nelx, nelz, order="F")
        c = float(((Emin + xPhys**penal * (E0 - Emin)) * ce).sum())

        dc = -penal * (E0 - Emin) * xPhys ** (penal - 1) * ce
        dv = np.ones_like(xPhys)

        # Filter sensitivities
        dc = (H * (dc.ravel(order="F") / Hs)).reshape((nely, nelx, nelz), order="F")
        dv = (H * (dv.ravel(order="F") / Hs)).reshape((nely, nelx, nelz), order="F")

        dc[obstacle_mask] = 0.0
        dv[obstacle_mask] = 0.0

        # OC update
        xnew, change = optimality_criteria_update(
            x, dc, dv, volfrac, H, Hs, nele, obstacle_mask, design_nele
        )
        xnew[obstacle_mask] = 0.0

        xPhys = (H * xnew.ravel(order="F") / Hs).reshape((nely, nelx, nelz), order="F")
        xPhys[obstacle_mask] = 0.0
        x = xnew

        current_vf = float(xPhys[~obstacle_mask].mean()) if design_nele > 0 else 0.0
        elapsed = time.time() - t_global_start

        if progress_callback:
            progress_callback(loop, c, current_vf, change, elapsed)

    return xPhys


def density_to_stl_bytes(
    xPhys: np.ndarray,
    grid_bounds: dict,
    level: float = 0.5,
    smooth_iterations: int = 5,
) -> bytes:
    """
    Convert density array to STL bytes, with vertices in frontend world coordinates.

    xPhys shape: (nely, nelx, nelz)
    grid_bounds: {bbox_min, bbox_max, dx, dy, dz}
    """
    padding = 1
    padded = np.pad(xPhys, padding, mode="constant", constant_values=0)

    vertices, faces, normals, _ = measure.marching_cubes(padded, level=level)

    # Marching cubes axes: 0=ey, 1=ex, 2=ez (matching density array layout)
    # Convert from voxel-index space to world coordinates
    bbox_min = grid_bounds["bbox_min"]
    bbox_max = grid_bounds["bbox_max"]
    dx = grid_bounds["dx"]
    dy = grid_bounds["dy"]
    dz = grid_bounds["dz"]

    ey_float = vertices[:, 0] - padding
    ex_float = vertices[:, 1] - padding
    ez_float = vertices[:, 2] - padding

    world_x = bbox_min[0] + ex_float * dx
    world_y = bbox_max[1] - ey_float * dy  # y-axis inverted
    world_z = bbox_min[2] + ez_float * dz

    vertices_world = np.column_stack([world_x, world_y, world_z])

    mesh = trimesh.Trimesh(vertices=vertices_world, faces=faces)

    # Laplacian smoothing
    if smooth_iterations > 0 and len(mesh.vertices) > 0:
        for _ in range(smooth_iterations):
            trimesh.smoothing.filter_laplacian(mesh, iterations=1, lamb=0.5)

    # Fix mesh
    if not mesh.is_watertight:
        mesh.fill_holes()
        mesh = mesh.process(validate=True)

    buf = BytesIO()
    mesh.export(buf, file_type="stl")
    return buf.getvalue()
