#!/usr/bin/env python3
import base64
import hmac
import http.server
import os
import secrets
import sys
import json
import datetime
import re
import tempfile
from pathlib import Path


PORT = int(os.environ.get("REVIEW_PORT", "8765"))
JOBHUNT_ROOT = Path(os.environ.get("JOBHUNT_ROOT", str(Path.home() / "JobHunt")))
TINDER_APP_DIR = JOBHUNT_ROOT / "tinder_app"

# Basic Auth guards the public Tailscale funnel (serves resume/PII). Creds come
# from env (REVIEW_USER/REVIEW_PASS) so no secret is written to disk. If unset,
# an ephemeral password is generated and printed once at startup. Set REVIEW_PASS
# in the launch env for a stable password across restarts.
AUTH_USER = os.environ.get("REVIEW_USER", "reviewer")
AUTH_PASS = os.environ.get("REVIEW_PASS") or secrets.token_urlsafe(12)
_EXPECTED_AUTH = "Basic " + base64.b64encode(f"{AUTH_USER}:{AUTH_PASS}".encode()).decode()

# When present, the queue endpoint is served from this local file instead of
# proxying to n8n. Lets the review app show real scored+tailored jobs even while
# the n8n/Sheet path is empty or out of date. Delete the file to fall back to n8n.
LOCAL_QUEUE_FILE = JOBHUNT_ROOT / "applications" / "local_queue.json"
LOCAL_QUEUE_PATHS = {"/webhook/jobhunt/api/queue"}

# Records every swipe locally (role_id -> {action, at}) so the local rebuild can
# drop applied/skipped jobs and carry un-acted ones forward. Swipes still proxy
# to n8n in parallel; this file is the local source of truth for queue merging.
SWIPE_STATE_FILE = JOBHUNT_ROOT / "applications" / "_swipe_state.json"
SWIPE_PATHS = {"/webhook/jobhunt/api/swipe"}

# n8n was the original orchestrator; the pipeline is now fully local (shell-driven).
# This server serves the app + queue + artifacts and records swipes locally — no proxy.

OUTCOMES_FILE = JOBHUNT_ROOT / "applications" / "_outcomes.json"
STAGES = ["applied", "screening", "interview", "offer", "rejected", "ghosted"]

def load_outcomes() -> dict:
    if not OUTCOMES_FILE.is_file():
        return {}
    try:
        return json.loads(OUTCOMES_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}

def save_outcomes(d: dict) -> None:
    OUTCOMES_FILE.parent.mkdir(parents=True, exist_ok=True)
    dir_name = str(OUTCOMES_FILE.parent)
    fd, temp_path = tempfile.mkstemp(dir=dir_name, prefix="outcomes_", suffix=".json.tmp")
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(d, f, ensure_ascii=False, indent=2)
        os.replace(temp_path, str(OUTCOMES_FILE))
    except Exception as e:
        try:
            os.unlink(temp_path)
        except OSError:
            pass
        raise e

def upsert_outcome(data: dict, role_id, stage=None, company=None, role=None, note=None, now_iso=None) -> dict:
    role_id_str = str(role_id)
    if role_id_str not in data:
        valid_stage = stage if stage in STAGES else "applied"
        data[role_id_str] = {
            "role_id": role_id_str,
            "company": company if company is not None else "",
            "role": role if role is not None else "",
            "stage": valid_stage,
            "applied_at": now_iso,
            "updated_at": now_iso,
            "history": [{"stage": valid_stage, "at": now_iso}],
            "note": note if note is not None else ""
        }
    else:
        record = data[role_id_str]
        if company is not None:
            record["company"] = company
        if role is not None:
            record["role"] = role
        if note is not None:
            record["note"] = note
        
        if stage is not None and stage in STAGES:
            if record.get("stage") != stage:
                record["stage"] = stage
                if "history" not in record:
                    record["history"] = []
                record["history"].append({"stage": stage, "at": now_iso})
                record["updated_at"] = now_iso
    return data

class TinderProxyHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        # Serve files from the tinder_app directory
        super().__init__(*args, directory=str(TINDER_APP_DIR), **kwargs)

    def normalize_path(self):
        # Strip /review prefix if present to support sub-path routing
        if self.path.startswith("/review/"):
            self.path = self.path[7:]
        elif self.path == "/review":
            self.path = "/"

    def check_auth(self) -> bool:
        """True if the request carries valid Basic Auth. Else send 401 + return False.

        Constant-time compare avoids timing leaks on the credential.
        """
        header = self.headers.get("Authorization", "")
        if hmac.compare_digest(header, _EXPECTED_AUTH):
            return True
        self.send_response(401)
        self.send_header("WWW-Authenticate", 'Basic realm="JobHunt review"')
        self.send_header("Content-Length", "0")
        self.end_headers()
        return False

    def do_GET(self):
        if not self.check_auth():
            return
        self.normalize_path()

        # Check for secure artifact serving route
        path_only = self.path.split('?', 1)[0]
        prefix = "/webhook/jobhunt/api/artifact/"
        if path_only.startswith(prefix):
            suffix = path_only[len(prefix):]
            parts = suffix.split('/')
            if len(parts) == 2:
                self.serve_artifact(parts[0], parts[1])
            else:
                self.send_error(400, "Bad Request")
            return

        if self.path == "/webhook/jobhunt/api/outcomes":
            self._send_json(200, load_outcomes())
        elif self.path in LOCAL_QUEUE_PATHS and LOCAL_QUEUE_FILE.exists():
            self.serve_local_queue()
        else:
            super().do_GET()

    def _send_json(self, code, obj):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def serve_local_queue(self):
        try:
            body = LOCAL_QUEUE_FILE.read_bytes()
        except Exception as e:
            self.send_error(500, f"local queue read error: {e}")
            return
        print(f"[*] Serving local queue from {LOCAL_QUEUE_FILE}", file=sys.stderr)
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def serve_artifact(self, role_id, filename):
        if not re.match(r"^[A-Za-z0-9_-]+$", role_id):
            self.send_error(400, "Bad Request: Invalid role ID")
            return

        allowlist = {
            "resume.pdf", "resume.md",
            "cover_letter.pdf", "cover_letter.md",
            "crib.json", "essays.json"
        }
        if filename not in allowlist:
            self.send_error(404, "Not Found: Invalid filename")
            return

        applications_dir = JOBHUNT_ROOT / "applications"
        file_path = applications_dir / role_id / filename

        # Verify relative path safety
        try:
            resolved = file_path.resolve()
            resolved_apps = applications_dir.resolve()
            if not resolved.is_relative_to(resolved_apps):
                self.send_error(403, "Forbidden")
                return
        except Exception:
            self.send_error(403, "Forbidden")
            return

        if not file_path.is_file():
            self.send_error(404, "Not Found")
            return

        try:
            body = file_path.read_bytes()
        except Exception as e:
            self.send_error(500, f"Read error: {e}")
            return

        content_types = {
            ".pdf": "application/pdf",
            ".json": "application/json",
            ".md": "text/markdown"
        }
        ext = file_path.suffix.lower()
        content_type = content_types.get(ext, "application/octet-stream")

        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        if not self.check_auth():
            return
        self.normalize_path()
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length) if content_length > 0 else None
        if self.path in SWIPE_PATHS:
            self.record_swipe(body)
            self._send_json(200, {"ok": True})
        elif self.path == "/webhook/jobhunt/api/outcome":
            try:
                payload = json.loads(body.decode("utf-8")) if body else {}
            except Exception:
                self._send_json(400, {"error": "Invalid JSON"})
                return
            role_id = payload.get("role_id")
            if not role_id:
                self._send_json(400, {"error": "role_id required"})
                return
            data = load_outcomes()
            upsert_outcome(
                data,
                role_id=role_id,
                stage=payload.get("stage"),
                company=payload.get("company"),
                role=payload.get("role"),
                note=payload.get("note"),
                now_iso=datetime.datetime.utcnow().isoformat() + "Z"
            )
            try:
                save_outcomes(data)
            except Exception as e:
                self._send_json(500, {"error": f"save error: {e}"})
                return
            self._send_json(200, {"ok": True, "outcome": data[str(role_id)]})
        elif self.path.startswith("/webhook/"):
            # n8n removed — accept + no-op so optional UI posts don't error.
            self._send_json(200, {"ok": True})
        else:
            super().do_POST()

    def record_swipe(self, body):
        if not body:
            return
        try:
            payload = json.loads(body.decode("utf-8"))
            role_id = payload.get("role_id")
            action = payload.get("action")
            if not role_id or not action:
                return
            state = {}
            if SWIPE_STATE_FILE.exists():
                state = json.loads(SWIPE_STATE_FILE.read_text(encoding="utf-8"))
            state[str(role_id)] = {"action": action, "at": datetime.datetime.utcnow().isoformat() + "Z"}
            SWIPE_STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"[*] Recorded swipe {action} for {role_id}", file=sys.stderr)

            if action == "apply":
                try:
                    data = load_outcomes()
                    upsert_outcome(
                        data,
                        role_id=role_id,
                        stage="applied",
                        company=payload.get("company"),
                        role=payload.get("role"),
                        now_iso=datetime.datetime.utcnow().isoformat() + "Z"
                    )
                    save_outcomes(data)
                except Exception as oe:
                    print(f"[!] outcome seed error: {oe}", file=sys.stderr)
        except Exception as e:
            print(f"[!] swipe record error: {e}", file=sys.stderr)

    def do_HEAD(self):
        if not self.check_auth():
            return
        self.normalize_path()
        super().do_HEAD()

def main():
    server_address = ('', PORT)
    httpd = http.server.ThreadingHTTPServer(server_address, TinderProxyHandler)
    print(f"[+] Tinder app review server running at http://localhost:{PORT}", file=sys.stderr)
    print(f"[*] Serving files from: {TINDER_APP_DIR}", file=sys.stderr)
    print("[*] Local-only mode (n8n proxy removed)", file=sys.stderr)
    if os.environ.get("REVIEW_PASS"):
        print(f"[*] Basic Auth ON  user={AUTH_USER}  (credential from REVIEW_PASS env)", file=sys.stderr)
    else:
        print("[*] Basic Auth ON with an ephemeral generated secret; set REVIEW_PASS for stable auth", file=sys.stderr)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n[+] Server shutting down.", file=sys.stderr)
        httpd.server_close()

if __name__ == "__main__":
    main()
