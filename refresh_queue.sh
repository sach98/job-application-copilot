#!/bin/zsh
# Refresh the local review queue: scrape fresh jobs across public boards + multiple
# keywords (volume without quality loss), then score+gate+tailor into
# applications/local_queue.json (what serve_tinder.py serves).
#
# Quality gate: only jobs at/above MIN_FIT (default 0.80 holistic fit) are queued.
# Volume comes from scraping WIDER (more boards + keywords), not from lowering the bar.
#
# Usage:
#   ./refresh_queue.sh [TOP]                 # TOP defaults to 25
# Override via env:
#   MIN_FIT=0.8 KEYWORDS="Business Analyst;Product Analyst" LOCATION="India" \
#   SITES="linkedin,indeed,glassdoor" ./refresh_queue.sh
#
# Cron (every 3h, 09:00-21:00 IST). `crontab -e`:
#   0 9-21/3 * * * ${JOBHUNT_ROOT:-$HOME/JobHunt}/refresh_queue.sh >> ${JOBHUNT_ROOT:-$HOME/JobHunt}/logs/refresh.log 2>&1
# (Public boards = no LinkedIn login = ban-safe + cron-friendly.)

set -uo pipefail

ROOT="${JOBHUNT_ROOT:-$HOME/JobHunt}"
PY="$ROOT/.venv/bin/python"
JOBS="$ROOT/applications/_scraped_jobs.json"
PARTS_DIR="$ROOT/applications/_scrape_parts"
TOP="${1:-25}"
MIN_FIT="${MIN_FIT:-0.80}"
LOCATION="${LOCATION:-India}"   # scrape broad; build keeps NCR/remote OR ≥0.78 standout anywhere
# Glassdoor dropped — jobspy's Glassdoor API errors on every call. LinkedIn+Indeed are public.
SITES="${SITES:-linkedin,indeed}"
RESULTS="${RESULTS:-60}"
# Niche-weighted keywords surface candidate's actual-fit roles (insurance/BFSI/regulatory BA),
# not just generic analytics BA — generic terms score moderate against a narrow niche.
KEYWORDS="${KEYWORDS:-Insurance Business Analyst;BFSI Business Analyst;Regulatory Business Analyst;Senior Business Analyst;Business Analyst Consumer Duty;Business Analyst}"
SINCE="$(date -u -v-72H +%Y-%m-%dT%H:%M:%SZ)"

mkdir -p "$ROOT/logs" "$PARTS_DIR"
rm -f "$PARTS_DIR"/*.json(N) 2>/dev/null  # (N) null-glob: no error when dir empty

echo "[refresh] $(date -u +%FT%TZ) scrape ${SITES} since ${SINCE}" >&2

# jobspy_wrapper resolves `from lib...` relative to its own dir, so run from there.
cd "$ROOT/scrapers"
i=0
# zsh: split KEYWORDS on ';'
for kw in ${(s.;.)KEYWORDS}; do
  i=$((i+1))
  echo "[refresh]   keyword: '${kw}'" >&2
  "$PY" jobspy_wrapper.py \
    --sites "$SITES" \
    --keywords "$kw" \
    --location "$LOCATION" \
    --since "$SINCE" \
    --results-wanted "$RESULTS" > "${PARTS_DIR}/part_${i}.json" 2>>"$ROOT/logs/refresh.log" || \
    echo "[refresh]   keyword '${kw}' scrape errored (continuing)" >&2
done

# Merge all keyword parts → dedupe by external_id/jd_url → JOBS.
"$PY" - "$PARTS_DIR" "$JOBS" <<'PYEOF'
import json, sys, glob, os
parts_dir, out = sys.argv[1], sys.argv[2]
seen, merged = set(), []
for fp in sorted(glob.glob(os.path.join(parts_dir, "*.json"))):
    try:
        rows = json.load(open(fp, encoding="utf-8"))
    except Exception:
        continue
    for r in rows or []:
        key = str(r.get("external_id") or r.get("id") or (r.get("jd_url") or "").rstrip("/"))
        if not key or key in seen:
            continue
        seen.add(key); merged.append(r)
if merged:
    tmp = out + ".tmp"
    json.dump(merged, open(tmp, "w", encoding="utf-8"), ensure_ascii=False)
    os.replace(tmp, out)
    print(f"[refresh] merged {len(merged)} unique jobs across keywords", file=sys.stderr)
else:
    print("[refresh] scrape produced 0 jobs; keeping previous jobs file", file=sys.stderr)
PYEOF

if [ ! -s "$JOBS" ]; then
  echo "[refresh] no jobs file to build from; aborting." >&2
  exit 1
fi

"$PY" "$ROOT/playwright_scripts/build_local_queue.py" --jobs "$JOBS" --top "$TOP" --min-fit "$MIN_FIT"
echo "[refresh] $(date -u +%FT%TZ) done." >&2
