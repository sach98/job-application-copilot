#!/bin/zsh
# Continuous "apply-as-posted" poller. Pulls FRESH jobs from the fast sources, keeps
# only postings not seen before (seen-ledger in build_local_queue --poll), scores them,
# tailors + fabrication-audits the ≥MIN_FIT ones, and appends ready cards to the queue.
#
# Run every ~20 min via cron so new roles surface within minutes of posting:
#   */20 * * * * ${JOBHUNT_ROOT:-$HOME/JobHunt}/poll_jobs.sh >> ${JOBHUNT_ROOT:-$HOME/JobHunt}/logs/poll.log 2>&1
#
# Sources (fastest first):
#   1. Company ATS (Greenhouse/Lever/Ashby public JSON) — instant, no ban, niche.
#   2. Indeed  — fresh window (last HOURS h), works, no ban.
#   3. LinkedIn guest — fresh window, low results (rate-limit-careful, no account).

set -uo pipefail

ROOT="${JOBHUNT_ROOT:-$HOME/JobHunt}"
PY="$ROOT/.venv/bin/python"
JOBS="$ROOT/applications/_poll_jobs.json"
PARTS="$ROOT/applications/_poll_parts"
MIN_FIT="${MIN_FIT:-0.60}"
LOCATION="${LOCATION:-India}"   # scrape broad; build keeps NCR/remote OR ≥0.78 standout
HOURS="${HOURS:-3}"                 # freshness window
KEYWORDS="${KEYWORDS:-Business Analyst;Insurance Business Analyst;Senior Business Analyst}"
SINCE="$(date -u -v-${HOURS}H +%Y-%m-%dT%H:%M:%SZ)"

mkdir -p "$ROOT/logs" "$PARTS"
rm -f "$PARTS"/*.json(N) 2>/dev/null

echo "[poll] $(date -u +%FT%TZ) freshness=${HOURS}h" >&2

# 1. ATS — instant-fresh, India-only.
"$PY" "$ROOT/scrapers/ats_fetch.py" --india-only > "$PARTS/ats.json" 2>>"$ROOT/logs/poll.log" \
  || echo "[poll] ats fetch errored (continuing)" >&2

# 2. Indeed + LinkedIn guest, fresh window, per keyword.
cd "$ROOT/scrapers"
i=0
for kw in ${(s.;.)KEYWORDS}; do
  i=$((i+1))
  "$PY" jobspy_wrapper.py --sites linkedin,indeed --keywords "$kw" --location "$LOCATION" \
    --since "$SINCE" --results-wanted 25 > "$PARTS/js_${i}.json" 2>>"$ROOT/logs/poll.log" \
    || echo "[poll]   keyword '${kw}' errored (continuing)" >&2
done

# 3. Merge all parts → dedupe by external_id/jd_url.
"$PY" - "$PARTS" "$JOBS" <<'PYEOF'
import json, sys, glob, os
parts, out = sys.argv[1], sys.argv[2]
seen, merged = set(), []
for fp in sorted(glob.glob(os.path.join(parts, "*.json"))):
    try:
        rows = json.load(open(fp, encoding="utf-8"))
    except Exception:
        continue
    for r in rows or []:
        k = str(r.get("external_id") or r.get("id") or (r.get("jd_url") or "").rstrip("/"))
        if not k or k in seen:
            continue
        seen.add(k); merged.append(r)
tmp = out + ".tmp"
json.dump(merged, open(tmp, "w", encoding="utf-8"), ensure_ascii=False)
os.replace(tmp, out)
print(f"[poll] merged {len(merged)} fresh jobs", file=sys.stderr)
PYEOF

[ -s "$JOBS" ] || { echo "[poll] no jobs this cycle" >&2; exit 0; }

# 4. Build in poll mode: only NEW postings get scored/tailored/audited + appended.
"$PY" "$ROOT/playwright_scripts/build_local_queue.py" --jobs "$JOBS" --poll --min-fit "$MIN_FIT" --top 25
echo "[poll] $(date -u +%FT%TZ) done" >&2
