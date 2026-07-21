#!/usr/bin/env python3
"""Crib generator: assemble a "crib sheet" of standard application answers for one job.

Pulled from answers.md and master_resume.md. Pure rule-based parsing.
"""

import json
import re
import argparse
import sys
from pathlib import Path

# Module-level constants for default paths
sys.path.append(str(Path(__file__).parent))
from lib.paths import PROFILE_DIR

DEFAULT_ANSWERS_PATH = PROFILE_DIR / "answers.md"
DEFAULT_MASTER_RESUME_PATH = PROFILE_DIR / "master_resume.md"

def parse_answers(content: str) -> dict[int, str]:
    """Parse answers.md into a dictionary mapping heading number (int) to body text."""
    sections = {}
    current_num = None
    current_lines = []
    
    for line in content.splitlines():
        if line.startswith("## "):
            if current_num is not None:
                sections[current_num] = "\n".join(current_lines).strip()
            
            heading = line[3:].strip()
            # Parse leading number in heading: e.g. "9. Salary expectation + flexibility"
            match = re.match(r"^(\d+)\.", heading)
            if match:
                current_num = int(match.group(1))
            else:
                current_num = None
            current_lines = []
        else:
            if current_num is not None:
                current_lines.append(line)
                
    if current_num is not None:
        sections[current_num] = "\n".join(current_lines).strip()
        
    return sections

