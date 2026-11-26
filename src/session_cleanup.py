import logging
import os
import re
import shutil
import threading
import time
from pathlib import Path

from src.vectore_store import VectorStore

logger = logging.getLogger(__name__)

SESSION_TTL_SECONDS = 60 * 60
CLEANUP_INTERVAL_SECONDS = 5 * 60
SESSION_ID_PATTERN = re.compile(r"^[0-9a-f]{32}$")


class SessionCleanupJob:
    def __init__(
        self,
        session_root: Path,
        ttl_seconds: int = SESSION_TTL_SECONDS,
        interval_seconds: int = CLEANUP_INTERVAL_SECONDS,
    ) -> None:
        if ttl_seconds <= 0 or interval_seconds <= 0:
            raise ValueError("TTL and cleanup interval must be greater than zero")

        self.session_root = session_root
        self.ttl_seconds = ttl_seconds
        self.interval_seconds = interval_seconds
        self._lock = threading.Lock()
        self._resources: dict[str, VectorStore] = {}
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return

        self.session_root.mkdir(parents=True, exist_ok=True)
        self._thread = threading.Thread(
            target=self._run,
            name="qpilot-session-cleanup",
            daemon=True,
        )
        self._thread.start()

    def register_session(self, session_id: str, vector_store: VectorStore) -> None:
        with self._lock:
            self._resources[session_id] = vector_store

    def unregister_session(self, session_id: str) -> None:
        with self._lock:
            self._resources.pop(session_id, None)

    def touch_session(self, session_id: str) -> bool:
        session_dir = self.session_root / session_id
        with self._lock:
            if not session_dir.is_dir():
                return False
            os.utime(session_dir, None)
            return True

    def _run(self) -> None:
        while not self._stop_event.is_set():
            try:
                self.cleanup_expired()
            except Exception:
                logger.exception("Could not scan for expired session directories")
            self._stop_event.wait(self.interval_seconds)

    def cleanup_expired(self) -> list[Path]:
        removed = []
        with self._lock:
            if not self.session_root.is_dir():
                return removed

            cutoff = time.time() - self.ttl_seconds
            for session_dir in self.session_root.iterdir():
                if (
                    not SESSION_ID_PATTERN.fullmatch(session_dir.name)
                    or session_dir.is_symlink()
                    or not session_dir.is_dir()
                ):
                    continue

                try:
                    if session_dir.stat().st_mtime >= cutoff:
                        continue

                    vector_store = self._resources.get(session_dir.name)
                    if vector_store is not None:
                        vector_store.collection = None
                        vector_store.client.close()
                        vector_store.client = None

                    shutil.rmtree(session_dir)
                    self._resources.pop(session_dir.name, None)
                    removed.append(session_dir)
                except Exception:
                    logger.exception(
                        "Could not remove expired session directory %s",
                        session_dir,
                    )

        return removed
