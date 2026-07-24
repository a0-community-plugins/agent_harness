from __future__ import annotations

from copy import deepcopy
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import support  # noqa: F401

from usr.plugins.agent_harness.helpers import parallel
from usr.plugins.agent_harness.helpers.lifecycle import create_run_record
from usr.plugins.agent_harness.helpers.models import (
    PARALLEL_WORKER_CONTEXT_KEY,
    RUN_CONTEXT_KEY,
    SubTask,
)


SETTINGS = {
    "mode_policies": {
        "ultra": {"subagent_limit": 3, "repair_limit": 3},
        "flash": {"subagent_limit": 0, "repair_limit": 0},
    }
}


class FakeAgent:
    def __init__(self, context):
        self.context = context
        self.messages = []

    def hist_add_user_message(self, message):
        self.messages.append(message)

    async def monologue(self):
        return "done"


class FakeContext:
    next_id = 0
    removed = []

    def __init__(self, config, type=None, set_current=False, data=None):
        self.__class__.next_id += 1
        self.id = f"worker-{self.__class__.next_id}"
        self.config = config
        self.data = data or {}
        self.output_data = {}
        self.agent0 = FakeAgent(self)

    def get_data(self, key, recursive=True):
        return self.data.get(key)

    def set_data(self, key, value, recursive=True):
        self.data[key] = value

    def set_output_data(self, key, value, recursive=True):
        self.output_data[key] = value

    @classmethod
    def remove(cls, context_id):
        cls.removed.append(context_id)


class FakeDeferred:
    def __init__(self, thread_name="Background"):
        self.thread_name = thread_name
        self.started = False
        self.killed = False

    def start_task(self, function):
        self.started = True
        self.function = function
        return self

    def is_ready(self):
        return False

    def kill(self, terminate_thread=False):
        self.killed = bool(terminate_thread)


def make_run(run_id: str):
    run = create_run_record(
        context_id=f"ctx-{run_id}",
        mode="ultra",
        objective="Parallel test",
        constraints=[],
        settings=SETTINGS,
    )
    run.run_id = run_id
    return run


def make_task():
    return SubTask(
        id="st_1",
        title="Inspect",
        description="Read the relevant code",
        role="research",
    )


class ParallelTests(unittest.TestCase):
    def setUp(self):
        parallel._active_tasks.clear()
        FakeContext.removed = []

    def tearDown(self):
        parallel._active_tasks.clear()

    def test_same_subtask_id_is_isolated_between_runs(self):
        parent = SimpleNamespace(
            config=SimpleNamespace(profile="selected"),
            data={"model": {"provider": "test"}},
        )
        first_run = make_run("run-a")
        second_run = make_run("run-b")
        first_task = make_task()
        second_task = make_task()

        with (
            patch.object(parallel, "AgentContext", FakeContext),
            patch.object(parallel, "DeferredTask", FakeDeferred),
        ):
            parallel.spawn_parallel(
                first_run,
                [first_task],
                SETTINGS,
                parent_context=parent,
            )
            parallel.spawn_parallel(
                second_run,
                [second_task],
                SETTINGS,
                parent_context=parent,
            )

            self.assertEqual(parallel.registered_task_ids("run-a"), {"st_1"})
            self.assertEqual(parallel.registered_task_ids("run-b"), {"st_1"})
            self.assertEqual(len(parallel._active_tasks), 2)

            first_worker = parallel._active_tasks["run-a:st_1"]
            self.assertEqual(first_worker.context.config.profile, "selected")
            self.assertEqual(
                first_worker.context.data["model"],
                deepcopy(parent.data["model"]),
            )
            self.assertIn(RUN_CONTEXT_KEY, first_worker.context.data)
            self.assertEqual(
                first_worker.context.data[PARALLEL_WORKER_CONTEXT_KEY]["sub_task_id"],
                "st_1",
            )

            self.assertEqual(parallel.kill_all("run-a"), 1)
            self.assertEqual(parallel.registered_task_ids("run-a"), set())
            self.assertEqual(parallel.registered_task_ids("run-b"), {"st_1"})


if __name__ == "__main__":
    unittest.main()
