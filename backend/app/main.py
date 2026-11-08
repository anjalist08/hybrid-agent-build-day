"""Lens backend: FastAPI app.

Run:  uv run uvicorn app.main:app --host 0.0.0.0 --port 8000
"""

import asyncio
import logging
import shutil
import subprocess
import tempfile
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile

from . import kb
from .config import settings
from .db import DB
from .extract import dhash, extract, hamming
from .query import answer
from .schemas import QueryRequest, QueryResponse

log = logging.getLogger("lens")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

db = DB(settings.db_path)


@dataclass
class DeviceState:
    last_hash: str | None = None
    last_touched: list[int] = field(default_factory=list)


@dataclass
class Job:
    jpeg: bytes | None  # None = duplicate frame: only extend dwell, in queue order
    ts: float
    device: str
    hash: str


devices: dict[str, DeviceState] = {}
queue: asyncio.Queue[Job] = asyncio.Queue(maxsize=200)
stats = {"received": 0, "deduped": 0, "processed": 0, "failed": 0, "dropped": 0}


def process(job: Job) -> None:
    state = devices.setdefault(job.device, DeviceState())
    if job.jpeg is None:
        kb.extend_dwell(db, state.last_touched, job.ts)
        return
    obs, extractor = extract(db, job.jpeg)
    db.execute(
        "INSERT INTO frames(ts, device, dhash, app, screen_kind, sensitive, extractor, observation) VALUES (?,?,?,?,?,?,?,?)",
        (job.ts, job.device, job.hash, obs.app, obs.screen_kind, int(obs.sensitive), extractor,
         None if obs.sensitive else obs.model_dump_json()),
    )
    touched = kb.record_observation(db, obs, job.ts)
    state.last_touched = touched
    if settings.save_frames and not obs.sensitive:
        settings.frames_dir.mkdir(parents=True, exist_ok=True)
        (settings.frames_dir / f"{job.device}-{job.ts:.0f}.jpg").write_bytes(job.jpeg)
    log.info("frame %s %s -> %s items (%s)", job.device, obs.app, len(obs.items), extractor)


async def worker() -> None:
    # One worker: frames are processed in order so dwell time accumulates correctly,
    # and a laptop GPU is only running one vision call at a time anyway.
    while True:
        job = await queue.get()
        try:
            await asyncio.to_thread(process, job)
            if job.jpeg is not None:
                stats["processed"] += 1
        except Exception:  # noqa: BLE001
            stats["failed"] += 1
            log.exception("frame processing failed")
        finally:
            queue.task_done()


@asynccontextmanager
async def lifespan(_: FastAPI):
    task = asyncio.create_task(worker())
    log.info("Lens backend up. extractor=%s cloud_fallback=%s db=%s", settings.extractor, settings.cloud_fallback,
             settings.db_path)
    yield
    task.cancel()


app = FastAPI(title="Lens", lifespan=lifespan)


def enqueue(jpeg: bytes, ts: float, device: str) -> str:
    stats["received"] += 1
    h = dhash(jpeg)
    state = devices.setdefault(device, DeviceState())
    duplicate = state.last_hash is not None and hamming(h, state.last_hash) <= settings.dedup_bits
    if not duplicate:
        state.last_hash = h
    try:
        # Duplicates skip the vision call but still go through the queue, so dwell is
        # credited after the original frame has been extracted.
        queue.put_nowait(Job(None if duplicate else jpeg, ts, device, h))
    except asyncio.QueueFull:
        stats["dropped"] += 1
        return "dropped"
    if duplicate:
        stats["deduped"] += 1
        return "duplicate"
    return "queued"


@app.get("/health")
def health() -> dict:
    return {"ok": True, "extractor": settings.extractor, "cloud_fallback": settings.cloud_fallback,
            "queue": queue.qsize(), **stats}


@app.post("/ingest/frame", status_code=202)
async def ingest_frame(
    frame: UploadFile = File(...),
    ts: float | None = Form(None),
    device: str = Form("iphone"),
) -> dict:
    jpeg = await frame.read()
    if not jpeg:
        raise HTTPException(400, "empty frame")
    return {"status": enqueue(jpeg, ts or time.time(), device)}


@app.post("/ingest/video", status_code=202)
async def ingest_video(
    video: UploadFile = File(...),
    every_s: float = Form(3.0),
    device: str = Form("video-upload"),
) -> dict:
    """Demo fallback: upload an iPhone screen recording; frames are sampled with ffmpeg."""
    if not shutil.which("ffmpeg"):
        raise HTTPException(500, "ffmpeg not installed")
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "in.mp4"
        src.write_bytes(await video.read())
        subprocess.run(
            ["ffmpeg", "-loglevel", "error", "-i", str(src), "-vf", f"fps=1/{every_s},scale=-2:1280",
             "-q:v", "4", str(Path(tmp) / "f_%05d.jpg")],
            check=True,
        )
        frames = sorted(Path(tmp).glob("f_*.jpg"))
        start = time.time() - len(frames) * every_s
        results = [enqueue(f.read_bytes(), start + i * every_s, device) for i, f in enumerate(frames)]
    return {"frames": len(frames), "queued": results.count("queued"), "duplicates": results.count("duplicate")}


@app.post("/query", response_model=QueryResponse)
def query(req: QueryRequest) -> QueryResponse:
    if not req.text.strip():
        raise HTTPException(400, "empty question")
    try:
        result, route = answer(db, req.text)
    except Exception as e:  # noqa: BLE001
        log.exception("query failed")
        raise HTTPException(502, f"query failed: {e}") from e
    route["transcript_source"] = req.source
    return QueryResponse(answer=result, route=route)


@app.get("/impressions")
def impressions(limit: int = 50) -> list[dict]:
    return db.query("SELECT * FROM impressions ORDER BY ts_end DESC LIMIT ?", (limit,))


@app.get("/interests")
def get_interests(type: str | None = None, limit: int = 20) -> list[dict]:
    return kb.interests(db, type, limit)


@app.get("/routes")
def routes(limit: int = 30) -> list[dict]:
    return db.query("SELECT * FROM route_log ORDER BY ts DESC LIMIT ?", (limit,))


@app.delete("/data")
def wipe() -> dict:
    db.wipe()
    devices.clear()
    return {"ok": True}
