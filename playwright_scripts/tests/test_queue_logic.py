"""Unit tests for local-queue merge, CL gating, and score-cache keying.

Run: .venv/bin/python -m unittest playwright_scripts.tests.test_queue_logic
  (or)  cd playwright_scripts && ../.venv/bin/python -m unittest tests.test_queue_logic
"""

import sys
import unittest
from pathlib import Path

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
