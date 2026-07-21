"""Every threshold a doc states must be the one the code actually uses.

This whole remediation existed because README.md and prompts/scoring.md described an
"honest 0.80 gate on the TAILORED result" that no code implemented. These tests make the
docs falsifiable: change a default in build_local_queue.py without updating the docs and
the suite goes red.

Run: cd playwright_scripts && ../.venv/bin/python -m unittest tests.test_docs_match_code
"""

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "playwright_scripts"))

import build_local_queue as bq


def cli_defaults():
    """The real defaults, parsed out of the shipped parser itself.

    This MUST NOT rebuild the parser: a hand-copied duplicate would let a default drift in
    build_local_queue.py while these tests kept asserting against the stale copy. Every
    number below therefore comes from the same argparse object main() runs on.
    """
    return bq.build_parser().parse_args(["--jobs", "x"])


class ReadmeThresholdsTests(unittest.TestCase):
    def setUp(self):
        self.readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
        self.defaults = cli_defaults()

    def test_readme_gate_table_states_the_real_defaults(self):
        # The table row for each gate must carry that gate's actual numeric default.
        rows = [l for l in self.readme.splitlines() if l.startswith("| ")]
        pre = next(l for l in rows if "Pre-tailor floor" in l)
        tailored = next(l for l in rows if "Tailored-fit gate" in l)
        self.assertIn(f"{self.defaults.min_fit:.2f}", pre)
        self.assertIn("--min-fit", pre)
        self.assertIn(f"{self.defaults.tailored_gate:.2f}", tailored)
        self.assertIn("--tailored-gate", tailored)

    def test_readme_quotes_the_real_standout_and_retry_numbers(self):
        self.assertIn(f"{self.defaults.standout_fit:.2f}", self.readme)
        self.assertIn(f"{bq.RETRY_LOW:.2f}", self.readme)

    def test_readme_names_the_functions_that_implement_each_gate(self):
        for symbol in ["_keep", "tailor_and_gate", "_at_or_above_gate",
                       "--tailored-gate", "--min-fit"]:
            with self.subTest(symbol=symbol):
                self.assertIn(symbol, self.readme)
        self.assertTrue(hasattr(bq, "_keep"))
        self.assertTrue(hasattr(bq, "tailor_and_gate"))
        self.assertTrue(hasattr(bq, "_at_or_above_gate"))

    def test_readme_does_not_claim_the_standout_concession_applies_to_the_re_gate(self):
        """The re-gate must not be described as reusing --standout-fit.

        standout (0.78) is below the tailored gate (0.80), so a re-gate honouring it would
        readmit stale 0.78-0.799 cards. Assert the ordering the prose relies on, so this
        paragraph goes stale loudly if either threshold ever moves.
        """
        self.assertLess(self.defaults.standout_fit, self.defaults.tailored_gate)
        self.assertFalse(bq._at_or_above_gate({"fit_score": self.defaults.standout_fit},
                                              self.defaults.tailored_gate))

    def test_readme_autosubmit_variable_is_the_one_apply_py_reads(self):
        import apply as apply_mod
        self.assertIn(apply_mod.AUTOSUBMIT_ENV_VAR, self.readme)

    def test_readme_sample_run_figures_match_the_committed_samples(self):
        import json
        queue = json.loads((REPO_ROOT / "sample_data" / "local_queue.json").read_text(encoding="utf-8"))
        scraped = json.loads((REPO_ROOT / "sample_data" / "scraped_jobs.json").read_text(encoding="utf-8"))
        self.assertEqual(len(scraped), 4, "README says four synthetic postings")
        self.assertEqual(len(queue["roles"]), 2, "README says two are queued")
        scores = sorted((c["fit_score"] for c in queue["roles"]), reverse=True)
        self.assertEqual(scores, [0.88, 0.83], "README quotes 0.88 and 0.83")
        for value in ["four synthetic postings", "0.88", "0.83", "0.71"]:
            with self.subTest(value=value):
                self.assertIn(value, self.readme)


class ScoringPromptTests(unittest.TestCase):
    def test_scoring_prompt_no_longer_claims_to_be_the_queue_bar(self):
        text = (REPO_ROOT / "prompts" / "scoring.md").read_text(encoding="utf-8")
        self.assertNotIn("an 80% gate depends on this", text)
        self.assertIn("PRE-FILTER", text)
        self.assertIn("--min-fit", text)
        self.assertIn("--tailored-gate", text)

    def test_verify_prompt_declares_itself_the_queue_bar(self):
        text = (REPO_ROOT / "prompts" / "verify_resume.md").read_text(encoding="utf-8")
        self.assertIn("--tailored-gate", text)
        self.assertIn(f"{bq.TAILORED_FIT_GATE:.2f}", text)
        self.assertIn("tailor_and_gate", text)


class NoDashesTests(unittest.TestCase):
    """House style: no em dashes or en dashes in any tracked file."""

    def test_repo_has_no_literal_em_or_en_dashes(self):
        offenders = []
        for path in sorted(REPO_ROOT.rglob("*")):
            if not path.is_file() or any(s in path.parts for s in (".git", ".venv", "__pycache__")):
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            for lineno, line in enumerate(text.splitlines(), 1):
                if chr(0x2013) in line or chr(0x2014) in line:
                    offenders.append(f"{path.relative_to(REPO_ROOT)}:{lineno}")
        self.assertEqual(offenders, [])


if __name__ == "__main__":
    unittest.main()
