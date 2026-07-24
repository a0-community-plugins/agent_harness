from __future__ import annotations

from typing import Any

from usr.plugins.agent_harness.helpers.models import (
    RunRecord, SubTask,
)
from usr.plugins.agent_harness.helpers.settings import get_mode_policy


def build_scoped_context(sub_task: SubTask, run: RunRecord) -> str:
    lines = [
        f"## Sub-Task: {sub_task.title}",
        f"Role: {sub_task.role}",
        f"Description: {sub_task.description}",
    ]
    if sub_task.depends_on and run.task_graph:
        completed_deps = [
            t for t in run.task_graph.sub_tasks
            if t.id in sub_task.depends_on and t.status == "completed"
        ]
        if completed_deps:
            lines.append("\n## Dependency Results:")
            for dep in completed_deps:
                lines.append(f"- {dep.title}: {dep.result_summary}")
    return "\n".join(lines)


def dispatch_ready_tasks(
    run: RunRecord, settings: dict[str, Any],
) -> list[SubTask]:
    if not run.task_graph:
        return []
    from usr.plugins.agent_harness.helpers.parallel import reconcile_run_graph

    reconcile_run_graph(run)
    policy = get_mode_policy(settings, run.mode)
    limit = policy["subagent_limit"]
    dispatched_count = sum(
        1 for t in run.task_graph.sub_tasks if t.status == "dispatched"
    )
    available_slots = max(0, limit - dispatched_count)
    ready = run.task_graph.ready_tasks()
    return ready[:available_slots]
