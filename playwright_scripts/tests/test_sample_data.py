"""The committed samples must be what the pipeline actually emits.

The bug this locks down: sample_data/ was hand-written to a
{job_posting, scored, tailored_output, audit} envelope that no code path ever produced.
sample_data/generate_samples.py now runs build_local_queue.main() for real against a stub
model, so the samples cannot drift from the code without this test going red.

Run: cd playwright_scripts && ../.venv/bin/python -m unittest tests.test_sample_data
"""

import json
import subprocess
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SAMPLE_DIR = REPO_ROOT / "sample_data"
GENERATOR = SAMPLE_DIR / "generate_samples.py"

sys.path.insert(0, str(REPO_ROOT / "playwright_scripts"))
import build_local_queue as bq


class SampleDataTests(unittest.TestCase):
    def setUp(self):
        self.queue = json.loads((SAMPLE_DIR / "local_queue.json").read_text(encoding="utf-8"))

    def test_committed_samples_match_a_fresh_pipeline_run(self):
        proc = subprocess.run([sys.executable, str(GENERATOR), "--check"],
                              capture_output=True, text=True, cwd=str(REPO_ROOT))
        self.assertEqual(proc.returncode, 0,
                         f"sample_data is stale, rerun generate_samples.py\n{proc.stdout}\n{proc.stderr}")

    def test_queue_envelope_is_the_shape_serve_tinder_reads(self):
        self.assertEqual(sorted(self.queue), ["pending_review_count", "roles", "today_applied"])
        self.assertEqual(self.queue["pending_review_count"], len(self.queue["roles"]))

    def test_card_keys_are_exactly_what_to_card_emits(self):
        # Build a card through the real function and compare key sets, so a schema change
        # in to_card() that the samples miss fails here.
        expected = set(bq.to_card({"id": "x", "company": "C", "role": "R"}))
        for card in self.queue["roles"]:
            with self.subTest(card=card["id"]):
                self.assertEqual(set(card), expected)

    def test_no_legacy_handwritten_envelope_remains(self):
        for path in SAMPLE_DIR.glob("*.json"):
            data = json.loads(path.read_text(encoding="utf-8"))
            keys = set(data) if isinstance(data, dict) else set()
            with self.subTest(path=path.name):
                self.assertNotIn("tailored_output", keys)
                self.assertNotIn("job_posting", keys)

    def test_every_queued_card_cleared_the_documented_tailored_gate(self):
        # The samples are the README's evidence that the gate is real, so they must
        # themselves satisfy it.
        for card in self.queue["roles"]:
            with self.subTest(card=card["id"]):
                self.assertGreaterEqual(card["fit_score"], bq.TAILORED_FIT_GATE)

    def test_samples_contain_no_absolute_machine_paths(self):
        for path in sorted(SAMPLE_DIR.iterdir()):
            if path.name == "generate_samples.py" or path.is_dir():
                continue
            text = path.read_text(encoding="utf-8")
            with self.subTest(path=path.name):
                self.assertNotIn("/Users/", text)
                self.assertNotIn("/var/folders/", text)
                self.assertNotIn(str(Path.home()), text)


if __name__ == "__main__":
    unittest.main()
