import sys
import unittest
from pathlib import Path

# Import pattern identical to other tests
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import serve_tinder

class TestOutcomes(unittest.TestCase):
    def test_new_role_id(self):
        data = {}
        now_iso = "2026-05-31T00:00:00Z"
        result = serve_tinder.upsert_outcome(
            data,
            role_id="role-1",
            company="Google",
            role="Software Engineer",
            now_iso=now_iso
        )
        self.assertIn("role-1", result)
        role_data = result["role-1"]
        self.assertEqual(role_data["stage"], "applied")
        self.assertEqual(role_data["applied_at"], now_iso)
        self.assertEqual(role_data["updated_at"], now_iso)
        self.assertEqual(role_data["company"], "Google")
        self.assertEqual(role_data["role"], "Software Engineer")
        self.assertEqual(role_data["note"], "")
        self.assertEqual(len(role_data["history"]), 1)
        self.assertEqual(role_data["history"][0], {"stage": "applied", "at": now_iso})

    def test_existing_role_id_new_stage(self):
        now_iso_1 = "2026-05-31T00:00:00Z"
        now_iso_2 = "2026-05-31T01:00:00Z"
        data = {
            "role-1": {
                "role_id": "role-1",
                "company": "Google",
                "role": "Software Engineer",
                "stage": "applied",
                "applied_at": now_iso_1,
                "updated_at": now_iso_1,
                "history": [{"stage": "applied", "at": now_iso_1}],
                "note": ""
            }
        }
        result = serve_tinder.upsert_outcome(
            data,
            role_id="role-1",
            stage="interview",
            now_iso=now_iso_2
        )
        role_data = result["role-1"]
        self.assertEqual(role_data["stage"], "interview")
        self.assertEqual(role_data["applied_at"], now_iso_1)
        self.assertEqual(role_data["updated_at"], now_iso_2)
        self.assertEqual(len(role_data["history"]), 2)
        self.assertEqual(role_data["history"][0], {"stage": "applied", "at": now_iso_1})
        self.assertEqual(role_data["history"][1], {"stage": "interview", "at": now_iso_2})

    def test_invalid_stage(self):
        now_iso_1 = "2026-05-31T00:00:00Z"
        now_iso_2 = "2026-05-31T01:00:00Z"
        data = {
            "role-1": {
                "role_id": "role-1",
                "company": "Google",
                "role": "Software Engineer",
                "stage": "applied",
                "applied_at": now_iso_1,
                "updated_at": now_iso_1,
                "history": [{"stage": "applied", "at": now_iso_1}],
                "note": ""
            }
        }
        result = serve_tinder.upsert_outcome(
            data,
            role_id="role-1",
            stage="banana",
            now_iso=now_iso_2
        )
        role_data = result["role-1"]
        self.assertEqual(role_data["stage"], "applied")
        self.assertEqual(role_data["updated_at"], now_iso_1)
        self.assertEqual(len(role_data["history"]), 1)

    def test_company_role_note_populate_and_update(self):
        now_iso = "2026-05-31T00:00:00Z"
        data = {
            "role-1": {
                "role_id": "role-1",
                "company": "Google",
                "role": "Software Engineer",
                "stage": "applied",
                "applied_at": now_iso,
                "updated_at": now_iso,
                "history": [{"stage": "applied", "at": now_iso}],
                "note": ""
            }
        }
        result = serve_tinder.upsert_outcome(
            data,
            role_id="role-1",
            company="Alphabet",
            role="Staff Engineer",
            note="Interview prepped",
            now_iso=now_iso
        )
        role_data = result["role-1"]
        self.assertEqual(role_data["company"], "Alphabet")
        self.assertEqual(role_data["role"], "Staff Engineer")
        self.assertEqual(role_data["note"], "Interview prepped")

if __name__ == "__main__":
    unittest.main()
