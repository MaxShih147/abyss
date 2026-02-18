"""
FastAPI backend for Abyss topology optimization.
"""

import asyncio
import json
import uuid
from dataclasses import dataclass, field
from typing import Optional

from fastapi import FastAPI, File, Form, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, StreamingResponse

from server.models import OptimizationParams, ProgressUpdate
from server.solver import custom_top3d, density_to_stl_bytes, prepare_optimization

app = FastAPI(title="Abyss Topology Optimization")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:5174"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@dataclass
class Job:
    job_id: str
    status: str = "running"  # running | complete | error
    progress: list[ProgressUpdate] = field(default_factory=list)
    result_stl: Optional[bytes] = None
    error_message: Optional[str] = None


# In-memory job store
jobs: dict[str, Job] = {}


def run_optimization_job(job: Job, stl_bytes: bytes, params: OptimizationParams):
    """Run optimization synchronously (called via asyncio.to_thread)."""
    try:
        prep = prepare_optimization(
            stl_bytes=stl_bytes,
            fixed_supports=params.fixed_supports,
            load_vectors=params.load_vectors,
            nelx=params.nelx,
            nely=params.nely,
            nelz=params.nelz,
        )

        def on_progress(iteration, objective, volfrac, change, elapsed):
            job.progress.append(ProgressUpdate(
                iteration=iteration,
                max_iterations=params.max_iterations,
                objective=round(objective, 6),
                volume_fraction=round(volfrac, 4),
                change=round(change, 6),
                elapsed_seconds=round(elapsed, 2),
            ))

        xPhys = custom_top3d(
            nelx=params.nelx,
            nely=params.nely,
            nelz=params.nelz,
            volfrac=params.volume_fraction,
            penal=params.penal,
            rmin=params.rmin,
            F=prep["F"],
            freedofs0=prep["freedofs0"],
            fixeddof0=prep["fixeddof0"],
            obstacle_mask=prep["obstacle_mask"],
            tolx=params.tolx,
            maxloop=params.max_iterations,
            progress_callback=on_progress,
        )

        result_bytes = density_to_stl_bytes(xPhys, prep["grid_bounds"])
        job.result_stl = result_bytes
        job.status = "complete"

    except Exception as e:
        job.status = "error"
        job.error_message = str(e)


@app.post("/api/optimize")
async def start_optimization(
    stl_file: UploadFile = File(...),
    params: str = Form(...),
):
    """Accept multipart form with STL file + JSON params string."""
    parsed_params = OptimizationParams(**json.loads(params))
    stl_bytes = await stl_file.read()

    job_id = str(uuid.uuid4())
    job = Job(job_id=job_id)
    jobs[job_id] = job

    asyncio.get_event_loop().run_in_executor(
        None, run_optimization_job, job, stl_bytes, parsed_params
    )

    return {"job_id": job_id}


@app.get("/api/optimize/{job_id}/progress")
async def stream_progress(job_id: str):
    """SSE stream of optimization progress."""
    job = jobs.get(job_id)
    if not job:
        return Response(status_code=404, content="Job not found")

    async def event_generator():
        sent_count = 0
        while True:
            # Send any new progress updates
            while sent_count < len(job.progress):
                update = job.progress[sent_count]
                yield f"data: {update.model_dump_json()}\n\n"
                sent_count += 1

            if job.status == "complete":
                yield f'data: {{"status": "complete"}}\n\n'
                return
            elif job.status == "error":
                msg = json.dumps({"status": "error", "message": job.error_message or "Unknown error"})
                yield f"data: {msg}\n\n"
                return

            await asyncio.sleep(0.5)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/api/optimize/{job_id}/result")
async def get_result(job_id: str):
    """Download result STL binary."""
    job = jobs.get(job_id)
    if not job:
        return Response(status_code=404, content="Job not found")
    if job.status != "complete" or job.result_stl is None:
        return Response(status_code=409, content="Result not ready")

    return Response(
        content=job.result_stl,
        media_type="application/octet-stream",
        headers={"Content-Disposition": "attachment; filename=optimized.stl"},
    )
