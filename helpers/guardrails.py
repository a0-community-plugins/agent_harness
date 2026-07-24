from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re
from fnmatch import fnmatch
from pathlib import Path
from typing import Any, Literal

from usr.plugins.agent_harness.helpers.models import (
    RunRecord,
    CheckpointRecord,
    RiskLevel,
    now_iso,
    new_id,
    _normalize_path,
    DEPENDENCY_INSTALL_RE,
    DESTRUCTIVE_COMMAND_RE,
    GIT_MUTATION_COMMAND_RE,
)


@dataclass
class GuardrailAssessment:
    checkpoint: CheckpointRecord | None = None
    approved_checkpoint: CheckpointRecord | None = None
    denied_checkpoint: CheckpointRecord | None = None
    denial_reason: str = ""


def is_file_mutation(tool_name: str, tool_args: dict[str, Any]) -> bool:
    normalized_name = str(tool_name or "").split(":", 1)[0].strip()
    if normalized_name not in {"text_editor", "text_editor_remote"}:
        return False
    action = str(
        tool_args.get("action")
        or tool_args.get("method")
        or tool_args.get("command")
        or ""
    ).strip().lower()
    if action:
        return action in {
            "write",
            "patch",
            "create",
            "str_replace",
            "insert",
            "replace",
        }
    return any(
        key in tool_args
        for key in (
            "content",
            "patch_text",
            "old_text",
            "new_text",
            "edits",
        )
    )


def get_pending_checkpoint(run: RunRecord) -> CheckpointRecord | None:
    return next(
        (
            checkpoint
            for checkpoint in reversed(run.checkpoints)
            if checkpoint.status == "pending"
        ),
        None,
    )


def _is_protected_path(path: str, settings: dict[str, Any]) -> bool:
    basename = Path(path).name
    path_variants = {_normalize_path(path)}
    try:
        resolved = Path(path).expanduser().resolve()
        path_variants.add(resolved.as_posix())
        path_variants.add(resolved.relative_to(Path.cwd().resolve()).as_posix())
    except (OSError, RuntimeError, ValueError):
        pass

    for pattern in settings.get("protected_paths", []):
        raw_pattern = str(pattern).strip()
        if not raw_pattern:
            continue
        normalized_pattern = _normalize_path(raw_pattern)
        has_glob = any(token in raw_pattern for token in "*?[]")
        looks_like_directory = raw_pattern.endswith("/") or (
            "/" in normalized_pattern and not has_glob and Path(raw_pattern).suffix == ""
        )
        for normalized in path_variants:
            if looks_like_directory:
                directory = normalized_pattern.rstrip("/")
                if normalized == directory or normalized.startswith(f"{directory}/"):
                    return True
            if fnmatch(normalized, raw_pattern) or fnmatch(basename, raw_pattern):
                return True
    return False


def _terminal_command(tool_name: str, tool_args: dict[str, Any]) -> str:
    if tool_name != "code_execution_tool":
        return ""
    if str(tool_args.get("runtime", "")).lower() != "terminal":
        return ""
    return str(tool_args.get("code", ""))


def _command_matches(
    *,
    tool_name: str,
    tool_args: dict[str, Any],
    pattern: re.Pattern[str],
) -> bool:
    command = _terminal_command(tool_name, tool_args)
    return bool(command and pattern.search(command))


def _would_cross_edit_breadth_limit(
    run: RunRecord,
    tool_name: str,
    tool_args: dict[str, Any],
    settings: dict[str, Any],
) -> bool:
    if run.allow_broad_edits:
        return False
    if not is_file_mutation(tool_name, tool_args):
        return False
    path = str(tool_args.get("path", "")).strip()
    if not path:
        return False
    normalized = _normalize_path(path)
    touched_files = {_normalize_path(item) for item in run.touched_files}
    if normalized in touched_files:
        return False
    try:
        max_files = int(settings.get("max_auto_edit_files", 8))
    except (TypeError, ValueError):
        max_files = 8
    return len(touched_files) >= max(1, max_files)


def _set_blocked_state(run: RunRecord, risk_level: RiskLevel) -> None:
    run.phase = "blocked"
    run.status = "blocked"
    run.risk_level = risk_level


