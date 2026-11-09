"""Lens backend: FastAPI app.

Run:  uv run uvicorn app.main:app --host 0.0.0.0 --port 8000
"""

import asyncio
import collections
import json
import logging
import shutil
import subprocess
import tempfile
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path

from fastapi import Body, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

from . import agent, debug, kb, sources, travel
from .config import settings
from .db import DB
from .extract import dhash, extract, hamming
from .query import answer
from .schemas import QueryRequest, QueryResponse

log = logging.getLogger("lens")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

db = DB(settings.db_path)
agent.attach_db(db)


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
# Capture timestamps of frames waiting for extraction, oldest first (for lag reporting).
pending: collections.deque[float] = collections.deque()
stats = {"received": 0, "deduped": 0, "processed": 0, "failed": 0, "dropped": 0, "ignored": 0}


def backlog() -> dict:
    """How far indexing is behind the phone. Shared with /health and the query context."""
    now = time.time()
    return {"frames_pending": len(pending), "behind_s": round(now - pending[0], 1) if pending else 0.0}


def process(job: Job) -> bool:
    """Returns False if extraction failed."""
    state = devices.setdefault(job.device, DeviceState())
    if job.jpeg is None:
        kb.extend_dwell(db, state.last_touched, job.ts)
        debug.duplicate(job.ts, state.last_touched)
        return True

    behind_s = time.time() - job.ts
    result = extract(db, job.jpeg, behind_s=behind_s)
    obs = result.obs
    touched: list[int] = []
    ignored_reason = None
    if obs is not None:
        db.execute(
            "INSERT INTO frames(ts, device, dhash, app, screen_kind, sensitive, extractor, observation) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (job.ts, job.device, job.hash, obs.app, obs.screen_kind, int(obs.sensitive), result.label,
             None if obs.sensitive else obs.model_dump_json()),
        )
        ignored_reason = kb.blocked_reason(obs.app)
        if ignored_reason:
            stats["ignored"] += 1
        touched = kb.record_observation(db, obs, job.ts)
    # Dwell from following duplicate frames goes to what this frame showed (nothing, if it failed).
    state.last_touched = touched
    debug.frame(db, ts=job.ts, device=job.device, jpeg=job.jpeg, result=result, touched=touched,
                ignored_reason=ignored_reason, behind_s=behind_s)
    log.info("frame %s %s -> %s items, %d indexed (%s, %dms, %.0fs behind)", job.device,
             obs.app if obs else "FAILED", len(obs.items) if obs else 0, len(touched), result.label, result.ms, behind_s)
    return obs is not None


async def worker() -> None:
    # One worker: frames are processed in order so dwell time accumulates correctly,
    # and a laptop GPU is only running one vision call at a time anyway.
    while True:
        job = await queue.get()
        try:
            ok = await asyncio.to_thread(process, job)
            if job.jpeg is not None:
                stats["processed" if ok else "failed"] += 1
        except Exception:  # noqa: BLE001
            stats["failed"] += 1
            log.exception("frame processing failed")
        finally:
            if job.jpeg is not None and pending:
                pending.popleft()
            queue.task_done()


@asynccontextmanager
async def lifespan(_: FastAPI):
    task = asyncio.create_task(worker())
    log.info("Lens backend up. extractor=%s cloud_fallback=%s cloud_burst_lag=%ss debug=%s db=%s",
             settings.extractor, settings.cloud_fallback, settings.cloud_burst_lag_s,
             settings.debug_dir if settings.debug_dump else "off", settings.db_path)
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
        if not duplicate:
            pending.append(ts)
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
            "queue": queue.qsize(), **backlog(), **stats}


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
        result, route = answer(db, req.text, backlog())
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


# ---------------------------------------------------------------- OpenUI agent (trip planning + booking)


class ChatMessage(BaseModel):
    role: str  # "user" | "assistant"
    content: str


class ChatRequest(BaseModel):
    messages: list[ChatMessage]
    effort: str = "low"


@app.post("/agent/chat")
def agent_chat(req: ChatRequest) -> StreamingResponse:
    """Streams an OpenUI Lang answer as Server-Sent Events (see app/agent.py for the event types)."""
    msgs = [m.model_dump() for m in req.messages]

    def sse():
        for event in agent.stream(msgs, effort=req.effort):
            yield f"data: {json.dumps(event)}\n\n"

    return StreamingResponse(sse(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.post("/tools/{name}")
def call_tool(name: str, args: dict = Body(default_factory=dict)):
    """Query()/Mutation() calls from the generated UI. Errors come back as 400 {error}."""
    try:
        return agent.run_ui_tool(name, args)
    except travel.TravelError as e:
        log.info("tool %s failed: %s", name, e)
        return JSONResponse({"error": str(e)}, status_code=400)



# ---------------------------------------------------------------- screen memory sources


@app.get("/settings/sources")
def get_sources() -> list[dict]:
    return sources.get_sources()


@app.post("/settings/sources")
def set_sources(changes: dict[str, bool] = Body(...)) -> list[dict]:
    """Body: {"instagram": true, "messages": false, ...}. Switching a source off also forgets it."""
    result = sources.set_sources(changes)
    for key, enabled in changes.items():
        if not enabled:
            n = kb.forget_source(db, key)
            log.info("source %s switched off: forgot %d saved items", key, n)
    return result
