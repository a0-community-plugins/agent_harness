from __future__ import annotations

import threading
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any

from agent import Agent, AgentContext, AgentContextType, UserMessage
from helpers.defer import DeferredTask
from initialize import initialize_agent

from usr.plugins.agent_harness.helpers.models import (
    PARALLEL_WORKER_CONTEXT_KEY,
    RunRecord,
    SubTask,
    now_iso,
)
from usr.plugins.agent_harness.helpers.orchestrator import build_scoped_context
from usr.plugins.agent_harness.helpers.lifecycle import (
    create_run_record,
    save_current_run,
)

# Module-level registry of active background sub-agents.
# DeferredTask objects are not serializable, so they live here instead of on RunRecord.
_active_tasks: dict[str, "BackgroundSubAgent"] = {}
_lock = threading.Lock()
_INHERITED_CONTEXT_SKIP_KEYS = {
    Agent.DATA_NAME_SUPERIOR,
    Agent.DATA_NAME_SUBORDINATE,
    "agent_harness.current_run",
    PARALLEL_WORKER_CONTEXT_KEY,
}
_RESULT_SUMMARY_LIMIT = 4_000


@dataclass
class BackgroundSubAgent:
    sub_task_id: str
    run_id: str
    context: AgentContext
    agent: Agent
    deferred: DeferredTask
    spawned_at: str = field(default_factory=now_iso)


def _clone_parent_context_data(parent_context: "AgentContext | None") -> dict[str, Any] | None:
    if not parent_context or not parent_context.data:
        return None

    inherited: dict[str, Any] = {}
    for key, value in parent_context.data.items():
        if key in _INHERITED_CONTEXT_SKIP_KEYS:
            continue
        try:
            inherited[key] = deepcopy(value)
        except Exception:
            continue
    return inherited or None


def _registry_key(run_id: str, sub_task_id: str) -> str:
    return f"{run_id}:{sub_task_id}"


def _dispose_background(bg: BackgroundSubAgent) -> None:
    try:
        bg.deferred.kill(terminate_thread=True)
    finally:
        AgentContext.remove(bg.context.id)


def registered_task_ids(run_id: str) -> set[str]:
    with _lock:
        return {
            bg.sub_task_id
            for bg in _active_tasks.values()
            if bg.run_id == run_id
        }


def reconcile_run_graph(run: RunRecord) -> list[str]:
    if not run.task_graph:
        return []

    known_task_ids = registered_task_ids(run.run_id)
    restored: list[str] = []
    for task in run.task_graph.sub_tasks:
        if task.status != "dispatched":
            continue
        if task.id in known_task_ids:
            continue
        task.status = "pending"
        task.dispatched_at = ""
        restored.append(task.id)
    return restored


