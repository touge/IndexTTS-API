"""
log_cleaner.py

Periodically checks and manages the size of logs/latest.log.

Strategy:
  - When latest.log exceeds `max_size_mb`, archive the current file to
    logs/<YYYY-MM-DD_HH-MM-SS>.log, then truncate latest.log (or keep
    the last `keep_lines` lines, if configured).
  - Old archive files beyond `max_archives` count are deleted.
  - Runs in a background daemon thread started from FastAPI's lifespan.
"""

import os
import time
import shutil
import threading
import logging
from pathlib import Path
from datetime import datetime

logger = logging.getLogger("log_cleaner")

# Resolved path to the logs/ directory (two levels up from app/utils/ -> project root -> logs/)
LOGS_DIR = Path(__file__).resolve().parent.parent.parent / "logs"
LATEST_LOG = LOGS_DIR / "latest.log"


def _archive_and_truncate(max_size_bytes: int, keep_lines: int, max_archives: int) -> None:
    """
    Check latest.log and, if it exceeds max_size_bytes:
      1. Archive the current file as logs/<timestamp>.log
      2. Truncate (or tail) latest.log
      3. Remove oldest archives exceeding max_archives
    """
    if not LATEST_LOG.exists():
        return

    size = LATEST_LOG.stat().st_size
    if size <= max_size_bytes:
        return

    size_mb = size / (1024 * 1024)
    logger.info(
        f"[LogCleaner] 'latest.log' is {size_mb:.2f} MB, exceeds limit – archiving..."
    )

    # 1. Archive the current log
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    archive_path = LOGS_DIR / f"{timestamp}.log"
    try:
        shutil.copy2(LATEST_LOG, archive_path)
        logger.info(f"[LogCleaner] Archived to '{archive_path.name}'.")
    except Exception as e:
        logger.error(f"[LogCleaner] Failed to archive log: {e}")
        return

    # 2. Truncate latest.log (keep tail lines if keep_lines > 0)
    try:
        if keep_lines > 0:
            content = LATEST_LOG.read_bytes().decode("utf-8", errors="replace")
            lines = content.splitlines(keepends=True)
            tail = lines[-keep_lines:] if len(lines) > keep_lines else lines
            LATEST_LOG.write_text("".join(tail), encoding="utf-8")
            logger.info(
                f"[LogCleaner] 'latest.log' truncated, kept last {len(tail)} lines."
            )
        else:
            LATEST_LOG.write_text("", encoding="utf-8")
            logger.info("[LogCleaner] 'latest.log' truncated completely.")
    except Exception as e:
        logger.error(f"[LogCleaner] Failed to truncate 'latest.log': {e}")

    # 3. Remove oldest archives if over max_archives limit
    if max_archives <= 0:
        return
    try:
        archives = sorted(
            [f for f in LOGS_DIR.iterdir() if f.suffix == ".log" and f.name != "latest.log"],
            key=lambda f: f.stat().st_mtime,
        )
        while len(archives) > max_archives:
            oldest = archives.pop(0)
            oldest.unlink()
            logger.info(f"[LogCleaner] Deleted old archive '{oldest.name}'.")
    except Exception as e:
        logger.error(f"[LogCleaner] Failed to clean old archives: {e}")


def run_cleanup(config) -> None:
    """Read settings from config and perform one cleanup pass."""
    log_cleanup_cfg = config.get("log_cleanup", {}) or {}
    max_size_mb    = float(log_cleanup_cfg.get("max_size_mb",    10))
    keep_lines     = int(  log_cleanup_cfg.get("keep_lines",     500))
    max_archives   = int(  log_cleanup_cfg.get("max_archives",   7))
    max_size_bytes = int(max_size_mb * 1024 * 1024)

    _archive_and_truncate(max_size_bytes, keep_lines, max_archives)


def start_cleanup_thread(config) -> threading.Thread:
    """
    Start a daemon thread that periodically cleans logs/latest.log.
    Returns the thread object (already started).
    """
    log_cleanup_cfg  = config.get("log_cleanup", {}) or {}
    interval_minutes = float(log_cleanup_cfg.get("check_interval_minutes", 30))
    interval_seconds = interval_minutes * 60
    max_size_mb      = log_cleanup_cfg.get("max_size_mb", 10)

    def _loop():
        logger.info(
            f"[LogCleaner] Background thread started – "
            f"checking every {interval_minutes:.0f} min, "
            f"threshold {max_size_mb} MB."
        )
        while True:
            try:
                run_cleanup(config)
            except Exception as e:
                logger.error(f"[LogCleaner] Unexpected error during cleanup: {e}")
            time.sleep(interval_seconds)

    thread = threading.Thread(target=_loop, daemon=True, name="LogCleanerThread")
    thread.start()
    return thread
