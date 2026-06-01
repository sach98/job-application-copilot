"""Unit tests for referral contact filtering logic in enrich_linkedin.py.

Run: cd playwright_scripts && ../.venv/bin/python -m unittest tests.test_referral_filter -v
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import enrich_linkedin as el


class ReferralFilterTests(unittest.TestCase):
    def test_exact_company_match(self):
        # exact-company match True
        self.assertTrue(el.title_matches_company("Business Analyst at Deloitte", "Deloitte"))
        self.assertTrue(el.title_matches_company("Consultant @ KPMG", "KPMG"))

    def test_acronym_match(self):
        # acronym match (BCG) True
        self.assertTrue(el.title_matches_company("Consultant at BCG", "Boston Consulting Group (BCG)"))
        self.assertTrue(el.title_matches_company("Consultant at Boston Consulting Group", "Boston Consulting Group (BCG)"))

    def test_suffix_stripped_match(self):
        # suffix-stripped match (Cognizant vs "Cognizant Technology Solutions") True
        self.assertTrue(el.title_matches_company("Consultant at Cognizant", "Cognizant Technology Solutions"))
        self.assertTrue(el.title_matches_company("Consultant at Cognizant Technology Solutions", "Cognizant"))
        self.assertTrue(el.title_matches_company("Consultant at Cognizant Technology Solutions", "Cognizant Technology Solutions"))

    def test_unrelated_company(self):
        # unrelated company (KPMG title vs Cognizant target) False
        self.assertFalse(el.title_matches_company("Consultant @ KPMG India", "Cognizant"))
        self.assertFalse(el.title_matches_company("Data Analyst at Sportradar", "Cognizant"))

    def test_empty_title(self):
        # empty title False
        self.assertFalse(el.title_matches_company("", "Cognizant"))
        self.assertFalse(el.title_matches_company("   ", "Cognizant"))
        self.assertFalse(el.title_matches_company(None, "Cognizant"))

    def test_empty_company(self):
        # empty company False
        self.assertFalse(el.title_matches_company("Consultant at Deloitte", ""))
        self.assertFalse(el.title_matches_company("Consultant at Deloitte", "   "))
        self.assertFalse(el.title_matches_company("Consultant at Deloitte", None))

    def test_case_insensitive_match(self):
        self.assertTrue(el.title_matches_company("Business Analyst at DELOITTE India", "deloitte"))
        self.assertTrue(el.title_matches_company("business analyst at deloitte india", "Deloitte"))

    def test_suffix_not_making_name_empty(self):
        # If the company name is exactly one of the suffixes, we shouldn't strip it to empty.
        self.assertTrue(el.title_matches_company("Consultant at India", "India"))
        self.assertTrue(el.title_matches_company("Consultant at Consulting", "Consulting"))
        self.assertTrue(el.title_matches_company("Consultant at Technologies", "Technologies"))

    def test_non_string_types(self):
        self.assertFalse(el.title_matches_company(123, "Cognizant"))
        self.assertFalse(el.title_matches_company("Consultant", 123))

    def test_short_core_word_boundary(self):
        # "EY" core "ey" must NOT match substrings inside other words.
        self.assertFalse(el.title_matches_company("Senior Attorney at Microsoft", "EY"))
        self.assertFalse(el.title_matches_company("Survey Analyst at Acme", "EY"))
        self.assertFalse(el.title_matches_company("Money Manager at Acme", "EY"))
        # But a standalone EY token must still match.
        self.assertTrue(el.title_matches_company("Business Analyst at EY India", "EY"))
        self.assertTrue(el.title_matches_company("Consultant, EY", "EY"))

    def test_prefer_insiders_mixed(self):
        people = [
            {"name": "Alice", "title": "Analyst at Deloitte"},
            {"name": "Bob", "title": "Consultant at KPMG"}
        ]
        res = el.prefer_insiders(people, "Deloitte")
        self.assertEqual(res, [{"name": "Alice", "title": "Analyst at Deloitte"}])

    def test_prefer_insiders_all_non_insiders(self):
        people = [
            {"name": "Alice", "title": "Analyst at KPMG"},
            {"name": "Bob", "title": "Consultant at PwC"}
        ]
        res = el.prefer_insiders(people, "Deloitte")
        self.assertEqual(res, people)

    def test_prefer_insiders_empty(self):
        self.assertEqual(el.prefer_insiders([], "Deloitte"), [])

    def test_current_employer_guard(self):
        self.assertFalse(el.title_matches_company("ex-Deloitte consultant", "Deloitte"))
        self.assertFalse(el.title_matches_company("former Deloitte analyst", "Deloitte"))
        self.assertFalse(el.title_matches_company("previously Deloitte engineer", "Deloitte"))
        self.assertFalse(el.title_matches_company("ex Deloitte consultant", "Deloitte"))
        self.assertFalse(el.title_matches_company("Ex-Deloitte consultant", "Deloitte"))
        self.assertTrue(el.title_matches_company("Analyst at Deloitte", "Deloitte"))
        self.assertTrue(el.title_matches_company("ex-Deloitte consultant, now Analyst at Deloitte", "Deloitte"))


if __name__ == "__main__":
    unittest.main()