def spawn_parallel(
    run: RunRecord,
    sub_tasks: list[SubTask],
    settings: dict[str, Any],
    parent_context: "AgentContext | None" = None,
) -> list[str]:
    """Spawn background agents for each sub-task. Returns list of spawned IDs.

    Parent configuration and safe context data are copied into each child so the
    worker uses the selected profile and project settings while keeping isolated
    history and harness state.
    """
    prepared: list[BackgroundSubAgent] = []
    spawned_ids: list[str] = []
    inherited_data = _clone_parent_context_data(parent_context)

    try:
        for sub_task in sub_tasks:
            scoped_msg = build_scoped_context(sub_task, run)
            config = (
                deepcopy(parent_context.config)
                if parent_context is not None
                else initialize_agent()
            )
            ctx = AgentContext(
                config=config,
                type=AgentContextType.BACKGROUND,
                set_current=False,
                data=deepcopy(inherited_data) if inherited_data else None,
            )
            child_run = create_run_record(
                context_id=ctx.id,
                mode="flash",
                objective=f"{sub_task.title}: {sub_task.description}".strip(": "),
                constraints=[
                    "Stay within the assigned sub-task.",
                    "Stop if an action requires user approval.",
                ],
                settings=settings,
                allow_broad_edits=run.allow_broad_edits,
            )
            child_run.phase = "implement"
            save_current_run(ctx, child_run)
            ctx.set_data(
                PARALLEL_WORKER_CONTEXT_KEY,
                {
                    "parent_run_id": run.run_id,
                    "parent_context_id": run.context_id,
                    "sub_task_id": sub_task.id,
                    "role": sub_task.role,
                },
                recursive=False,
            )

            agent = ctx.agent0
            agent.hist_add_user_message(
                UserMessage(message=scoped_msg, attachments=[])
            )
            prepared.append(
                BackgroundSubAgent(
                    sub_task_id=sub_task.id,
                    run_id=run.run_id,
                    context=ctx,
                    agent=agent,
                    deferred=DeferredTask(
                        thread_name=f"harness-{run.run_id}-{sub_task.id}"
                    ),
                )
            )

        for bg in prepared:
            bg.deferred.start_task(bg.agent.monologue)
            with _lock:
                _active_tasks[
                    _registry_key(bg.run_id, bg.sub_task_id)
                ] = bg
            sub_task = next(
                task for task in sub_tasks if task.id == bg.sub_task_id
            )
            sub_task.status = "dispatched"
            sub_task.dispatched_at = now_iso()
            spawned_ids.append(sub_task.id)
    except Exception:
        with _lock:
            for bg in prepared:
                _active_tasks.pop(
                    _registry_key(bg.run_id, bg.sub_task_id),
                    None,
                )
        for bg in prepared:
            _dispose_background(bg)
        for sub_task in sub_tasks:
            if sub_task.id in spawned_ids:
                sub_task.status = "pending"
                sub_task.dispatched_at = ""
        raise

    return spawned_ids


def poll_status(run_id: str) -> dict[str, str]:
    """Check each active background task for a given run.
    Returns dict of sub_task_id -> 'running' | 'completed' | 'failed'.
    """
    results: dict[str, str] = {}
    with _lock:
        tasks = [bg for bg in _active_tasks.values() if bg.run_id == run_id]
    for bg in tasks:
        if not bg.deferred.is_ready():
            results[bg.sub_task_id] = "running"
        else:
            try:
                bg.deferred.result_sync(timeout=0)
                results[bg.sub_task_id] = "completed"
            except Exception:
                results[bg.sub_task_id] = "failed"
    return results


def collect_completed(run: RunRecord) -> list[tuple[str, str | None, str | None]]:
    """Harvest results from finished background tasks.
    Returns list of (sub_task_id, summary_or_none, error_or_none).
    Removes completed/failed tasks from the registry.
    """
    collected: list[tuple[str, str | None, str | None]] = []
    with _lock:
        ready = [
            bg
            for bg in _active_tasks.values()
            if bg.run_id == run.run_id and bg.deferred.is_ready()
        ]

    for bg in ready:
        try:
            result = bg.deferred.result_sync(timeout=0)
            summary = str(result)[:_RESULT_SUMMARY_LIMIT] if result else ""
            collected.append((bg.sub_task_id, summary, None))
        except Exception as exc:
            collected.append((bg.sub_task_id, None, str(exc)))
        with _lock:
            _active_tasks.pop(
                _registry_key(bg.run_id, bg.sub_task_id),
                None,
            )
        _dispose_background(bg)

    return collected


def kill_all(run_id: str) -> int:
    """Kill all background tasks for a run. Returns number killed."""
    with _lock:
        selected = [
            bg for bg in _active_tasks.values() if bg.run_id == run_id
        ]
        for bg in selected:
            _active_tasks.pop(
                _registry_key(bg.run_id, bg.sub_task_id),
                None,
            )
    for bg in selected:
        _dispose_background(bg)
    return len(selected)


def kill_all_runs() -> int:
    """Kill every plugin-owned background worker."""
    with _lock:
        selected = list(_active_tasks.values())
        _active_tasks.clear()
    for bg in selected:
        _dispose_background(bg)
    return len(selected)


def active_count(run_id: str) -> int:
    """Return number of currently running background tasks for a run."""
    with _lock:
        return sum(
            1 for bg in _active_tasks.values()
            if bg.run_id == run_id and not bg.deferred.is_ready()
        )
