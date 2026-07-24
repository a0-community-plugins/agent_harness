from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from usr.plugins.agent_harness.helpers.models import WorkspacePaths

WORKSPACE_ROOT = ".harness"
MAX_LISTED_FILES = 1_000


def _safe_context_segment(context_id: str) -> str:
    return "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in context_id)


def ensure_workspace(project_dir: str, context_id: str = "") -> WorkspacePaths:
    root = Path(project_dir) / WORKSPACE_ROOT
    thread_root = root / "threads" / _safe_context_segment(context_id) if context_id else None
    user_data = thread_root / "user-data" if thread_root else None
    workspace_dir = user_data / "workspace" if user_data else root / "workspace"
    outputs_dir = user_data / "outputs" if user_data else root / "outputs"
    uploads_dir = user_data / "uploads" if user_data else root / "uploads"
    paths = WorkspacePaths(
        root=str(root),
        workspace=str(workspace_dir),
        outputs=str(outputs_dir),
        uploads=str(uploads_dir),
        thread_root=str(thread_root) if thread_root else "",
        user_data=str(user_data) if user_data else "",
    )
    for p in [paths.workspace, paths.outputs, paths.uploads]:
        Path(p).mkdir(parents=True, exist_ok=True)
    return paths


def clean_workspace(paths: WorkspacePaths) -> None:
    if Path(paths.workspace).exists():
        shutil.rmtree(paths.workspace)


def save_upload(paths: WorkspacePaths, filename: str, content: bytes) -> str:
    if not filename or Path(filename).name != filename or filename in {".", ".."}:
        raise ValueError("Upload filename must be a single safe path segment")
    filepath = resolve_upload(paths, filename, create_parent=True)
    filepath.write_bytes(content)
    return str(filepath)


def list_uploads(paths: WorkspacePaths) -> list[dict[str, Any]]:
    return _list_safe_files(Path(paths.uploads))


def delete_upload(paths: WorkspacePaths, relative_path: str) -> bool:
    target = resolve_upload(paths, relative_path, create_parent=False)
    if not target.exists() or not target.is_file():
        return False
    target.unlink()
    return True


def resolve_upload(
    paths: WorkspacePaths,
    relative_path: str,
    *,
    create_parent: bool = False,
) -> Path:
    uploads_root = Path(paths.uploads).resolve()
    candidate = (uploads_root / relative_path).resolve()
    if uploads_root != candidate and uploads_root not in candidate.parents:
        raise ValueError("Upload path escapes the thread uploads directory")
    if create_parent:
        candidate.parent.mkdir(parents=True, exist_ok=True)
    return candidate


def list_artifacts(paths: WorkspacePaths) -> list[dict[str, Any]]:
    return _list_safe_files(Path(paths.outputs))


def resolve_artifact(paths: WorkspacePaths, relative_path: str) -> Path:
    outputs_root = Path(paths.outputs).resolve()
    candidate = (outputs_root / relative_path).resolve()
    if outputs_root != candidate and outputs_root not in candidate.parents:
        raise ValueError("Artifact path escapes the thread outputs directory")
    return candidate


def cleanup_thread_data(paths: WorkspacePaths) -> None:
    if paths.thread_root and Path(paths.thread_root).exists():
        shutil.rmtree(paths.thread_root)


def _list_safe_files(root: Path) -> list[dict[str, Any]]:
    try:
        resolved_root = root.resolve()
    except (OSError, RuntimeError):
        return []
    if not resolved_root.exists():
        return []

    results: list[dict[str, Any]] = []
    for file_path in sorted(resolved_root.rglob("*")):
        try:
            resolved_file = file_path.resolve(strict=True)
            if not resolved_file.is_file() or not resolved_file.is_relative_to(resolved_root):
                continue
            relative = file_path.relative_to(resolved_root).as_posix()
            size = resolved_file.stat().st_size
        except (OSError, RuntimeError, ValueError):
            continue
        results.append(
            {
                "name": file_path.name,
                "path": relative,
                "size": size,
            }
        )
        if len(results) >= MAX_LISTED_FILES:
            break
    return results
