"""
Audio separation engine using Meta's Demucs.
Runs Demucs CLI in a subprocess to avoid blocking the event loop.
"""

from __future__ import annotations

import asyncio
import logging
import shutil
import subprocess
import sys
from pathlib import Path

logger = logging.getLogger("separator")


def get_optimal_device() -> str:
    """Detect the best acceleration device available (CUDA, Apple Silicon MPS, or CPU)."""
    try:
        import torch
        if torch.cuda.is_available():
            return "cuda"
        if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            return "mps"
    except Exception:
        pass
    return "cpu"


from typing import Callable
import re

def parse_tqdm(text: str) -> tuple[int | None, str | None, str | None]:
    """Parse percentage and ETA from a tqdm progress string."""
    pct_match = re.search(r'(\d{1,3})%', text)
    eta_match = re.search(r'<([0-9:]+)', text)

    pct = int(pct_match.group(1)) if pct_match else None
    eta_raw = eta_match.group(1) if eta_match else None

    eta_human = None
    if eta_raw:
        parts = eta_raw.split(':')
        if len(parts) == 2:
            m, s = int(parts[0]), int(parts[1])
            if m > 0:
                eta_human = f"{m} daqiqa {s} soniya"
            else:
                eta_human = f"{s} soniya"
        elif len(parts) == 3:
            h, m, s = int(parts[0]), int(parts[1]), int(parts[2])
            eta_human = f"{h} soat {m} daqiqa"

    return pct, eta_raw, eta_human


async def run_demucs_separation(
    input_path: Path,
    output_dir: Path,
    model: str = "htdemucs",
    two_stems: str = "vocals",
    shifts: int = 1,
    overlap: float = 0.1,
    jobs: int = 4,
    on_progress: Callable[[dict], None] | None = None,
) -> dict[str, Path]:
    """
    Run Demucs 2-stem separation (vocals vs. no_vocals) asynchronously with GPU acceleration.

    Args:
        input_path: Path to the uploaded audio file.
        output_dir: Directory where Demucs will write its output.
        model: Demucs model name (default: htdemucs).
        two_stems: Which stem to isolate (default: vocals).
        shifts: Number of random shifts (1 for fast high-quality).
        overlap: Overlap between splits (0.1 for maximum speed).
        jobs: Parallel worker jobs.
        on_progress: Callback invoked with {"progress": int, "eta": str, "eta_raw": str}.

    Returns:
        Dictionary mapping track type to its output file path.

    Raises:
        RuntimeError: If Demucs process fails.
    """
    device = get_optimal_device()
    cmd = [
        sys.executable,
        "-m",
        "demucs.separate",
        "--two-stems",
        two_stems,
        "-n",
        model,
        "-d",
        device,
        "--shifts",
        str(shifts),
        "--overlap",
        str(overlap),
        "-j",
        str(jobs),
        "-o",
        str(output_dir),
        "--mp3",  # Output as MP3 to save space
        str(input_path),
    ]

    logger.info("Starting Demucs [device=%s, shifts=%d, overlap=%.2f]: %s", device, shifts, overlap, " ".join(cmd))

    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.PIPE,
    )

    buf = b""
    stderr_chunks = []
    last_pct = -1

    while True:
        chunk = await process.stderr.read(64)
        if not chunk:
            break
        stderr_chunks.append(chunk)
        buf += chunk
        parts = re.split(b"[\r\n]+", buf)
        buf = parts[-1]
        for line_bytes in parts[:-1]:
            line_str = line_bytes.decode("utf-8", errors="ignore").strip()
            pct, eta_raw, eta_human = parse_tqdm(line_str)
            if pct is not None and (pct != last_pct or eta_human):
                last_pct = pct
                if on_progress:
                    on_progress({
                        "progress": pct,
                        "eta": eta_human or "Hisoblanmoqda...",
                        "eta_raw": eta_raw or "--:--",
                    })

    await process.wait()

    if process.returncode != 0:
        error_msg = b"".join(stderr_chunks).decode(errors="replace")
        logger.error("Demucs failed (code %d): %s", process.returncode, error_msg[-500:])
        raise RuntimeError(f"Demucs separation failed: {error_msg[-500:]}")

    # Demucs outputs to: <output_dir>/<model>/<filename_without_ext>/vocals.mp3, no_vocals.mp3
    stem_name = input_path.stem
    result_dir = output_dir / model / stem_name

    if not result_dir.exists():
        # Sometimes Demucs sanitises the folder name; try to find it
        model_dir = output_dir / model
        if model_dir.exists():
            candidates = list(model_dir.iterdir())
            if candidates:
                result_dir = candidates[0]

    vocals_path = _find_file(result_dir, "vocals")
    no_vocals_path = _find_file(result_dir, "no_vocals")

    if vocals_path is None or no_vocals_path is None:
        found = list(result_dir.iterdir()) if result_dir.exists() else []
        raise RuntimeError(
            f"Expected stems not found in {result_dir}. Found: {found}"
        )

    return {
        "vocals": vocals_path,
        "no_vocals": no_vocals_path,
    }


def _find_file(directory: Path, stem_prefix: str) -> Path | None:
    """Find a file whose name starts with `stem_prefix` in `directory`."""
    if not directory.exists():
        return None
    for f in directory.iterdir():
        if f.stem == stem_prefix and f.is_file():
            return f
    return None


def cleanup_old_tasks(
    uploads_dir: Path,
    outputs_dir: Path,
    max_age_hours: float = 2.0,
) -> int:
    """
    Remove upload & output directories older than `max_age_hours`.

    Returns the number of directories removed.
    """
    import time

    removed = 0
    now = time.time()
    cutoff = now - max_age_hours * 3600

    for base_dir in (uploads_dir, outputs_dir):
        if not base_dir.exists():
            continue
        for child in base_dir.iterdir():
            if child.is_dir() and child.stat().st_mtime < cutoff:
                shutil.rmtree(child, ignore_errors=True)
                removed += 1
                logger.info("Cleaned up old directory: %s", child)

    return removed
