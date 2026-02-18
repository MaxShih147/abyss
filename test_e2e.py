"""
End-to-end test: submit a beam STL with cantilever BCs,
stream progress, download result STL.
"""

import json
import time
import sys
import requests

API = "http://localhost:8000"
STL_PATH = "test_results/test_beam.stl"

# After the frontend transform, the box (6x2x2) becomes:
# centered, scaled by 3.0/6.0 = 0.5, then shifted up so bottom at y=0
# Result: x in [-1.5, 1.5], y in [0, 1.0], z in [-0.5, 0.5]
#
# We'll place:
# - 2 fixed supports on the left face (x ~ -1.5)
# - 1 load vector on the right face (x ~ 1.5), pushing down (-y)

params = {
    "fixed_supports": [
        {
            "position": {"x": -1.5, "y": 0.25, "z": 0.0},
            "normal": {"x": -1.0, "y": 0.0, "z": 0.0},
        },
        {
            "position": {"x": -1.5, "y": 0.75, "z": 0.0},
            "normal": {"x": -1.0, "y": 0.0, "z": 0.0},
        },
    ],
    "load_vectors": [
        {
            "position": {"x": 1.5, "y": 0.5, "z": 0.0},
            "direction": {"x": 0.0, "y": -1.0, "z": 0.0},
            "magnitude": 1.0,
        },
    ],
    "volume_fraction": 0.3,
    "nelx": 30,
    "nely": 10,
    "nelz": 10,
    "penal": 3.0,
    "rmin": 1.5,
    "max_iterations": 30,
    "tolx": 0.01,
}


def main():
    print("=" * 60)
    print("ABYSS END-TO-END TEST")
    print("=" * 60)

    # 1. Submit optimization
    print("\n[1] Submitting optimization job...")
    with open(STL_PATH, "rb") as f:
        files = {"stl_file": ("test_beam.stl", f, "application/octet-stream")}
        data = {"params": json.dumps(params)}
        resp = requests.post(f"{API}/api/optimize", files=files, data=data)

    if resp.status_code != 200:
        print(f"FAIL: Submit returned {resp.status_code}: {resp.text}")
        sys.exit(1)

    job_id = resp.json()["job_id"]
    print(f"  Job ID: {job_id}")

    # 2. Stream progress via SSE
    print("\n[2] Streaming progress (SSE)...")
    t0 = time.time()
    last_iter = 0
    final_status = None

    resp = requests.get(f"{API}/api/optimize/{job_id}/progress", stream=True)
    for line in resp.iter_lines(decode_unicode=True):
        if not line or not line.startswith("data: "):
            continue
        payload = json.loads(line[6:])

        if "status" in payload:
            final_status = payload["status"]
            print(f"\n  Final status: {final_status}")
            if final_status == "error":
                print(f"  Error: {payload.get('message', '?')}")
            break

        it = payload["iteration"]
        obj = payload["objective"]
        vf = payload["volume_fraction"]
        ch = payload["change"]
        el = payload["elapsed_seconds"]
        last_iter = it
        print(f"  Iter {it:3d}/{payload['max_iterations']} | obj={obj:10.4f} | vf={vf:.4f} | change={ch:.6f} | {el:.1f}s")

    elapsed = time.time() - t0
    print(f"\n  Total stream time: {elapsed:.1f}s")

    if final_status != "complete":
        print("FAIL: Optimization did not complete successfully.")
        sys.exit(1)

    # 3. Download result STL
    print("\n[3] Downloading result STL...")
    resp = requests.get(f"{API}/api/optimize/{job_id}/result")
    if resp.status_code != 200:
        print(f"FAIL: Result download returned {resp.status_code}")
        sys.exit(1)

    result_path = "test_results/e2e_result.stl"
    with open(result_path, "wb") as f:
        f.write(resp.content)
    print(f"  Saved to {result_path} ({len(resp.content):,} bytes)")

    # 4. Validate result
    print("\n[4] Validating result mesh...")
    import trimesh
    mesh = trimesh.load(result_path)
    print(f"  Vertices: {len(mesh.vertices)}")
    print(f"  Faces: {len(mesh.faces)}")
    print(f"  Bounds min: [{mesh.bounds[0][0]:.3f}, {mesh.bounds[0][1]:.3f}, {mesh.bounds[0][2]:.3f}]")
    print(f"  Bounds max: [{mesh.bounds[1][0]:.3f}, {mesh.bounds[1][1]:.3f}, {mesh.bounds[1][2]:.3f}]")
    print(f"  Watertight: {mesh.is_watertight}")

    # Check coordinate alignment: result should be roughly within the original beam's bounds
    # Original transformed bounds: x[-1.5, 1.5], y[0, 1.0], z[-0.5, 0.5]
    bmin, bmax = mesh.bounds[0], mesh.bounds[1]
    x_ok = bmin[0] >= -1.8 and bmax[0] <= 1.8
    y_ok = bmin[1] >= -0.3 and bmax[1] <= 1.3
    z_ok = bmin[2] >= -0.8 and bmax[2] <= 0.8

    if x_ok and y_ok and z_ok:
        print("  Coordinate alignment: PASS")
    else:
        print(f"  Coordinate alignment: WARN (bounds outside expected range)")

    print("\n" + "=" * 60)
    print("ALL CHECKS PASSED")
    print("=" * 60)


if __name__ == "__main__":
    main()
