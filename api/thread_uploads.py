from __future__ import annotations

from helpers.api import ApiHandler, Request, Response
from helpers.security import safe_filename

from usr.plugins.agent_harness.helpers.deerflow_client import DeerFlowClient
from usr.plugins.agent_harness.helpers.upload_limits import (
    MAX_UPLOAD_BATCH_BYTES,
    UploadTooLargeError,
    format_byte_limit,
    read_upload_bytes,
)


class ThreadUploads(ApiHandler):
    @classmethod
    def get_methods(cls) -> list[str]:
        return ["GET", "POST"]

    async def process(self, input: dict, request: Request) -> dict | Response:
        action = (
            request.args.get("action")
            or request.form.get("action")
            or input.get("action", "list")
        )
        action = str(action or "list").strip().lower()
        context_id = (
            request.args.get("context_id")
            or request.form.get("context_id")
            or input.get("context_id", "")
        )
        context = self.use_context(str(context_id).strip(), create_if_not_exists=False)
        client = DeerFlowClient(context)

        if action in {"delete", "upload"} and request.method != "POST":
            return Response("Upload mutations require POST.", status=405)

        if action == "delete":
            relative_path = str(
                request.form.get("path") or input.get("path") or input.get("filename", "")
            ).strip()
            try:
                deleted = client.delete_thread_upload(relative_path)
            except ValueError as exc:
                return Response(str(exc), status=400)
            return {
                "success": deleted,
                "context_id": context.id,
                "uploads": client.list_thread_uploads(),
            }

        if action == "upload":
            files_to_save = request.files.getlist("files[]") or request.files.getlist("file")
            if not files_to_save:
                files_to_save = list(request.files.values())
            if not files_to_save:
                return {
                    "success": False,
                    "context_id": context.id,
                    "error": "No files uploaded",
                    "uploads": client.list_thread_uploads(),
                }

            saved: list[str] = []
            skipped: list[str] = []
            rejected: list[dict[str, str]] = []
            batch_size = 0
            for file in files_to_save:
                if not file or not file.filename:
                    continue
                filename = safe_filename(file.filename)
                if not filename:
                    skipped.append(file.filename)
                    continue
                try:
                    content = read_upload_bytes(file)
                except UploadTooLargeError as exc:
                    rejected.append({"name": file.filename, "reason": str(exc)})
                    continue
                if batch_size + len(content) > MAX_UPLOAD_BATCH_BYTES:
                    rejected.append(
                        {
                            "name": file.filename,
                            "reason": (
                                "Upload batch exceeds the "
                                f"{format_byte_limit(MAX_UPLOAD_BATCH_BYTES)} limit."
                            ),
                        }
                    )
                    continue
                try:
                    client.save_thread_upload(filename, content)
                except ValueError as exc:
                    rejected.append({"name": file.filename, "reason": str(exc)})
                    continue
                batch_size += len(content)
                saved.append(filename)

            return {
                "success": bool(saved),
                "context_id": context.id,
                "saved": saved,
                "skipped": skipped,
                "rejected": rejected,
                "uploads": client.list_thread_uploads(),
            }

        if action != "list":
            return Response(f"Unknown upload action: {action}", status=400)

        return {
            "success": True,
            "context_id": context.id,
            "uploads": client.list_thread_uploads(),
        }
