from __future__ import annotations

from helpers.extension import Extension
from helpers.tool import Response

from usr.plugins.agent_harness.helpers import runtime


class HarnessToolEvents(Extension):
    async def execute(
        self,
        tool_name: str = "",
        response: Response | None = None,
        **kwargs,
    ):
        if not self.agent:
            return
        run = runtime.get_current_run(self.agent)
        if not run:
            return
        current_tool = self.agent.loop_data.current_tool
        tool_args = current_tool.args if current_tool else {}
        runtime.record_tool_activity(
            run=run,
            tool_name=tool_name,
            tool_args=tool_args,
            tool_response=response.message if response else "",
        )
        runtime.save_current_run(self.agent.context, run)
