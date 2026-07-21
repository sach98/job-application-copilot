"""Unit tests for local-queue merge, CL gating, and score-cache keying.

Run: .venv/bin/python -m unittest playwright_scripts.tests.test_queue_logic
  (or)  cd playwright_scripts && ../.venv/bin/python -m unittest tests.test_queue_logic
"""

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import build_local_queue as bq
import tailor


class MergeCardsTests(unittest.TestCase):
    def test_carries_unacted_and_drops_acted(self):
        existing = [{"id": "a", "jd_url": "http://x/a"}, {"id": "b", "jd_url": "http://x/b"}]
        acted = {"b"}
        merged = bq.merge_cards(existing, [], acted)
        ids = [c["id"] for c in merged]
        self.assertEqual(ids, ["a"])

    def test_appends_fresh(self):
        existing = [{"id": "a", "jd_url": "http://x/a"}]
        fresh = [{"id": "c", "jd_url": "http://x/c"}]
        merged = bq.merge_cards(existing, fresh, set())
        self.assertEqual([c["id"] for c in merged], ["a", "c"])

    def test_dedupes_by_id(self):
        existing = [{"id": "a", "jd_url": "http://x/a"}]
        fresh = [{"id": "a", "jd_url": "http://different"}]
        merged = bq.merge_cards(existing, fresh, set())
        self.assertEqual(len(merged), 1)

    def test_dedupes_by_jd_url_ignoring_trailing_slash(self):
        existing = [{"id": "a", "jd_url": "http://x/job/"}]
        fresh = [{"id": "b", "jd_url": "http://x/job"}]
        merged = bq.merge_cards(existing, fresh, set())
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]["id"], "a")

    def test_acted_drops_fresh_too(self):
        fresh = [{"id": "z", "jd_url": "http://x/z"}]
        merged = bq.merge_cards([], fresh, {"z"})
        self.assertEqual(merged, [])


class CoverLetterGateTests(unittest.TestCase):
    def test_true_phrasings(self):
        wants = [
            "Please submit a cover letter with your application.",
            "A covering letter is required.",
            "Include a letter of motivation.",
            "Attach a brief letter explaining your interest.",
            "Tell us why you want to work here.",
            "In a statement of purpose, describe your goals.",
            "Explain why you are a good fit for this role.",
        ]
        for jd in wants:
            with self.subTest(jd=jd):
                self.assertTrue(tailor.jd_wants_cover_letter(jd))

    def test_false_phrasings(self):
        no = [
            "Responsibilities include building dashboards in SQL and Python.",
            "5+ years of experience in business analysis.",
            "",
            None,
            "Submit your resume and references.",
        ]
        for jd in no:
            with self.subTest(jd=jd):
                self.assertFalse(tailor.jd_wants_cover_letter(jd))


class CoverLetterProductionBehaviourTests(unittest.TestCase):
    """jd_wants_cover_letter is a detector, not the production decision.

    tailor.run() hardcodes wants_cl = True so a cover letter is always ready to attach.
    That is deliberate, so pin it: the detector's verdict must not change what run() writes.
    """

    TAILORED = {
        "tailored_resume_markdown": "# Candidate\n\n" + ("real resume content. " * 20),
        "cover_letter": "Dear Hiring Team, this is the drafted cover letter body.",
        "fit_summary_3_bullets": ["a", "b", "c"],
        "tailored_resume_bullets": ["one", "two", "three"],
    }

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def _run(self, jd):
        role = {"id": "cl-role", "company": "Acme", "role": "BA", "jd_text": jd}
        with patch.object(tailor, "call_claude", lambda *a, **k: dict(self.TAILORED)), \
             patch.object(tailor, "APPLICATIONS_DIR", self.tmp), \
             patch.object(tailor, "md_to_pdf", lambda p: None):
            merged = tailor.run(role)
        return merged, self.tmp / "cl-role"

    def test_cover_letter_written_even_when_the_jd_never_asks(self):
        jd = "Responsibilities include building dashboards in SQL and Python."
        self.assertFalse(tailor.jd_wants_cover_letter(jd))  # detector says no
        merged, out_dir = self._run(jd)
        self.assertTrue((out_dir / "cover_letter.md").is_file(),
                        "run() must write a cover letter regardless of the detector")
        self.assertIn("drafted cover letter body", merged["cl_preview"])
        self.assertNotEqual(merged["cl_url"], "")

    def test_cover_letter_written_when_the_jd_does_ask(self):
        jd = "Please submit a cover letter with your application."
        self.assertTrue(tailor.jd_wants_cover_letter(jd))
        merged, out_dir = self._run(jd)
        self.assertTrue((out_dir / "cover_letter.md").is_file())
        self.assertIn("drafted cover letter body", merged["cl_preview"])

    def test_the_detector_does_not_influence_the_written_artifacts(self):
        asks = self._run("Please submit a cover letter.")[1] / "cover_letter.md"
        asks_text = asks.read_text(encoding="utf-8")
        shutil.rmtree(self.tmp, ignore_errors=True)
        self.tmp.mkdir(parents=True, exist_ok=True)
        silent = self._run("No mention of any letter here at all.")[1] / "cover_letter.md"
        self.assertEqual(asks_text, silent.read_text(encoding="utf-8"))


