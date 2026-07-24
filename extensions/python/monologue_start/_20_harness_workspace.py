from __future__ import annotations

from helpers.extension import Extension
from helpers import persist_chat

from usr.plugins.agent_harness.helpers import lifecycle
from usr.plugins.agent_harness.helpers import settings as harness_settings
from usr.plugins.agent_harness.helpers.workspace import ensure_workspace


class HarnessWorkspace(Extension):
    async def execute(self, **kwargs):
        if not self.agent:
            return
        run = lifecycle.get_current_run(self.agent)
        if not run:
            return
        agent_settings = harness_settings.load_agent_settings(self.agent)
        if not agent_settings.get("workspace_enabled", True):
            return
        base_dir = persist_chat.get_chat_folder_path(self.agent.context.id)
        paths = ensure_workspace(base_dir, context_id=self.agent.context.id)
        run.workspace = paths
        lifecycle.save_current_run(self.agent.context, run)
