from __future__ import annotations

import unittest

import support  # noqa: F401

from usr.plugins.agent_harness.helpers.guardrails import (
    assess_tool_guardrail_decision,
    decide_checkpoint,
    request_checkpoint,
)
from usr.plugins.agent_harness.helpers.lifecycle import create_run_record


SETTINGS = {
    "dependency_install_requires_checkpoint": True,
    "destructive_actions_require_checkpoint": True,
    "git_mutations_require_checkpoint": True,
    "max_auto_edit_files": 8,
    "protected_paths": ["agent.py", "initialize.py", "usr/plugins/"],
    "mode_policies": {
        "pro": {"subagent_limit": 0, "repair_limit": 1},
    },
}


def make_run():
    return create_run_record(
        context_id="ctx",
        mode="pro",
        objective="Test the guardrails",
        constraints=[],
        settings=SETTINGS,
    )


class GuardrailTests(unittest.TestCase):
    def test_approved_command_is_action_bound_and_single_use(self):
        run = make_run()
        checkpoint = request_checkpoint(
            run,
            reason="Install requirements",
            proposed_action="pip install -r requirements.txt",
            tool_name="code_execution_tool",
            tool_args={
                "runtime": "terminal",
                "code": "pip install -r requirements.txt",
            },
            risk_level="high",
        )
        decide_checkpoint(
            run,
            checkpoint_id=checkpoint.id,
            decision="approved",
        )

        actual_args = {
            "runtime": "terminal",
            "code": "pip install -r requirements.txt",
            "session": 0,
            "reset": False,
            "allow_running": False,
        }
        first = assess_tool_guardrail_decision(
            run=run,
            tool_name="code_execution_tool",
            tool_args=actual_args,
            settings=SETTINGS,
        )
        second = assess_tool_guardrail_decision(
            run=run,
            tool_name="code_execution_tool",
            tool_args=actual_args,
            settings=SETTINGS,
        )

        self.assertIs(first.approved_checkpoint, checkpoint)
        self.assertTrue(checkpoint.consumed_at)
        self.assertIs(second.denied_checkpoint, checkpoint)
        self.assertIn("already consumed", second.denial_reason)

    def test_pending_checkpoint_stops_unrelated_tools(self):
        run = make_run()
        checkpoint = request_checkpoint(
            run,
            reason="Install dependency",
            proposed_action="pip install rich",
            tool_name="code_execution_tool",
            tool_args={"runtime": "terminal", "code": "pip install rich"},
            risk_level="high",
        )

        assessment = assess_tool_guardrail_decision(
            run=run,
            tool_name="text_editor",
            tool_args={"path": "README.md"},
            settings=SETTINGS,
        )

        self.assertIs(assessment.denied_checkpoint, checkpoint)
        self.assertIn("still pending", assessment.denial_reason)

    def test_protected_directory_uses_path_boundaries(self):
        protected_run = make_run()
        protected = assess_tool_guardrail_decision(
            run=protected_run,
            tool_name="text_editor",
            tool_args={
                "action": "patch",
                "path": "usr/plugins/example/main.py",
                "old_text": "old",
                "new_text": "new",
            },
            settings=SETTINGS,
        )

        similar_run = make_run()
        similar = assess_tool_guardrail_decision(
            run=similar_run,
            tool_name="text_editor",
            tool_args={
                "action": "patch",
                "path": "usr/plugins_backup/example/main.py",
                "old_text": "old",
                "new_text": "new",
            },
            settings=SETTINGS,
        )

        self.assertIsNotNone(protected.checkpoint)
        self.assertIsNone(similar.checkpoint)

    def test_reading_a_protected_path_does_not_request_approval(self):
        run = make_run()

        assessment = assess_tool_guardrail_decision(
            run=run,
            tool_name="text_editor",
            tool_args={"action": "read", "path": "agent.py"},
            settings=SETTINGS,
        )

        self.assertIsNone(assessment.checkpoint)

    def test_read_only_git_is_allowed_but_commit_requires_approval(self):
        status_run = make_run()
        status = assess_tool_guardrail_decision(
            run=status_run,
            tool_name="code_execution_tool",
            tool_args={"runtime": "terminal", "code": "git status --short"},
            settings=SETTINGS,
        )

        commit_run = make_run()
        commit = assess_tool_guardrail_decision(
            run=commit_run,
            tool_name="code_execution_tool",
            tool_args={"runtime": "terminal", "code": "git commit -m 'fix'"},
            settings=SETTINGS,
        )

        self.assertIsNone(status.checkpoint)
        self.assertIsNotNone(commit.checkpoint)
        self.assertIn("repository-changing Git", commit.checkpoint.reason)

    def test_python_module_pip_install_requires_approval(self):
        run = make_run()

        assessment = assess_tool_guardrail_decision(
            run=run,
            tool_name="code_execution_tool",
            tool_args={
                "runtime": "terminal",
                "code": "python3 -m pip install -r requirements.txt",
            },
            settings=SETTINGS,
        )

        self.assertIsNotNone(assessment.checkpoint)
        self.assertIn("dependency install", assessment.checkpoint.reason)


if __name__ == "__main__":
    unittest.main()
