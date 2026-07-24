from __future__ import annotations

import unittest
from unittest.mock import patch

import support  # noqa: F401

from agent import LoopData
from usr.plugins.agent_harness.extensions.python.message_loop_prompts_after._20_harness_runtime import (
    HarnessRuntimePrompt,
)


class Context:
    def get_data(self, key, recursive=True):
        return None


class Agent:
    def __init__(self):
        self.context = Context()
        self.last_user_message = None


class PromptExtensionTests(unittest.IsolatedAsyncioTestCase):
    async def test_ambient_prompt_is_injected_without_an_active_run(self):
        loop_data = LoopData()
        extension = HarnessRuntimePrompt(agent=Agent())
        settings = {
            "ambient_assist_enabled": True,
            "accepted_rules": [{"rule_text": "Verify the same delivery surface."}],
        }

        with (
            patch(
                "usr.plugins.agent_harness.extensions.python.message_loop_prompts_after._20_harness_runtime.load_agent_settings",
                return_value=settings,
            ),
            patch(
                "usr.plugins.agent_harness.extensions.python.message_loop_prompts_after._20_harness_runtime.get_current_run",
                return_value=None,
            ),
        ):
            await extension.execute(loop_data=loop_data)

        prompt = loop_data.extras_persistent["agent_harness_runtime"]
        self.assertIn("AMBIENT ASSIST", prompt)
        self.assertIn("Verify the same delivery surface", prompt)

    async def test_disabled_ambient_assist_removes_stale_prompt(self):
        loop_data = LoopData()
        loop_data.extras_persistent["agent_harness_runtime"] = "stale"
        extension = HarnessRuntimePrompt(agent=Agent())

        with (
            patch(
                "usr.plugins.agent_harness.extensions.python.message_loop_prompts_after._20_harness_runtime.load_agent_settings",
                return_value={"ambient_assist_enabled": False},
            ),
            patch(
                "usr.plugins.agent_harness.extensions.python.message_loop_prompts_after._20_harness_runtime.get_current_run",
                return_value=None,
            ),
        ):
            await extension.execute(loop_data=loop_data)

        self.assertNotIn("agent_harness_runtime", loop_data.extras_persistent)


if __name__ == "__main__":
    unittest.main()