class CarriedCardRegateTests(unittest.TestCase):
    """Every build re-applies the queue bar to carried-over cards.

    Carried cards are never re-tailored, so this filter is the ONLY thing that can evict a
    card written by an older build under a laxer gate. These tests drive main() end to end
    with an empty jobs file, so the carry-over path is the only code that runs and the
    written local_queue.json is the oracle.
    """

    # Hand-computed against the default tailored gate of 0.80.
    CARRIED = [
        # 0.88 clears the gate outright.
        {"id": "keep-ncr", "jd_url": "http://x/1", "fit_score": 0.88, "location": "Gurgaon"},
        # 0.79 is below the gate but at/above the 0.78 pre-tailor standout threshold. It
        # must NOT survive: standout is a pre-tailor concession, not a queue bar.
        {"id": "drop-standout", "jd_url": "http://x/2", "fit_score": 0.79, "location": "Chennai"},
        # 0.65 clears the 0.60 pre-tailor floor in NCR but not the 0.80 gate. It must NOT
        # survive: re-gating at the pre-tailor floor would be no gate at all.
        {"id": "drop-prefloor", "jd_url": "http://x/3", "fit_score": 0.65, "location": "Noida"},
        # Exactly at the gate, non-NCR. Location was settled before tailoring, so it stays.
        {"id": "keep-boundary", "jd_url": "http://x/4", "fit_score": 0.80, "location": "Mumbai"},
    ]

    def build(self, carried, gate=None):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        jobs_file = tmp / "jobs.json"
        jobs_file.write_text("[]", encoding="utf-8")  # no fresh jobs: carry-over path only
        out = tmp / "local_queue.json"
        argv = ["build_local_queue.py", "--jobs", str(jobs_file)]
        if gate is not None:
            argv += ["--tailored-gate", str(gate)]
        with patch.object(bq, "load_existing_cards", return_value=[dict(c) for c in carried]), \
             patch.object(bq, "load_acted_ids", return_value=set()), \
             patch.object(bq, "today_applied_count", return_value=0), \
             patch.object(bq, "load_score_cache", return_value={}), \
             patch.object(bq, "SCORE_CACHE", tmp / "_score_cache.json"), \
             patch.object(bq, "OUT", out), \
             patch.object(bq, "log", lambda msg: None), \
             patch.object(sys, "argv", argv):
            self.assertEqual(bq.main(), 0)
        return json.loads(out.read_text(encoding="utf-8"))

    def test_only_cards_at_or_above_the_gate_are_written_back(self):
        payload = self.build(self.CARRIED)
        self.assertEqual([c["id"] for c in payload["roles"]], ["keep-ncr", "keep-boundary"])

    def test_the_count_the_app_shows_matches_the_surviving_cards(self):
        payload = self.build(self.CARRIED)
        self.assertEqual(payload["pending_review_count"], 2)

    def test_raising_the_gate_evicts_cards_the_old_gate_admitted(self):
        # The regression this filter exists to stop: a 0.83 card queued under a 0.80 gate
        # must disappear once the gate moves to 0.85.
        card = [{"id": "old", "jd_url": "http://x/9", "fit_score": 0.83, "location": "Delhi"}]
        self.assertEqual([c["id"] for c in self.build(card)["roles"]], ["old"])
        self.assertEqual(self.build(card, gate=0.85)["roles"], [])

    def test_lowering_the_gate_admits_a_card_the_old_gate_rejected(self):
        card = [{"id": "near", "jd_url": "http://x/8", "fit_score": 0.72, "location": "Delhi"}]
        self.assertEqual(self.build(card)["roles"], [])
        self.assertEqual([c["id"] for c in self.build(card, gate=0.70)["roles"]], ["near"])


class ScoreCacheKeyTests(unittest.TestCase):
    def test_key_stable_for_same_inputs(self):
        job = {"id": "42", "jd_text": "Analyze data and report."}
        self.assertEqual(bq._cache_key(job), bq._cache_key(dict(job)))

    def test_key_changes_when_jd_changes(self):
        a = bq._cache_key({"id": "42", "jd_text": "one"})
        b = bq._cache_key({"id": "42", "jd_text": "two"})
        self.assertNotEqual(a, b)

    def test_key_changes_when_id_changes(self):
        a = bq._cache_key({"id": "1", "jd_text": "same"})
        b = bq._cache_key({"id": "2", "jd_text": "same"})
        self.assertNotEqual(a, b)

    def test_cache_hit_reuses_score(self):
        job = {"id": "9", "jd_text": "JD body"}
        cache = {bq._cache_key(job): {"fit_score": 0.73}}
        cached = cache.get(bq._cache_key(job))
        self.assertIsNotNone(cached)
        self.assertEqual(cached["fit_score"], 0.73)


if __name__ == "__main__":
    unittest.main()
