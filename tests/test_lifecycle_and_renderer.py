from __future__ import annotations

import unittest

import support  # noqa: F401

from usr.plugins.agent_harness.helpers.lifecycle import (
    complete_run,
    completion_blocker,
    create_run_record,
    parse_verification_status,
    record_verification,
)
from usr.plugins.agent_harness.helpers.planner import (
    mark_sub_task_completed,
    submit_plan,
)
from usr.plugins.agent_harness.helpers.renderer import render_system_prompt
from usr.plugins.agent_harness.helpers.settings import get_mode_policy


SETTINGS = {
    "ambient_assist_enabled": True,
    "mode_policies": {
        "flash": {"subagent_limit": 0, "repair_limit": 0},
        "standard": {"subagent_limit": 0, "repair_limit": 1},
        "pro": {"subagent_limit": 0, "repair_limit": 1},
        "ultra": {"subagent_limit": 3, "repair_limit": 3},
    },
}


def make_run(mode: str = "pro"):
    return create_run_record(
        context_id="ctx",
        mode=mode,  # type: ignore[arg-type]
        objective="Ship a safe fix",
        constraints=[],
        settings=SETTINGS,
    )


class LifecycleAndRendererTests(unittest.TestCase):
    def test_ambient_assist_renders_without_a_run(self):
        prompt = render_system_prompt(
            settings=SETTINGS,
            run=None,
            accepted_rules=[{"rule_text": "Never edit generated files."}],
        )

        self.assertIn("AMBIENT ASSIST", prompt)
        self.assertIn("Never edit generated files", prompt)

    def test_pro_plan_phase_does_not_demand_parallel_task_graph(self):
        run = make_run("pro")
        run.phase = "plan"

        prompt = render_system_prompt(
            settings=SETTINGS,
            run=run,
            accepted_rules=[],
        )

        self.assertIn("PLANNING PHASE — SINGLE-AGENT", prompt)
        self.assertNotIn('action="dispatch"', prompt)

    def test_ultra_plan_requires_independent_task_graph(self):
        run = make_run("ultra")
        run.phase = "plan"

        prompt = render_system_prompt(
            settings=SETTINGS,
            run=run,
            accepted_rules=[],
        )

        self.assertIn("DECOMPOSE INDEPENDENT WORK", prompt)
        self.assertIn('action="plan"', prompt)

    def test_workers_are_exclusive_to_ultra_and_bounded(self):
        settings = {
            "mode_policies": {
                "pro": {"subagent_limit": 4, "repair_limit": 1},
                "ultra": {"subagent_limit": 99, "repair_limit": 3},
            }
        }

        self.assertEqual(get_mode_policy(settings, "pro")["subagent_limit"], 0)
        self.assertEqual(get_mode_policy(settings, "ultra")["subagent_limit"], 4)

    def test_common_test_runner_summaries_are_recognized(self):
        self.assertEqual(
            parse_verification_status("Ran 4 tests in 0.1s\n\nOK\n"),
            "passed",
        )
        self.assertEqual(
            parse_verification_status("test result: FAILED. 2 passed; 1 failed"),
            "failed",
        )

    def test_completion_requires_successful_tasks_and_passing_verification(self):
        run = make_run("ultra")
        graph = submit_plan(
            run,
            [
                {
                    "title": "Implement",
                    "description": "Make the change",
                    "role": "code",
                    "depends_on": [],
                }
            ],
        )

        self.assertIn("unfinished", completion_blocker(run))
        complete_run(run)
        self.assertEqual(graph.sub_tasks[0].status, "pending")

        run.status = "active"
        run.phase = "implement"
        mark_sub_task_completed(run, "st_1", summary="Implemented")
        self.assertIn("passing verification", completion_blocker(run))

        record_verification(
            run,
            name="unit tests",
            status="passed",
            summary="12 tests passed",
        )
        self.assertEqual(completion_blocker(run), "")


if __name__ == "__main__":
    unittest.main()
