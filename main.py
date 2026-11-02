"""
Audio Vocal & Voice Isolator — FastAPI Application.

Provides endpoints for uploading audio, running Demucs 2-stem separation
in the background, polling task status, and streaming/downloading results.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

import anyio
from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from separator import cleanup_old_tasks, run_demucs_separation

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = BASE_DIR / "uploads"
OUTPUT_DIR = BASE_DIR / "outputs"
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"

ALLOWED_EXTENSIONS = {".mp3", ".wav", ".ogg", ".m4a"}
MAX_FILE_SIZE_MB = 200
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024

CLEANUP_INTERVAL_SECONDS = 3600  # Run cleanup every hour
CLEANUP_MAX_AGE_HOURS = 2.0

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
)
logger = logging.getLogger("app")

# ---------------------------------------------------------------------------
# In-memory task store
# ---------------------------------------------------------------------------
# task_id -> {"status": str, "original": Path | None, "result": dict | None, "error": str | None}
tasks: dict[str, dict] = {}


# ---------------------------------------------------------------------------
# Background: periodic cleanup of old uploads/outputs
# ---------------------------------------------------------------------------
async def _periodic_cleanup():
    """Remove stale upload & output folders every CLEANUP_INTERVAL_SECONDS."""
    while True:
        await asyncio.sleep(CLEANUP_INTERVAL_SECONDS)
        try:
            removed = cleanup_old_tasks(UPLOAD_DIR, OUTPUT_DIR, CLEANUP_MAX_AGE_HOURS)
            if removed:
                logger.info("Periodic cleanup removed %d old directories.", removed)
        except Exception:
            logger.exception("Error during periodic cleanup")


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown lifecycle hook."""
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    cleanup_task = asyncio.create_task(_periodic_cleanup())
    logger.info("Audio Isolator started. Uploads → %s  Outputs → %s", UPLOAD_DIR, OUTPUT_DIR)
    yield
    cleanup_task.cancel()
    logger.info("Audio Isolator shutting down.")


# ---------------------------------------------------------------------------
# App & middleware
# ---------------------------------------------------------------------------
app = FastAPI(
    title="Audio Vocal & Voice Isolator",
    version="1.0.0",
    lifespan=lifespan,
)

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


