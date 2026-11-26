import os
import tempfile
import time
import unittest
from pathlib import Path

from src.session_cleanup import SessionCleanupJob


class FakeVectorStore:
    def __init__(self) -> None:
        self.collection = object()
        self.client = FakeClient()


class FakeClient:
    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True


class SessionCleanupTests(unittest.TestCase):
    def test_removes_only_expired_session_directories(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            expired = root / "not-a-session"
            expired.mkdir()
            old_session = root / "0123456789abcdef0123456789abcdef"
            old_session.mkdir()
            recent_session = root / "fedcba9876543210fedcba9876543210"
            recent_session.mkdir()
            old_timestamp = time.time() - 120
            os.utime(old_session, (old_timestamp, old_timestamp))
            job = SessionCleanupJob(root, ttl_seconds=60, interval_seconds=30)

            removed = job.cleanup_expired()

            self.assertEqual(removed, [old_session])
            self.assertTrue(expired.exists())
            self.assertTrue(recent_session.exists())
            self.assertFalse(old_session.exists())

    def test_closes_registered_client_before_removing_expired_session(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            session_id = "0123456789abcdef0123456789abcdef"
            session_dir = root / session_id
            session_dir.mkdir()
            old_timestamp = time.time() - 120
            os.utime(session_dir, (old_timestamp, old_timestamp))

            vector_store = FakeVectorStore()
            client = vector_store.client
            job = SessionCleanupJob(root, ttl_seconds=60, interval_seconds=30)
            job.register_session(session_id, vector_store)

            removed = job.cleanup_expired()

            self.assertEqual(removed, [session_dir])
            self.assertTrue(client.closed)
            self.assertIsNone(vector_store.client)
            self.assertIsNone(vector_store.collection)
            self.assertFalse(session_dir.exists())


if __name__ == "__main__":
    unittest.main()
