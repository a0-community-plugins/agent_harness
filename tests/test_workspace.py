from __future__ import annotations

from io import BytesIO
from pathlib import Path
import tempfile
import unittest

import support  # noqa: F401

from usr.plugins.agent_harness.helpers.upload_limits import (
    UploadTooLargeError,
    read_upload_bytes,
)
from usr.plugins.agent_harness.helpers.workspace import (
    ensure_workspace,
    list_uploads,
    resolve_artifact,
    save_upload,
)


class Upload:
    def __init__(self, content: bytes, content_length=None):
        self.stream = BytesIO(content)
        self.content_length = content_length

    def read(self, size=-1):
        return self.stream.read(size)


class WorkspaceTests(unittest.TestCase):
    def test_uploads_are_confined_to_the_thread_directory(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            paths = ensure_workspace(temp_dir, context_id="ctx")
            saved = save_upload(paths, "notes.txt", b"evidence")

            self.assertEqual(Path(saved).read_bytes(), b"evidence")
            self.assertEqual(list_uploads(paths)[0]["path"], "notes.txt")
            with self.assertRaisesRegex(ValueError, "single safe path segment"):
                save_upload(paths, "../escape.txt", b"no")

    def test_symlink_escapes_are_not_listed_or_resolved(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            paths = ensure_workspace(temp_dir, context_id="ctx")
            outside = Path(temp_dir) / "outside.txt"
            outside.write_text("private", encoding="utf-8")
            upload_link = Path(paths.uploads) / "linked.txt"
            upload_link.symlink_to(outside)
            artifact_link = Path(paths.outputs) / "linked.txt"
            artifact_link.symlink_to(outside)

            self.assertEqual(list_uploads(paths), [])
            with self.assertRaisesRegex(ValueError, "escapes"):
                resolve_artifact(paths, "linked.txt")

    def test_upload_reader_stops_at_the_limit(self):
        with self.assertRaises(UploadTooLargeError):
            read_upload_bytes(Upload(b"12345"), limit=4)

        with self.assertRaises(UploadTooLargeError):
            read_upload_bytes(Upload(b"x", content_length=5), limit=4)


if __name__ == "__main__":
    unittest.main()
