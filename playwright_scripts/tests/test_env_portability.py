"""Tests for the two portability claims: JOBHUNT_ROOT relocates the tree, and the
Claude CLI is discovered rather than assumed to sit at an Apple-Silicon Homebrew path.

Run: cd playwright_scripts && ../.venv/bin/python -m unittest tests.test_env_portability
"""

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = SCRIPTS_DIR.parent
sys.path.insert(0, str(SCRIPTS_DIR))

from lib import sonnet


class JobhuntRootTests(unittest.TestCase):
    """README tells the user to `export JOBHUNT_ROOT="$PWD"`. Prove that it takes.

    The constants are resolved at import time, so this runs a fresh interpreter with the
    env var set rather than reimporting into an already-populated sys.modules.
    """

    def _paths_under(self, root):
        code = (
            "import sys; sys.path.insert(0, %r)\n"
            "import build_local_queue, tailor, verify, serve_tinder, make_crib\n"
            "import lib.base as base, lib.profile as prof, lib.screenshots as ss\n"
            "print(build_local_queue.OUT)\n"
            "print(tailor.APPLICATIONS_DIR)\n"
            "print(verify.MASTER_RESUME)\n"
            "print(serve_tinder.LOCAL_QUEUE_FILE)\n"
            "print(make_crib.DEFAULT_ANSWERS_PATH)\n"
            "print(base.MASTER_RESUME_PDF)\n"
            "print(base.PROFILE_DIR)\n"
            "print(prof.PROFILE_PATH)\n"
            "print(ss.SCREENSHOT_DIR)\n"
        ) % str(SCRIPTS_DIR)
        env = dict(os.environ)
        if root is None:
            env.pop("JOBHUNT_ROOT", None)
        else:
            env["JOBHUNT_ROOT"] = str(root)
        out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                             env=env, cwd=str(SCRIPTS_DIR))
        self.assertEqual(out.returncode, 0, out.stderr)
        return [Path(line) for line in out.stdout.strip().splitlines()]

    def test_every_pipeline_path_moves_with_the_env_var(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "relocated"
            paths = self._paths_under(root)
            self.assertEqual(len(paths), 9)
            for p in paths:
                with self.subTest(path=str(p)):
                    self.assertTrue(p.is_relative_to(root),
                                    f"{p} escaped JOBHUNT_ROOT={root}")

    def test_exact_expected_locations(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "relocated"
            out, apps, master, queue, answers, pdf, browser, profile, shots = \
                self._paths_under(root)
            self.assertEqual(out, root / "applications" / "local_queue.json")
            self.assertEqual(apps, root / "applications")
            self.assertEqual(master, root / "profile" / "master_resume.md")
            self.assertEqual(queue, root / "applications" / "local_queue.json")
            self.assertEqual(answers, root / "profile" / "answers.md")
            self.assertEqual(pdf, root / "profile" / "master_resume.pdf")
            self.assertEqual(browser, root / ".browser-profile" / "comet")
            self.assertEqual(profile, root / "profile" / "candidate_profile_data.json")
            self.assertEqual(shots, root / "screenshots")

    def test_default_is_the_historical_home_layout(self):
        paths = self._paths_under(None)
        expected_root = Path.home() / "JobHunt"
        for p in paths:
            with self.subTest(path=str(p)):
                self.assertTrue(p.is_relative_to(expected_root))

    def test_no_module_hardcodes_the_home_jobhunt_path(self):
        """Guards against a new file reintroducing Path.home() / "JobHunt"."""
        offenders = []
        for py in sorted(REPO_ROOT.rglob("*.py")):
            # Tests legitimately reference the default layout when asserting on it.
            if ".venv" in py.parts or "tests" in py.parts:
                continue
            for lineno, line in enumerate(py.read_text(encoding="utf-8").splitlines(), 1):
                if 'Path.home() / "JobHunt"' not in line:
                    continue
                # Legal only as the fallback inside a JOBHUNT_ROOT lookup.
                if "JOBHUNT_ROOT" in line:
                    continue
                offenders.append(f"{py.relative_to(REPO_ROOT)}:{lineno}")
        self.assertEqual(offenders, [])


class ResolveClaudeBinTests(unittest.TestCase):
    def test_explicit_override_wins(self):
        env = {"CLAUDE_BIN": "/somewhere/custom/claude", "PATH": "/usr/bin"}
        self.assertEqual(sonnet.resolve_claude_bin(env), "/somewhere/custom/claude")

    def test_path_lookup_is_used_before_the_hardcoded_fallbacks(self):
        with tempfile.TemporaryDirectory() as tmp:
            fake = Path(tmp) / "claude"
            fake.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            fake.chmod(0o755)
            resolved = sonnet.resolve_claude_bin({"PATH": tmp})
            self.assertEqual(Path(resolved), fake)
            # The old code returned the Homebrew path unconditionally.
            self.assertNotEqual(resolved, "/opt/homebrew/bin/claude")

    def test_missing_everywhere_raises_a_directive_error(self):
        with tempfile.TemporaryDirectory() as empty:
            # Point every fallback at a directory with nothing in it.
            with mock.patch.object(sonnet, "CLAUDE_BIN_FALLBACKS",
                                   (str(Path(empty) / "claude"),)):
                with self.assertRaises(FileNotFoundError) as ctx:
                    sonnet.resolve_claude_bin({"PATH": empty})
        message = str(ctx.exception)
        self.assertIn("CLAUDE_BIN", message)
        self.assertIn(empty, message)

    def test_apple_silicon_path_is_a_fallback_not_the_only_option(self):
        self.assertIn("/opt/homebrew/bin/claude", sonnet.CLAUDE_BIN_FALLBACKS)
        self.assertIn("/usr/local/bin/claude", sonnet.CLAUDE_BIN_FALLBACKS)
        self.assertGreater(len(sonnet.CLAUDE_BIN_FALLBACKS), 1)


if __name__ == "__main__":
    unittest.main()