# ---------------------------------------------------------------------------
# Background separation worker
# ---------------------------------------------------------------------------
async def _process_task(task_id: str, input_path: Path):
    """Run Demucs separation and update task state."""
    task = tasks[task_id]
    task["status"] = "PROCESSING"
    task["progress"] = 0
    task["eta"] = "Hisoblanmoqda..."
    logger.info("Task %s: PROCESSING started.", task_id)

    task_output_dir = OUTPUT_DIR / task_id
    task_output_dir.mkdir(parents=True, exist_ok=True)

    def on_progress(info: dict):
        task["progress"] = info.get("progress", task.get("progress", 0))
        if info.get("eta"):
            task["eta"] = info["eta"]

    try:
        result = await run_demucs_separation(
            input_path=input_path,
            output_dir=task_output_dir,
            on_progress=on_progress,
        )
        task["result"] = result
        task["status"] = "COMPLETED"
        task["progress"] = 100
        task["eta"] = "0 soniya"
        logger.info("Task %s: COMPLETED. Results: %s", task_id, result)
    except Exception as exc:
        task["status"] = "FAILED"
        task["error"] = str(exc)
        logger.exception("Task %s: FAILED.", task_id)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Serve the main UI page."""
    return templates.TemplateResponse("index.html", {"request": request})


@app.post("/api/separate")
async def separate_audio(file: UploadFile = File(...)):
    """
    Accept an audio file upload, validate it, save it,
    and kick off background Demucs separation.
    """
    # --- Validate extension ---
    if file.filename is None:
        raise HTTPException(status_code=400, detail="Fayl nomi ko'rsatilmagan.")

    ext = Path(file.filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Noto'g'ri format: {ext}. Ruxsat etilgan: {', '.join(ALLOWED_EXTENSIONS)}",
        )

    # --- Read and validate size ---
    contents = await file.read()
    if len(contents) > MAX_FILE_SIZE_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"Fayl hajmi {MAX_FILE_SIZE_MB}MB dan oshmasligi kerak.",
        )

    # --- Save to disk ---
    task_id = uuid.uuid4().hex
    task_upload_dir = UPLOAD_DIR / task_id
    task_upload_dir.mkdir(parents=True, exist_ok=True)

    safe_filename = f"input{ext}"
    input_path = task_upload_dir / safe_filename
    input_path.write_bytes(contents)
    logger.info("Task %s: file saved (%d bytes) → %s", task_id, len(contents), input_path)

    # --- Register task & start background work ---
    tasks[task_id] = {
        "status": "QUEUED",
        "original": input_path,
        "result": None,
        "error": None,
    }
    asyncio.create_task(_process_task(task_id, input_path))

    return JSONResponse(
        content={"task_id": task_id, "status": "QUEUED"},
        status_code=202,
    )


@app.get("/api/status/{task_id}")
async def task_status(task_id: str):
    """Return the current status of a separation task."""
    task = tasks.get(task_id)
    if task is None:
        # Check disk fallback if server was reloaded
        out_task_dir = OUTPUT_DIR / task_id
        if out_task_dir.exists():
            v_files = list(out_task_dir.rglob("vocals.*"))
            nv_files = list(out_task_dir.rglob("no_vocals.*"))
            if v_files and nv_files:
                return JSONResponse(
                    content={
                        "task_id": task_id,
                        "status": "COMPLETED",
                        "progress": 100,
                        "eta": "0 soniya",
                        "tracks": {
                            "vocals": f"/api/audio/{task_id}/vocals",
                            "no_vocals": f"/api/audio/{task_id}/no_vocals",
                        },
                        "original": f"/api/audio/{task_id}/original",
                    }
                )
        raise HTTPException(status_code=404, detail="Task topilmadi.")

    payload: dict = {
        "task_id": task_id,
        "status": task["status"],
        "progress": task.get("progress", 0),
        "eta": task.get("eta", "Hisoblanmoqda..."),
    }

    if task["status"] == "COMPLETED" and task["result"]:
        payload["tracks"] = {
            track: f"/api/audio/{task_id}/{track}"
            for track in task["result"]
        }
        payload["original"] = f"/api/audio/{task_id}/original"

    if task["status"] == "FAILED":
        payload["error"] = task.get("error", "Noma'lum xatolik.")

    return JSONResponse(content=payload)


def _parse_byte_range(range_header: str | None, file_size: int) -> tuple[int, int] | bool | None:
    """
    Parse HTTP Range header (e.g. 'bytes=1000-2000' or 'bytes=1000-').
    Returns:
      (start, end) if valid range
      False if unsatisfiable (416)
      None if no range header
    """
    if not range_header or not range_header.startswith("bytes="):
        return None
    range_str = range_header.replace("bytes=", "").strip()
    parts = range_str.split("-")
    if len(parts) != 2:
        return None
    start_str, end_str = parts[0].strip(), parts[1].strip()

    try:
        if start_str and end_str:
            start = int(start_str)
            end = int(end_str)
        elif start_str and not end_str:
            start = int(start_str)
            end = file_size - 1
        elif not start_str and end_str:
            suffix_len = int(end_str)
            start = max(0, file_size - suffix_len)
            end = file_size - 1
        else:
            return None
    except ValueError:
        return None

    if start > end or start >= file_size or start < 0:
        return False
    end = min(end, file_size - 1)
    return (start, end)


async def _stream_file(file_path: Path, start: int, end: int, chunk_size: int = 64 * 1024):
    """Asynchronously yield byte slices of a file."""
    async with await anyio.open_file(file_path, mode="rb") as f:
        await f.seek(start)
        bytes_left = end - start + 1
        while bytes_left > 0:
            to_read = min(chunk_size, bytes_left)
            data = await f.read(to_read)
            if not data:
                break
            bytes_left -= len(data)
            yield data


@app.api_route("/api/audio/{task_id}/{track_type}", methods=["GET", "HEAD"])
async def get_audio(
    request: Request,
    task_id: str,
    track_type: str,
    download: bool = False,
):
    """
    Stream or download an audio track with full HTTP Range request (seeking) support.
    """
    task = tasks.get(task_id)
    file_path = None

    if task:
        if track_type == "original":
            file_path = task.get("original")
        elif task.get("result") and track_type in task["result"]:
            file_path = task["result"][track_type]

    # Disk fallback if task is not in memory
    if file_path is None or not Path(file_path).exists():
        if track_type == "original":
            upload_dir = UPLOAD_DIR / task_id
            if upload_dir.exists():
                for f in upload_dir.iterdir():
                    if f.is_file() and f.stem.startswith("input"):
                        file_path = f
                        break
        else:
            out_task_dir = OUTPUT_DIR / task_id
            if out_task_dir.exists():
                for f in out_task_dir.rglob(f"{track_type}.*"):
                    if f.is_file():
                        file_path = f
                        break

    if file_path is None or not Path(file_path).exists():
        raise HTTPException(status_code=404, detail="Fayl topilmadi.")

    file_path = Path(file_path)
    file_size = file_path.stat().st_size
    media_type = _media_type(file_path.suffix)
    safe_filename = f"{track_type}{file_path.suffix}"

    # Handle HEAD requests (used by browsers to inspect capabilities)
    if request.method.upper() == "HEAD":
        return Response(
            status_code=200,
            headers={
                "Accept-Ranges": "bytes",
                "Content-Length": str(file_size),
                "Content-Type": media_type,
            },
        )

    # Check Range header
    range_header = request.headers.get("range")
    range_result = _parse_byte_range(range_header, file_size)

    if range_result is False:
        # 416 Range Not Satisfiable
        return Response(
            status_code=416,
            headers={
                "Content-Range": f"bytes */{file_size}",
                "Accept-Ranges": "bytes",
            },
        )

    if range_result is not None:
        # 206 Partial Content (Seek forward/backward)
        start, end = range_result
        headers = {
            "Content-Range": f"bytes {start}-{end}/{file_size}",
            "Accept-Ranges": "bytes",
            "Content-Length": str(end - start + 1),
            "Content-Type": media_type,
        }
        if download:
            headers["Content-Disposition"] = f'attachment; filename="{safe_filename}"'
        else:
            headers["Content-Disposition"] = "inline"

        return StreamingResponse(
            _stream_file(file_path, start, end),
            status_code=206,
            headers=headers,
        )

    # 200 OK — full stream
    headers = {
        "Accept-Ranges": "bytes",
        "Content-Length": str(file_size),
        "Content-Type": media_type,
    }
    if download:
        headers["Content-Disposition"] = f'attachment; filename="{safe_filename}"'
    else:
        headers["Content-Disposition"] = "inline"

    return StreamingResponse(
        _stream_file(file_path, 0, file_size - 1),
        status_code=200,
        headers=headers,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _media_type(ext: str) -> str:
    return {
        ".mp3": "audio/mpeg",
        ".wav": "audio/wav",
        ".ogg": "audio/ogg",
        ".m4a": "audio/mp4",
        ".flac": "audio/flac",
    }.get(ext.lower(), "application/octet-stream")
