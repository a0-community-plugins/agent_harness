from __future__ import annotations

from helpers.tool import Response, Tool

from usr.plugins.agent_harness.helpers import runtime


def _coerce_risk_level(value: str) -> runtime.RiskLevel:
    normalized = str(value or "").strip().lower()
    if normalized in {"low", "elevated", "high", "critical"}:
        return normalized  # type: ignore[return-value]
    return "high"


class HarnessCheckpoint(Tool):
    async def execute(
        self,
        reason: str = "",
        proposed_action: str = "",
        risk_level: str = "high",
        target_tool_name: str = "",
        target_tool_args: dict | None = None,
        **kwargs,
    ) -> Response:
        if self.agent.context.get_data(
            runtime.PARALLEL_WORKER_CONTEXT_KEY,
            recursive=False,
        ):
            raise RuntimeError(
                "Parallel workers cannot request user approvals. Stop this sub-task "
                "and report the exact action that the main chat must perform."
            )

        settings = runtime.load_agent_settings(self.agent)
        run = runtime.ensure_run(self.agent, settings=settings)

        existing = runtime.get_pending_checkpoint(run)
        if existing:
            runtime.save_current_run(self.agent.context, run)
            return Response(
                message=(
                    f"Checkpoint already pending: {existing.reason}. "
                    "Wait for user approval before proceeding."
                ),
                break_loop=False,
            )

        target_name = str(target_tool_name or "").strip()
        target_args = dict(target_tool_args or {})
        action = str(proposed_action or "Await user approval.").strip()
        if not target_name and (
            runtime.DEPENDENCY_INSTALL_RE.search(action)
            or runtime.DESTRUCTIVE_COMMAND_RE.search(action)
            or runtime.GIT_MUTATION_COMMAND_RE.search(action)
        ):
            target_name = "code_execution_tool"
            target_args = {"runtime": "terminal", "code": action}
        if not target_name:
            target_name = self.name
            target_args = {
                "reason": reason,
                "proposed_action": proposed_action,
                "risk_level": risk_level,
            }

        checkpoint = runtime.request_checkpoint(
            run,
            reason=str(reason or "Manual checkpoint requested.").strip(),
            proposed_action=action,
            tool_name=target_name,
            tool_args=target_args,
            risk_level=_coerce_risk_level(risk_level),
        )
        runtime.save_current_run(self.agent.context, run)
        return Response(
            message=(
                f"Checkpoint requested: {checkpoint.reason}. "
                "Await user approval before continuing."
            ),
            break_loop=False,
        )