def _set_active_state(run: RunRecord) -> None:
    run.phase = "implement" if run.mode != "flash" else "idle"
    run.status = "active"


def action_fingerprint(tool_name: str, tool_args: dict[str, Any]) -> str:
    normalized_tool_name = str(tool_name or "").strip()
    payload = {
        "tool_name": normalized_tool_name,
        "tool_args": _canonical_tool_args(normalized_tool_name, tool_args or {}),
    }
    serialized = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _canonical_tool_args(tool_name: str, tool_args: dict[str, Any]) -> Any:
    if tool_name != "code_execution_tool":
        return _json_safe(tool_args)

    runtime = str(tool_args.get("runtime", "") or "").strip().lower()
    canonical: dict[str, Any] = {
        "runtime": runtime,
        "session": _safe_int(tool_args.get("session", 0), default=0),
        "reset": bool(tool_args.get("reset", False) or runtime == "reset"),
        "allow_running": bool(tool_args.get("allow_running", False)),
    }
    if runtime in {"terminal", "python", "nodejs"}:
        canonical["code"] = str(tool_args.get("code", "") or "")
    return canonical


def _safe_int(value: Any, *, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): _json_safe(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def _checkpoint_action_fingerprint(checkpoint: CheckpointRecord) -> str:
    if checkpoint.action_fingerprint:
        return checkpoint.action_fingerprint
    if checkpoint.tool_name == "harness_checkpoint":
        proposed_action = checkpoint.proposed_action.strip()
        if proposed_action and (
            DEPENDENCY_INSTALL_RE.search(proposed_action)
            or DESTRUCTIVE_COMMAND_RE.search(proposed_action)
            or GIT_MUTATION_COMMAND_RE.search(proposed_action)
        ):
            return action_fingerprint(
                "code_execution_tool",
                {"runtime": "terminal", "code": proposed_action},
            )
    return action_fingerprint(checkpoint.tool_name, checkpoint.tool_args)


def _latest_matching_checkpoint(
    run: RunRecord,
    *,
    tool_name: str,
    tool_args: dict[str, Any],
) -> CheckpointRecord | None:
    fingerprint = action_fingerprint(tool_name, tool_args)
    for checkpoint in reversed(run.checkpoints):
        if _checkpoint_action_fingerprint(checkpoint) == fingerprint:
            return checkpoint
    return None


def request_checkpoint(
    run: RunRecord,
    *,
    reason: str,
    proposed_action: str,
    tool_name: str,
    tool_args: dict[str, Any],
    risk_level: RiskLevel,
) -> CheckpointRecord:
    checkpoint = CheckpointRecord(
        id=new_id("chk"),
        reason=reason,
        proposed_action=proposed_action,
        tool_name=tool_name,
        tool_args=tool_args,
        action_fingerprint=action_fingerprint(tool_name, tool_args),
        risk_level=risk_level,
        created_at=now_iso(),
    )
    run.checkpoints.append(checkpoint)
    _set_blocked_state(run, risk_level)
    return checkpoint


def assess_tool_guardrail_decision(
    *,
    run: RunRecord,
    tool_name: str,
    tool_args: dict[str, Any],
    settings: dict[str, Any],
) -> GuardrailAssessment:
    if tool_name in {
        "harness_run",
        "harness_checkpoint",
        "harness_memory_propose",
        "response",
    }:
        return GuardrailAssessment()

    pending = get_pending_checkpoint(run)
    if pending:
        return GuardrailAssessment(
            denied_checkpoint=pending,
            denial_reason=(
                "A checkpoint is still pending. No additional tool execution is allowed "
                "until the user approves or rejects it."
            ),
        )

    matching = _latest_matching_checkpoint(
        run,
        tool_name=tool_name,
        tool_args=tool_args,
    )
    if matching and matching.status == "approved":
        if matching.consumed_at:
            _set_blocked_state(run, matching.risk_level)
            return GuardrailAssessment(
                denied_checkpoint=matching,
                denial_reason=(
                    "The matching checkpoint approval was already consumed by one execution "
                    "attempt. Request a new checkpoint instead of retrying the action."
                ),
            )
        matching.consumed_at = now_iso()
        _set_active_state(run)
        return GuardrailAssessment(approved_checkpoint=matching)
    if matching and matching.status == "rejected":
        _set_blocked_state(run, matching.risk_level)
        return GuardrailAssessment(
            denied_checkpoint=matching,
            denial_reason=(
                "The user rejected the matching checkpoint. Change the proposed action or "
                "request a new explicit checkpoint; do not retry it unchanged."
            ),
        )

    if settings.get("dependency_install_requires_checkpoint", True) and _command_matches(
        tool_name=tool_name,
        tool_args=tool_args,
        pattern=DEPENDENCY_INSTALL_RE,
    ):
        return GuardrailAssessment(
            checkpoint=request_checkpoint(
                run,
                reason="Checkpoint required for dependency install in deep harness mode.",
                proposed_action=_terminal_command(tool_name, tool_args).strip(),
                tool_name=tool_name,
                tool_args=tool_args,
                risk_level="high",
            ),
        )

    if settings.get("destructive_actions_require_checkpoint", True) and _command_matches(
        tool_name=tool_name,
        tool_args=tool_args,
        pattern=DESTRUCTIVE_COMMAND_RE,
    ):
        return GuardrailAssessment(
            checkpoint=request_checkpoint(
                run,
                reason="Checkpoint required for destructive filesystem or git action.",
                proposed_action=_terminal_command(tool_name, tool_args).strip(),
                tool_name=tool_name,
                tool_args=tool_args,
                risk_level="critical",
            ),
        )

    if settings.get("git_mutations_require_checkpoint", True) and _command_matches(
        tool_name=tool_name,
        tool_args=tool_args,
        pattern=GIT_MUTATION_COMMAND_RE,
    ):
        return GuardrailAssessment(
            checkpoint=request_checkpoint(
                run,
                reason="Checkpoint required before a repository-changing Git command.",
                proposed_action=_terminal_command(tool_name, tool_args).strip(),
                tool_name=tool_name,
                tool_args=tool_args,
                risk_level="high",
            ),
        )

    path = str(tool_args.get("path", "")).strip()
    if path and is_file_mutation(tool_name, tool_args) and _is_protected_path(path, settings):
        return GuardrailAssessment(
            checkpoint=request_checkpoint(
                run,
                reason=f"Checkpoint required for protected path edit: {Path(path).name}.",
                proposed_action=path,
                tool_name=tool_name,
                tool_args=tool_args,
                risk_level="high",
            ),
        )

    if _would_cross_edit_breadth_limit(run, tool_name, tool_args, settings):
        return GuardrailAssessment(
            checkpoint=request_checkpoint(
                run,
                reason="Checkpoint required before exceeding the automatic edit breadth limit.",
                proposed_action=path,
                tool_name=tool_name,
                tool_args=tool_args,
                risk_level="high",
            ),
        )

    return GuardrailAssessment()


def assess_tool_guardrail(
    *,
    run: RunRecord,
    tool_name: str,
    tool_args: dict[str, Any],
    settings: dict[str, Any],
) -> CheckpointRecord | None:
    return assess_tool_guardrail_decision(
        run=run,
        tool_name=tool_name,
        tool_args=tool_args,
        settings=settings,
    ).checkpoint


def decide_checkpoint(
    run: RunRecord,
    *,
    checkpoint_id: str,
    decision: Literal["approved", "rejected"],
    comment: str = "",
) -> CheckpointRecord:
    if decision not in {"approved", "rejected"}:
        raise ValueError("Checkpoint decision must be 'approved' or 'rejected'.")
    for checkpoint in run.checkpoints:
        if checkpoint.id != checkpoint_id:
            continue
        if checkpoint.status != "pending":
            raise ValueError(
                f"Checkpoint '{checkpoint_id}' was already {checkpoint.status}."
            )
        checkpoint.status = decision
        checkpoint.decision_comment = comment
        checkpoint.decided_at = now_iso()
        if decision == "approved":
            _set_active_state(run)
        else:
            _set_blocked_state(run, checkpoint.risk_level)
        return checkpoint
    raise ValueError(f"Checkpoint '{checkpoint_id}' not found")
