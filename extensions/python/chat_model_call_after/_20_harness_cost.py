from __future__ import annotations

from helpers.extension import Extension

from usr.plugins.agent_harness.helpers import lifecycle
from usr.plugins.agent_harness.helpers import settings as harness_settings
from usr.plugins.agent_harness.helpers.cost_tracker import record_usage, check_budget
from usr.plugins.agent_harness.helpers.guardrails import request_checkpoint


def _budget_checkpoint_exists(run, budget: int) -> bool:
    return any(
        checkpoint.tool_name == "harness_budget"
        and checkpoint.tool_args.get("run_id") == run.run_id
        and checkpoint.tool_args.get("budget") == budget
        for checkpoint in run.checkpoints
    )


def _configured_budget(settings: dict) -> int:
    try:
        return max(0, int(settings.get("token_budget", 0)))
    except (TypeError, ValueError):
        return 0


class HarnessCost(Extension):
    async def execute(self, response: str = "", **kwargs):
        if not self.agent:
            return
        run = lifecycle.get_current_run(self.agent)
        if not run:
            return
        agent_settings = harness_settings.load_agent_settings(self.agent)
        if not agent_settings.get("cost_tracking_enabled", True):
            return

        try:
            from helpers.tokens import approximate_tokens
            completion_tokens = approximate_tokens(response) if response else 0
        except ImportError:
            completion_tokens = len(response) // 4 if response else 0

        if completion_tokens > 0:
            record_usage(run, prompt_tokens=0, completion_tokens=completion_tokens)
            budget = _configured_budget(agent_settings)
            if run.cost:
                run.cost.budget_limit = budget
                run.cost.budget_remaining = max(
                    0,
                    budget - run.cost.usage.total_tokens,
                )

            if (
                check_budget(run, agent_settings)
                and not _budget_checkpoint_exists(run, budget)
            ):
                request_checkpoint(
                    run,
                    reason=(
                        f"Approximate output-token budget of {budget} was reached. "
                        "Approve once to continue this run without another budget prompt."
                    ),
                    proposed_action=(
                        f"Continue run {run.run_id} beyond its configured token budget"
                    ),
                    tool_name="harness_budget",
                    tool_args={"run_id": run.run_id, "budget": budget},
                    risk_level="high",
                )
            lifecycle.save_current_run(self.agent.context, run)
