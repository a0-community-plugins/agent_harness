from __future__ import annotations

import importlib
from pathlib import Path
import shutil
import sys

PLUGIN_PACKAGE_PREFIX = "usr.plugins.agent_harness"
PLUGIN_ROOT = Path(__file__).resolve().parent


def install() -> None:
    """Finish installation or update without a separate Execute step."""
    _stop_workers()
    _clear_plugin_modules()
    _clear_plugin_bytecode()


def pre_update() -> None:
    _stop_workers()
    _clear_plugin_modules()
    _clear_plugin_bytecode()


def uninstall() -> None:
    _stop_workers()
    _clear_plugin_modules()
    _clear_plugin_bytecode()


def _stop_workers() -> None:
    try:
        from usr.plugins.agent_harness.helpers.parallel import kill_all_runs

        kill_all_runs()
    except ImportError:
        pass


def _clear_plugin_modules() -> None:
    for module_name in list(sys.modules):
        if module_name == PLUGIN_PACKAGE_PREFIX or module_name.startswith(
            f"{PLUGIN_PACKAGE_PREFIX}."
        ):
            sys.modules.pop(module_name, None)
    importlib.invalidate_caches()


def _clear_plugin_bytecode() -> None:
    for cache_dir in PLUGIN_ROOT.rglob("__pycache__"):
        shutil.rmtree(cache_dir, ignore_errors=True)
