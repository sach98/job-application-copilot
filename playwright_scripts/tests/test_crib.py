import sys
import unittest
import tempfile
import shutil
from pathlib import Path
from unittest.mock import Mock, patch

# Import pattern identical to other tests
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import make_crib
import serve_tinder

class TestCribGenerator(unittest.TestCase):
    def setUp(self):
        # Create a temp directory for mock files
        self.tmp_dir = tempfile.mkdtemp()
        self.answers_path = Path(self.tmp_dir) / "answers.md"
        self.master_resume_path = Path(self.tmp_dir) / "master_resume.md"
        
        # Write known sections to answers.md
        answers_content = """# candidate's Profile Q&A
## 9. Salary expectation + flexibility
₹18 LPA floor...

## 10. Notice period (literal weeks)
Immediate to 2 weeks.

## 11. Why this company?: template hooks
Some company specific hooks.

## 17. Open to relocation? Y/N + caveats
Primary preference: Delhi NCR.

## 18. Hybrid / remote / onsite preference
Hybrid NCR preference.
"""
        self.answers_path.write_text(answers_content, encoding="utf-8")
        
        # Write known contact details to master_resume.md
        master_resume_content = """# {{candidate_name}}
Example City, Country · +1 555 010 0000 · candidate@example.com · linkedin.com/in/candidate-example
"""
        self.master_resume_path.write_text(master_resume_content, encoding="utf-8")

    def tearDown(self):
        # Clean up temp dir
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_build_crib_standard(self):
        role = {
            "id": "role-1",
            "company": "Google",
            "role": "Software Engineer",
            "jd_url": "https://careers.google.com/jobs/1",
            "jd_text": "We need someone..."
        }
        crib = make_crib.build_crib(role, self.answers_path, self.master_resume_path)
        
        self.assertEqual(crib["role_id"], "role-1")
        self.assertEqual(crib["company"], "Google")
        self.assertEqual(crib["role"], "Software Engineer")
        
        # build_crib returns a dict with "fields" list and "apply_url" == the role's jd_url.
        self.assertEqual(crib["apply_url"], "https://careers.google.com/jobs/1")
        self.assertTrue(isinstance(crib["fields"], list))
        
        # Map fields by question title
        fields_by_q = {f["q"]: f for f in crib["fields"]}
        
        # the Notice-period field's answer contains "2 weeks"; the Salary field contains "LPA".
        self.assertIn("2 weeks", fields_by_q["Notice period"]["a"])
        self.assertIn("LPA", fields_by_q["Expected salary / CTC"]["a"])
        
        # phone/email/location fields are populated from the master resume.
        self.assertEqual(fields_by_q["Phone"]["a"], "+1 555 010 0000")
        self.assertEqual(fields_by_q["Email"]["a"], "candidate@example.com")
        self.assertEqual(fields_by_q["Current location"]["a"], "Example City, Country")
        
        # the work-authorization field has needs_confirm == True.
        self.assertTrue(fields_by_q["Authorized to work in India / require sponsorship?"]["needs_confirm"])
        
        # Relocation and preference checks
        self.assertEqual(fields_by_q["Open to relocation?"]["a"], "Primary preference: Delhi NCR.")
        self.assertEqual(fields_by_q["Hybrid / remote / onsite preference"]["a"], "Hybrid NCR preference.")
        self.assertEqual(fields_by_q["Why this company?"]["a"], "[Google] Some company specific hooks.")

    def test_empty_jd_url(self):
        # a role with empty/missing jd_url yields apply_url == "".
        role = {
            "id": "role-2",
            "company": "Google",
            "role": "Software Engineer"
        }
        crib = make_crib.build_crib(role, self.answers_path, self.master_resume_path)
        self.assertEqual(crib["apply_url"], "")


class MockHandler:
    def __init__(self):
        self.response_status = None
        self.response_message = None
        self.headers = {}
        self.wfile = Mock()

    def send_error(self, code, message=None, explain=None):
        self.response_status = code
        self.response_message = message

    def send_response(self, code, message=None):
        self.response_status = code

    def send_header(self, keyword, value):
        self.headers[keyword] = value

    def end_headers(self):
        pass

    def serve_artifact(self, role_id, filename):
        serve_tinder.TinderProxyHandler.serve_artifact(self, role_id, filename)


class TestServeTinderArtifacts(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.apps_dir = Path(self.tmp_dir) / "JobHunt" / "applications"
        self.apps_dir.mkdir(parents=True, exist_ok=True)
        
        # serve_tinder resolves JOBHUNT_ROOT once at import time, so patching Path.home()
        # here would have no effect. Patch the resolved constant the handler actually reads.
        self.root_patcher = patch.object(serve_tinder, "JOBHUNT_ROOT", Path(self.tmp_dir) / "JobHunt")
        self.root_patcher.start()

    def tearDown(self):
        self.root_patcher.stop()
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_serve_artifact_success_pdf(self):
        role_dir = self.apps_dir / "valid-role-123"
        role_dir.mkdir(parents=True, exist_ok=True)
        resume_file = role_dir / "resume.pdf"
        resume_file.write_bytes(b"mock pdf content")

        handler = MockHandler()
        handler.serve_artifact("valid-role-123", "resume.pdf")

        self.assertEqual(handler.response_status, 200)
        self.assertEqual(handler.headers.get("Content-Type"), "application/pdf")
        self.assertEqual(handler.headers.get("Content-Length"), str(len(b"mock pdf content")))
        handler.wfile.write.assert_called_once_with(b"mock pdf content")

    def test_serve_artifact_success_json(self):
        role_dir = self.apps_dir / "another_role"
        role_dir.mkdir(parents=True, exist_ok=True)
        crib_file = role_dir / "crib.json"
        crib_file.write_bytes(b"{}")

        handler = MockHandler()
        handler.serve_artifact("another_role", "crib.json")

        self.assertEqual(handler.response_status, 200)
        self.assertEqual(handler.headers.get("Content-Type"), "application/json")

    def test_serve_artifact_invalid_role_id(self):
        handler = MockHandler()
        
        # Traversals and dots in role_id
        handler.serve_artifact("../outside", "resume.pdf")
        self.assertEqual(handler.response_status, 400)
        
        handler.serve_artifact("role_id.with.dots", "resume.pdf")
        self.assertEqual(handler.response_status, 400)
        
        handler.serve_artifact("role/id", "resume.pdf")
        self.assertEqual(handler.response_status, 400)

    def test_serve_artifact_disallowed_filename(self):
        handler = MockHandler()
        handler.serve_artifact("valid-role-123", "unauthorized.txt")
        self.assertEqual(handler.response_status, 404)

    def test_serve_artifact_file_not_found(self):
        handler = MockHandler()
        handler.serve_artifact("valid-role-123", "resume.pdf")
        self.assertEqual(handler.response_status, 404)

    def test_serve_artifact_traversal_403(self):
        role_dir = self.apps_dir / "valid-role"
        role_dir.mkdir(parents=True, exist_ok=True)
        resume_file = role_dir / "resume.pdf"
        resume_file.write_bytes(b"pdf content")

        # Force is_relative_to to return False
        with patch("pathlib.PurePath.is_relative_to", return_value=False):
            handler = MockHandler()
            handler.serve_artifact("valid-role", "resume.pdf")
            self.assertEqual(handler.response_status, 403)


if __name__ == "__main__":
    unittest.main()
