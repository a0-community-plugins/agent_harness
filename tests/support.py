from __future__ import annotations

import os
from collections import OrderedDict
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
import sys
from types import ModuleType


PROJECT_ROOT = Path(
    os.getenv("A0_TEST_PROJECT_ROOT", Path(__file__).resolve().parents[4])
).resolve()
PLUGIN_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _install_core_stubs() -> None:
    helpers = ModuleType("helpers")
    helpers.__path__ = []  # type: ignore[attr-defined]

    files = ModuleType("helpers.files")
    files.USER_DIR = "usr"
    files.PLUGINS_DIR = "plugins"
    files.get_abs_path = lambda *parts: str(Path(*map(str, parts)))
    files.exists = lambda path: Path(path).exists()
    files.read_file = lambda path: Path(path).read_text(encoding="utf-8")

    plugins = ModuleType("helpers.plugins")
    plugins.CONFIG_DEFAULT_FILE_NAME = "default_config.yaml"
    plugins.CONFIG_FILE_NAME = "config.json"
    plugins.find_plugin_dir = (
        lambda plugin_name: str(PLUGIN_ROOT) if plugin_name == "agent_harness" else ""
    )
    plugins.determine_plugin_asset_path = (
        lambda plugin_name, project_name, agent_profile, filename: str(
            PLUGIN_ROOT / filename
        )
    )

    projects = ModuleType("helpers.projects")
    projects.get_context_project_name = lambda context: ""

    yaml_helper = ModuleType("helpers.yaml")
    yaml_helper.loads = lambda value: {}

    extension = ModuleType("helpers.extension")

    class Extension:
        def __init__(self, agent=None):
            self.agent = agent

    extension.Extension = Extension

    helpers.files = files
    helpers.plugins = plugins
    helpers.projects = projects
    helpers.yaml = yaml_helper
    helpers.extension = extension

    agent = ModuleType("agent")

    class AgentContext:
        def __init__(self):
            self.data = {}
            self.output_data = {}
            self.id = "test-context"

        def get_data(self, key, recursive=True):
            return self.data.get(key)

        def set_data(self, key, value, recursive=True):
            self.data[key] = value

        def set_output_data(self, key, value, recursive=True):
            self.output_data[key] = value

        @staticmethod
        def remove(context_id):
            return None

    class Agent:
        DATA_NAME_SUPERIOR = "_superior"
        DATA_NAME_SUBORDINATE = "_subordinate"

        def __init__(self, context=None):
            self.context = context or AgentContext()

    class LoopData:
        def __init__(self):
            self.extras_persistent = OrderedDict()

    class AgentContextType(Enum):
        USER = "user"
        BACKGROUND = "background"

    @dataclass
    class UserMessage:
        message: str
        attachments: list[str]

    agent.Agent = Agent
    agent.AgentContext = AgentContext
    agent.AgentContextType = AgentContextType
    agent.LoopData = LoopData
    agent.UserMessage = UserMessage

    defer = ModuleType("helpers.defer")

    class DeferredTask:
        def __init__(self, thread_name="Background"):
            self.thread_name = thread_name

    defer.DeferredTask = DeferredTask
    helpers.defer = defer

    initialize = ModuleType("initialize")
    initialize.initialize_agent = lambda: object()

    sys.modules.update(
        {
            "helpers": helpers,
            "helpers.files": files,
            "helpers.plugins": plugins,
            "helpers.projects": projects,
            "helpers.yaml": yaml_helper,
            "helpers.extension": extension,
            "helpers.defer": defer,
            "agent": agent,
            "initialize": initialize,
        }
    )


if os.getenv("A0_TEST_USE_REAL_CORE") != "1":
    _install_core_stubs()
