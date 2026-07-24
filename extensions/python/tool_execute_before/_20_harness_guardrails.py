from __future__ import annotations

from helpers.errors import RepairableException
from helpers.extension import Extension

from usr.plugins.agent_harness.helpers import runtime


class HarnessGuardrails(Extension):
    async def execute(self, tool_name: str = "", tool_args: dict | None = None, **kwargs):
        if not self.agent:
            return

        run = runtime.get_current_run(self.agent)
        if not run:
            return

        settings = runtime.load_agent_settings(self.agent)
        assessment = runtime.assess_tool_guardrail_decision(
            run=run,
            tool_name=tool_name,
            tool_args=tool_args or {},
            settings=settings,
        )
        if assessment.approved_checkpoint:
            runtime.save_current_run(self.agent.context, run)
            return

        if assessment.denied_checkpoint:
            runtime.save_current_run(self.agent.context, run)
            raise RuntimeError(
                "Agent Harness stopped a repeated risky action. "
                f"{assessment.denial_reason}"
            )

        checkpoint = assessment.checkpoint
        if not checkpoint:
            return

        worker = self.agent.context.get_data(
            runtime.PARALLEL_WORKER_CONTEXT_KEY,
            recursive=False,
        )
        if worker:
            checkpoint.status = "rejected"
            checkpoint.decision_comment = (
                "Parallel workers cannot request or consume user approvals."
            )
            checkpoint.decided_at = runtime.now_iso()
            runtime.record_failure(
                run,
                summary=(
                    f"Parallel worker stopped at an approval boundary: "
                    f"{checkpoint.proposed_action}"
                ),
                settings=settings,
            )
            runtime.save_current_run(self.agent.context, run)
            raise RuntimeError(
                "Agent Harness stopped this parallel worker because its assigned "
                "sub-task requires user approval. Return the blocked action to the "
                "main chat instead of retrying it."
            )

        runtime.save_current_run(self.agent.context, run)
        raise RepairableException(
            "Agent Harness blocked a risky action before execution. "
            f"Pending checkpoint: {checkpoint.reason} "
            f"Proposed action: {checkpoint.proposed_action}. "
            "Do not retry the risky tool until the user approves the checkpoint."
        )
