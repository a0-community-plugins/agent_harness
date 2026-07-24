from __future__ import annotations

from pathlib import Path
import unittest

import support


PLUGIN_ROOT = support.PLUGIN_ROOT


class RepositoryContractTests(unittest.TestCase):
    def test_standalone_plugin_metadata_is_present(self):
        for filename in (
            "plugin.yaml",
            "plugin.json",
            "README.md",
            "LICENSE",
            "hooks.py",
        ):
            self.assertTrue((PLUGIN_ROOT / filename).is_file(), filename)
        manifest = (PLUGIN_ROOT / "plugin.yaml").read_text(encoding="utf-8")
        self.assertIn("version: 2.0.0", manifest)

    def test_runtime_config_is_not_tracked_as_distribution_content(self):
        self.assertFalse((PLUGIN_ROOT / "config.json").exists())
        self.assertIn(
            "config.json",
            (PLUGIN_ROOT / ".gitignore").read_text(encoding="utf-8"),
        )

    def test_runtime_prompt_injects_full_harness_contract(self):
        source = (
            PLUGIN_ROOT
            / "extensions"
            / "python"
            / "message_loop_prompts_after"
            / "_20_harness_runtime.py"
        ).read_text(encoding="utf-8")

        self.assertIn("render_system_prompt", source)
        self.assertNotIn("render_runtime_summary(run)", source)

    def test_dashboard_has_no_runtime_cdn_dependency(self):
        dashboard = (PLUGIN_ROOT / "webui" / "dashboard.html").read_text(
            encoding="utf-8"
        )

        self.assertNotIn("cdn.jsdelivr.net", dashboard)
        self.assertIn("overflow-wrap: anywhere", dashboard)

    def test_observability_canvas_and_theme_native_entrypoints_are_registered(self):
        canvas = (PLUGIN_ROOT / "webui" / "canvas.html").read_text(
            encoding="utf-8"
        )
        status_control = (
            PLUGIN_ROOT
            / "extensions"
            / "webui"
            / "chat-input-progress-start"
            / "agent-harness-status.html"
        ).read_text(encoding="utf-8")
        surface = (
            PLUGIN_ROOT
            / "extensions"
            / "webui"
            / "surfaces_register"
            / "_20_register_agent_harness.js"
        ).read_text(encoding="utf-8")
        panel = (
            PLUGIN_ROOT
            / "extensions"
            / "webui"
            / "right-canvas-panels"
            / "_20_agent_harness_panel.html"
        ).read_text(encoding="utf-8")

        self.assertIn("Ultra task graph", canvas)
        self.assertIn("Approval gates", canvas)
        self.assertIn("overflow-x: hidden", canvas)
        self.assertIn(".ahc-sync {", canvas)
        self.assertIn("appearance: none", canvas)
        self.assertIn("background: transparent", canvas)
        self.assertIn("openObservability()", status_control)
        self.assertIn("agent-harness-toolbar-button", status_control)
        self.assertNotIn("btn btn-secondary", status_control)
        self.assertNotIn("openModal(", status_control)
        self.assertIn('id: "agent-harness"', surface)
        self.assertIn('data-surface-id="agent-harness"', panel)

    def test_store_rejects_stale_chat_state(self):
        source = (PLUGIN_ROOT / "webui" / "harness-store.js").read_text(
            encoding="utf-8"
        )
        self.assertIn("_requestSequence", source)
        self.assertIn("_inflightContext", source)
        self.assertIn("currentContextId() !== contextId", source)
        self.assertIn('canvas.open("agent-harness")', source)

    def test_obsolete_manual_setup_scripts_are_removed(self):
        self.assertFalse((PLUGIN_ROOT / "Install.md").exists())
        self.assertFalse((PLUGIN_ROOT / "execute.py").exists())

    def test_readme_matches_current_storage_and_renderer_contracts(self):
        readme = (PLUGIN_ROOT / "README.md").read_text(encoding="utf-8")
        self.assertNotIn("Project-backed workspaces", readme)
        self.assertNotIn("Mermaid graph", readme)
        self.assertIn("There is no separate Execute step.", readme)
        self.assertIn("Pro and Ultra are intentionally different", readme)


if __name__ == "__main__":
    unittest.main()
