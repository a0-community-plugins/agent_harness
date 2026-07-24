from __future__ import annotations

import unittest
from unittest.mock import patch

import support  # noqa: F401

from usr.plugins.agent_harness.helpers.lifecycle import (
    create_run_record,
    save_current_run,
)
from usr.plugins.agent_harness.helpers.memory import (
    accept_memory_candidate,
    propose_memory_candidate,
)


class Context:
    def __init__(self):
        self.id = "memory-test"
        self.data = {}
        self.output_data = {}

    def get_data(self, key, recursive=True):
        return self.data.get(key)

    def set_data(self, key, value, recursive=True):
        self.data[key] = value

    def set_output_data(self, key, value, recursive=True):
        self.output_data[key] = value


class MemoryTests(unittest.IsolatedAsyncioTestCase):
    async def test_accepted_rule_persists_only_to_selected_harness_scope(self):
        context = Context()
        run = create_run_record(
            context_id=context.id,
            mode="pro",
            objective="Remember a rule",
            constraints=[],
            settings={"mode_policies": {}},
        )
        candidate = propose_memory_candidate(
            run=run,
            rule_text="Run the focused test first.",
            reason="Fast feedback",
            source="test",
            scope="agent",
            confidence=0.9,
        )
        save_current_run(context, run)

        with (
            patch(
                "usr.plugins.agent_harness.helpers.memory.load_scope_settings",
                return_value={},
            ),
            patch(
                "usr.plugins.agent_harness.helpers.memory.persist_scope_settings",
            ) as persist,
        ):
            accepted = await accept_memory_candidate(
                context=context,
                candidate_id=candidate.id,
                scope="agent",
                agent_profile="developer",
            )

        self.assertEqual(accepted.status, "accepted")
        persisted = persist.call_args.kwargs
        self.assertEqual(persisted["scope"], "agent")
        self.assertEqual(persisted["agent_profile"], "developer")
        self.assertEqual(
            persisted["settings"]["accepted_rules"][0]["rule_text"],
            "Run the focused test first.",
        )

    async def test_invalid_scope_is_rejected(self):
        context = Context()

        with self.assertRaisesRegex(ValueError, "Memory scope"):
            await accept_memory_candidate(
                context=context,
                candidate_id="missing",
                scope="invalid",  # type: ignore[arg-type]
            )


if __name__ == "__main__":
    unittest.main()
