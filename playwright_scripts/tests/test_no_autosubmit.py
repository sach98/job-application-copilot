"""Regression tests for the "nothing auto-submits" promise in README.md.

The bug these lock down: n8n_workflows/apply.json routed an "apply" swipe straight into
the Playwright dispatcher with --submit hardcoded, so a swipe could click a real submit
button with no human in the loop. Two independent guards now enforce the promise:
  1. the workflow does not pass --submit at all
  2. --submit is inert unless a human exported JOBHUNT_ALLOW_AUTOSUBMIT=1

Run: cd playwright_scripts && ../.venv/bin/python -m unittest tests.test_no_autosubmit
"""

import json
import sys
import unittest
from unittest.mock import patch
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import apply as apply_mod

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS_DIR = REPO_ROOT / "n8n_workflows"


class SubmitAllowedTests(unittest.TestCase):
    VAR = apply_mod.AUTOSUBMIT_ENV_VAR

    def test_no_flag_means_no_submit_whatever_the_env_says(self):
        self.assertFalse(apply_mod.submit_allowed(False, {self.VAR: "1"}))
        self.assertFalse(apply_mod.submit_allowed(False, {}))

    def test_flag_alone_is_not_enough(self):
        # This is the exact scenario the workflow used to create: an automated caller
        # passes --submit with no human present.
        self.assertFalse(apply_mod.submit_allowed(True, {}))

    def test_flag_plus_explicit_human_optin_submits(self):
        self.assertTrue(apply_mod.submit_allowed(True, {self.VAR: "1"}))

    def test_near_miss_env_values_do_not_count_as_optin(self):
        for value in ["", "0", "true", "TRUE", "yes", "y", "2", " 1", "1 ", "on"]:
            with self.subTest(value=value):
                self.assertFalse(apply_mod.submit_allowed(True, {self.VAR: value}))


class DispatcherWiringTests(unittest.TestCase):
    """End to end through apply.main(): what command actually reaches subprocess.run?

    submit_allowed() being correct is not enough. main() has to consult it rather than the
    raw argparse flag, so these drive the real CLI path and inspect the dispatched argv.
    """

    ARGV = ["apply.py", "--url", "https://boards.greenhouse.io/acme/jobs/1",
            "--job-id", "j1", "--company", "Acme", "--role", "BA",
            "--webhook", "http://localhost:5678/webhook/jobhunt/api"]

    def _dispatch(self, extra_argv, env):
        captured = {}

        class FakeResult:
            returncode = 0

        def fake_run(cmd, *a, **k):
            captured["cmd"] = list(cmd)
            return FakeResult()

        with patch.object(apply_mod.subprocess, "run", fake_run), \
             patch.object(apply_mod.sys, "argv", self.ARGV + extra_argv), \
             patch.dict(apply_mod.os.environ, env, clear=False):
            for key in [apply_mod.AUTOSUBMIT_ENV_VAR]:
                if key not in env:
                    apply_mod.os.environ.pop(key, None)
            with self.assertRaises(SystemExit) as ctx:
                apply_mod.main()
        self.assertEqual(ctx.exception.code, 0)
        return captured["cmd"]

    def test_plain_run_never_passes_submit_downstream(self):
        cmd = self._dispatch([], {})
        self.assertNotIn("--submit", cmd)
        self.assertIn("greenhouse.py", " ".join(cmd))

    def test_submit_flag_without_optin_is_stripped_before_dispatch(self):
        # This is the exact hole the n8n workflow used to open.
        cmd = self._dispatch(["--submit"], {})
        self.assertNotIn("--submit", cmd)

    def test_submit_flag_with_a_near_miss_env_value_is_stripped(self):
        cmd = self._dispatch(["--submit"], {apply_mod.AUTOSUBMIT_ENV_VAR: "true"})
        self.assertNotIn("--submit", cmd)

    def test_submit_reaches_the_bot_only_with_the_explicit_human_optin(self):
        cmd = self._dispatch(["--submit"], {apply_mod.AUTOSUBMIT_ENV_VAR: "1"})
        self.assertIn("--submit", cmd)

    def test_optin_alone_does_not_submit_without_the_flag(self):
        cmd = self._dispatch([], {apply_mod.AUTOSUBMIT_ENV_VAR: "1"})
        self.assertNotIn("--submit", cmd)


class WorkflowDoesNotAutoSubmitTests(unittest.TestCase):
    def _command_nodes(self, workflow_path):
        data = json.loads(workflow_path.read_text(encoding="utf-8"))
        return [(n.get("name", ""), n.get("parameters", {}).get("command", ""))
                for n in data.get("nodes", [])
                if n.get("type") == "n8n-nodes-base.executeCommand"]

    def test_apply_workflow_dispatches_the_bot_without_submit(self):
        nodes = self._command_nodes(WORKFLOWS_DIR / "apply.json")
        dispatch = [c for name, c in nodes if "apply.py" in c]
        self.assertEqual(len(dispatch), 1, "expected exactly one apply.py dispatch node")
        self.assertNotIn("--submit", dispatch[0])
        # The node must still actually dispatch, so this is not passing by deletion.
        self.assertIn("--job-id", dispatch[0])
        self.assertIn("--webhook", dispatch[0])

    def test_no_shipped_workflow_passes_submit(self):
        for workflow in sorted(WORKFLOWS_DIR.glob("*.json")):
            for name, command in self._command_nodes(workflow):
                with self.subTest(workflow=workflow.name, node=name):
                    self.assertNotIn("--submit", command)

    def test_no_shipped_workflow_sets_the_optin_env_var(self):
        # A workflow could otherwise re-open the hole by exporting the opt-in itself.
        for workflow in sorted(WORKFLOWS_DIR.glob("*.json")):
            with self.subTest(workflow=workflow.name):
                self.assertNotIn(apply_mod.AUTOSUBMIT_ENV_VAR,
                                 workflow.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