def parse_contact_info(content: str) -> tuple[str, str, str]:
    """Extract location, phone, and email from master_resume.md."""
    location, phone, email = "", "", ""
    contact_line = None
    
    for line in content.splitlines():
        if "·" in line and "@" in line:
            contact_line = line.strip()
            break
            
    if contact_line:
        parts = contact_line.split("·")
        if parts:
            location = parts[0].strip()
        
        # Tolerant phone regex: \+?\d[\d ]{7,}\d
        phone_match = re.search(r"\+?\d[\d ]{7,}\d", contact_line)
        if phone_match:
            phone = phone_match.group(0).strip()
            
        # Standard email regex
        email_match = re.search(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+", contact_line)
        if email_match:
            email = email_match.group(0).strip()
    else:
        # Fallback search across the whole file
        phone_match = re.search(r"\+?\d[\d ]{7,}\d", content)
        if phone_match:
            phone = phone_match.group(0).strip()
            
        email_match = re.search(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+", content)
        if email_match:
            email = email_match.group(0).strip()
            
    return location, phone, email

def build_crib(role: dict, answers_md_path: Path, master_md_path: Path) -> dict:
    """Build the crib dictionary based on role, answers.md, and master_resume.md."""
    answers = {}
    if answers_md_path.exists():
        try:
            content = answers_md_path.read_text(encoding="utf-8")
            answers = parse_answers(content)
        except Exception:
            pass

    location, phone, email = "", "", ""
    if master_md_path.exists():
        try:
            content = master_md_path.read_text(encoding="utf-8")
            location, phone, email = parse_contact_info(content)
        except Exception:
            pass

    role_id = role.get("id") or ""
    company_name = role.get("company") or ""
    role_title = role.get("role") or ""
    apply_url = role.get("jd_url") or ""

    fields = []

    # Helper to check if a string is present and return correct value and needs_confirm
    def get_ans_field(val: str | None, missing_msg: str) -> tuple[str, bool]:
        if val and val.strip():
            return val.strip(), False
        return missing_msg, True

    # 1. Years of experience
    fields.append({
        "q": "Years of experience",
        "a": "6+ years (Senior Business Analyst)",
        "source": "profile",
        "needs_confirm": False
    })

    # 2. Authorized to work in India
    fields.append({
        "q": "Authorized to work in India / require sponsorship?",
        "a": "⚠ Not in profile, confirm before submitting (India-based roles typically need no sponsorship).",
        "source": "(missing)",
        "needs_confirm": True
    })

    # 3. Notice period (Section 10)
    sec10_val, sec10_confirm = get_ans_field(answers.get(10), "⚠ Not found in answers.md")
    fields.append({
        "q": "Notice period",
        "a": sec10_val,
        "source": "answers.md #10",
        "needs_confirm": sec10_confirm
    })

    # 4. Expected salary / CTC (Section 9)
    sec9_val, sec9_confirm = get_ans_field(answers.get(9), "⚠ Not found in answers.md")
    fields.append({
        "q": "Expected salary / CTC",
        "a": sec9_val,
        "source": "answers.md #9",
        "needs_confirm": sec9_confirm
    })

    # 5. Current location (from master_resume)
    loc_val, loc_confirm = get_ans_field(location, "⚠ Not found in master_resume.md")
    fields.append({
        "q": "Current location",
        "a": loc_val,
        "source": "master_resume",
        "needs_confirm": loc_confirm
    })

    # 6. Open to relocation? (Section 17)
    sec17_val, sec17_confirm = get_ans_field(answers.get(17), "⚠ Not found in answers.md")
    fields.append({
        "q": "Open to relocation?",
        "a": sec17_val,
        "source": "answers.md #17",
        "needs_confirm": sec17_confirm
    })

    # 7. Hybrid / remote / onsite preference (Section 18)
    sec18_val, sec18_confirm = get_ans_field(answers.get(18), "⚠ Not found in answers.md")
    fields.append({
        "q": "Hybrid / remote / onsite preference",
        "a": sec18_val,
        "source": "answers.md #18",
        "needs_confirm": sec18_confirm
    })

    # 8. Why this company? (Section 11)
    sec11 = answers.get(11)
    if sec11 and sec11.strip():
        sec11_ans = f"[{company_name}] {sec11.strip()}"
    else:
        sec11_ans = "⚠ Not found in answers.md"
    fields.append({
        "q": "Why this company?",
        "a": sec11_ans,
        "source": "answers.md #11",
        "needs_confirm": True
    })

    # 9. Phone (from master_resume)
    phone_val, phone_confirm = get_ans_field(phone, "⚠ Not found in master_resume.md")
    fields.append({
        "q": "Phone",
        "a": phone_val,
        "source": "master_resume",
        "needs_confirm": phone_confirm
    })

    # 10. Email (from master_resume)
    email_val, email_confirm = get_ans_field(email, "⚠ Not found in master_resume.md")
    fields.append({
        "q": "Email",
        "a": email_val,
        "source": "master_resume",
        "needs_confirm": email_confirm
    })

    return {
        "role_id": role_id,
        "company": company_name,
        "role": role_title,
        "apply_url": apply_url,
        "fields": fields
    }

def write_crib(role: dict, out_dir: Path) -> Path:
    """Build crib, write to <out_dir>/crib.json, return path."""
    out_dir.mkdir(parents=True, exist_ok=True)
    crib_dict = build_crib(role, DEFAULT_ANSWERS_PATH, DEFAULT_MASTER_RESUME_PATH)
    out_file = out_dir / "crib.json"
    out_file.write_text(json.dumps(crib_dict, indent=2, ensure_ascii=False), encoding="utf-8")
    return out_file

def main() -> int:
    parser = argparse.ArgumentParser(description="Generate crib sheet for JobHunt application.")
    parser.add_argument("--id", help="Role ID")
    parser.add_argument("--company", help="Company Name")
    parser.add_argument("--role", help="Role Title")
    parser.add_argument("--jd-url", help="Job Description URL")
    parser.add_argument("--out-dir", help="Output directory to write crib.json")
    parser.add_argument("--self-test", action="store_true", help="Run self-test with dummy data and print result")

    args = parser.parse_args()

    if args.self_test:
        sample_role = {
            "id": "test-role-123",
            "company": "Acme Corp",
            "role": "Senior BA",
            "jd_url": "https://example.com/job/123",
            "jd_text": "We are looking for a Senior BA..."
        }
        crib = build_crib(sample_role, DEFAULT_ANSWERS_PATH, DEFAULT_MASTER_RESUME_PATH)
        print(json.dumps(crib, indent=2, ensure_ascii=False))
        return 0

    if not args.out_dir:
        parser.print_help()
        return 1

    role = {
        "id": args.id or "",
        "company": args.company or "",
        "role": args.role or "",
        "jd_url": args.jd_url or "",
    }
    out_path = write_crib(role, Path(args.out_dir))
    print(out_path)
    return 0

if __name__ == "__main__":
    sys.exit(main())
