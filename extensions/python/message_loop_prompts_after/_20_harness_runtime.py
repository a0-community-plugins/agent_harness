from __future__ import annotations

from agent import LoopData
from helpers.extension import Extension

from usr.plugins.agent_harness.helpers.lifecycle import (
    get_current_run,
    save_current_run,
)
from usr.plugins.agent_harness.helpers.models import (
    DEFAULT_RUN_OBJECTIVE,
    PARALLEL_WORKER_CONTEXT_KEY,
)
from usr.plugins.agent_harness.helpers.renderer import render_system_prompt
from usr.plugins.agent_harness.helpers.settings import load_agent_settings


class HarnessRuntimePrompt(Extension):
    async def execute(self, loop_data: LoopData | None = None, **kwargs):
        if not self.agent or loop_data is None:
            return

        settings = load_agent_settings(self.agent)
        run = get_current_run(self.agent)

        # Auto-update objective from first user message if still default
        if (
            run
            and run.objective == DEFAULT_RUN_OBJECTIVE
            and self.agent.last_user_message
        ):
            msg_text = ""
            if hasattr(self.agent.last_user_message, "message"):
                msg_text = str(self.agent.last_user_message.message)
            elif hasattr(self.agent.last_user_message, "content"):
                content = self.agent.last_user_message.content
                if isinstance(content, dict):
                    msg_text = str(content.get("user_message", ""))
                else:
                    msg_text = str(content)
            if msg_text and len(msg_text.strip()) > 10:
                run.objective = msg_text.strip()[:200]
                save_current_run(self.agent.context, run)

        prompt = render_system_prompt(
            settings=settings,
            run=run,
            accepted_rules=list(settings.get("accepted_rules", [])),
        )
        worker = self.agent.context.get_data(
            PARALLEL_WORKER_CONTEXT_KEY,
            recursive=False,
        )
        if worker and prompt:
            prompt = "\n\n".join(
                [
                    prompt,
                    "PARALLEL WORKER SAFETY",
                    "- Work only on the assigned sub-task and avoid unrelated changes.",
                    "- Do not install dependencies, run destructive commands, edit protected paths, or exceed the edit breadth limit.",
                    "- If the sub-task needs approval, stop and report the exact blocked action so the main chat can perform it.",
                ]
            )

        key = "agent_harness_runtime"
        if prompt:
            loop_data.extras_persistent[key] = prompt
        else:
            loop_data.extras_persistent.pop(key, None)
