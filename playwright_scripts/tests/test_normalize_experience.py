"""Regression test for the experience-range parser in scrapers/lib/normalize.py.

Job descriptions write ranges with a plain hyphen ("5-10 years") and with an en dash
with an en dash. The pattern must accept both. A house style rule forbids literal
en dashes in source, so the pattern spells it \\u2013. This test proves the escape still
matches the real character, which a careless de-dashing pass would silently break.

Run: cd playwright_scripts && ../.venv/bin/python -m unittest tests.test_normalize_experience
"""

import importlib.util
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
NORMALIZE_PY = REPO_ROOT / "scrapers" / "lib" / "normalize.py"

# Load by path: "lib" already resolves to playwright_scripts/lib in this test run, so a
# plain `from lib.normalize import ...` would pick up the wrong package.
_spec = importlib.util.spec_from_file_location("scrapers_normalize", NORMALIZE_PY)
_normalize = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_normalize)
extract_experience = _normalize.extract_experience

EN_DASH = chr(0x2013)


class ExtractExperienceTests(unittest.TestCase):
    def test_hyphen_range(self):
        self.assertEqual(extract_experience("Requires 5-10 years experience"), "5-10 years")

    def test_en_dash_range(self):
        self.assertEqual(
            extract_experience(f"Requires 5{EN_DASH}10 years experience"),
            f"5{EN_DASH}10 years",
        )

    def test_word_range(self):
        self.assertEqual(extract_experience("Requires 3 to 7 yrs"), "3 to 7 yrs")

    def test_open_ended(self):
        self.assertEqual(extract_experience("8+ years in analytics"), "8+ years")

    def test_no_experience_stated(self):
        self.assertIsNone(extract_experience("Great team, free lunch"))
        self.assertIsNone(extract_experience(""))
        self.assertIsNone(extract_experience(None))

    def test_range_form_wins_over_the_bare_number_form(self):
        # The range pattern is listed first precisely so "5-10 years" is not read as
        # "10 years". Order matters, so assert the whole range comes back.
        for text in ["2-4 years", f"2{EN_DASH}4 years", "2 to 4 years"]:
            with self.subTest(text=text):
                self.assertEqual(extract_experience(f"We want {text} of BA work"), text)

    def test_source_carries_no_literal_dash_characters(self):
        source = NORMALIZE_PY.read_text(encoding="utf-8")
        self.assertNotIn(EN_DASH, source)
        self.assertNotIn(chr(0x2014), source)
        self.assertIn(r"\u2013", source)


if __name__ == "__main__":
    unittest.main()
