import sys
import requests

def lookup_essay_answer(webhook_url: str, question: str, company: str, role: str, jd_url: str, job_id: str = "") -> str:
    """Queries n8n webhook for a tailored essay answer to a custom portal question."""
    if not webhook_url:
        print(f"[-] No n8n webhook configured for essay lookup.", file=sys.stderr)
        return ""

    endpoint = f"{webhook_url.rstrip('/')}/essay"
    payload = {
        "question": question,
        "company": company,
        "role": role,
        "jd_url": jd_url,
        "job_id": job_id,
    }
    
    print(f"[*] Querying essay draft for: '{question[:60]}...'", file=sys.stderr)
    try:
        r = requests.post(endpoint, json=payload, timeout=120)  # long timeout for AI drafting
        if r.status_code == 200:
            res = r.json()
            return res.get("answer", "")
        else:
            print(f"[-] Essay lookup returned status {r.status_code}: {r.text}", file=sys.stderr)
    except Exception as e:
        print(f"[-] Essay lookup error: {e}", file=sys.stderr)
        
    return ""
