#!/usr/bin/env python3
import sys
import argparse
import json
import re
import urllib.parse
from pathlib import Path
from playwright.sync_api import sync_playwright

# Add script directory to sys.path to import lib
sys.path.append(str(Path(__file__).parent))
from lib.captcha import check_and_solve_captcha

class BlockedError(RuntimeError):
    pass


COMET_BIN = "/Applications/Comet.app/Contents/MacOS/Comet"
PROFILE_DIR = Path.home() / "JobHunt" / ".browser-profile" / "comet"

def log(msg: str) -> None:
    print(f"[*] [Enrich] {msg}", file=sys.stderr, flush=True)

_DEGREE_RE = re.compile(r"•\s*(1st|2nd|3rd\+?)")
_BUTTON_WORDS = {"connect", "message", "follow", "pending", "following", "save", "saved"}

BETWEEN_SEARCH_SLEEP_MS = 4000


_SUFFIXES = ["pvt", "ltd", "inc", "llp", "limited", "technologies", "technology", "consulting", "india", "solutions"]
_SUFFIX_PATTERNS = {
    s: re.compile(rf"\b{s}$", re.IGNORECASE) for s in _SUFFIXES
}
_WHOLE_SUFFIX_PATTERNS = {
    s: re.compile(rf"^\b{s}$", re.IGNORECASE) for s in _SUFFIXES
}
_ACRONYM_RE = re.compile(r"\(([^)]+)\)")
_PUNCT_RE = re.compile(r"[\s,.\-/|]+$")


def strip_suffixes(name: str) -> str:
    """Repeatedly strip common trailing suffixes and punctuation from name."""
    name = name.strip()
    while True:
        cleaned = _PUNCT_RE.sub("", name)
        if cleaned != name:
            name = cleaned
            continue

        matched = False
        for suffix, pattern in _SUFFIX_PATTERNS.items():
            # If the entire name is just the suffix, do not strip it
            if _WHOLE_SUFFIX_PATTERNS[suffix].match(name):
                continue

            new_name, count = pattern.subn("", name)
            if count > 0:
                name = new_name
                matched = True
                break

        if not matched:
            break

    return _PUNCT_RE.sub("", name).strip()


def title_matches_company(title: str, company: str) -> bool:
    """Check if the person's title plausibly indicates they work at the target company."""
    if not title or not company:
        return False
    if not isinstance(title, str) or not isinstance(company, str):
        return False

    title = title.strip()
    company = company.strip()
    if not title or not company:
        return False

    # Extract parenthetical acronyms if any
    variants = []
    match = _ACRONYM_RE.search(company)
    if match:
        acronym = match.group(1).strip()
        if acronym:
            variants.append(acronym)
        long_form = _ACRONYM_RE.sub("", company).strip()
        if long_form:
            variants.append(long_form)
    else:
        variants.append(company)

    core_names = []
    for var in variants:
        core = strip_suffixes(var)
        if core:
            core_names.append(core.lower())

    if not core_names:
        return False

    title_lower = title.lower()
    for core in core_names:
        # Word-boundary match (not bare substring) so a short core like "ey" (EY)
        # doesn't match "attorney"/"survey"/"money".
        # Ensure it is not immediately preceded by "ex-", "ex ", "former ", or "previously "
        for m in re.finditer(rf"\b{re.escape(core)}\b", title_lower):
            start = m.start()
            prefix = title_lower[:start]
            if (prefix.endswith("ex-") or 
                prefix.endswith("ex ") or 
                prefix.endswith("former ") or 
                prefix.endswith("previously ")):
                continue
            return True

    return False


def prefer_insiders(people: list[dict], company: str) -> list[dict]:
    """Keep only company insiders if any exist, else return the original list.
    Used for hiring_manager/team where the best contact (e.g. an external recruiter)
    may legitimately not have the company in their title."""
    insiders = [p for p in people if title_matches_company(p.get("title", ""), company)]
    return insiders if insiders else people


def _parse_person_block(text: str, profile_url: str) -> dict:
    """Parse a LinkedIn people-search result block into a contact dict.

    Block inner_text lines come in order: Name, "• <degree>", Title, Location,
    then noise (mutual connections, action buttons). LinkedIn ships obfuscated,
    per-session class names, so we parse text order instead of CSS hooks.
    """
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    if not lines:
        return {}

    name = _DEGREE_RE.split(lines[0])[0].strip().rstrip("|").strip()
    degree = ""
    for l in lines:
        m = _DEGREE_RE.search(l)
        if m:
            degree = m.group(1)
            break

    # Content lines = drop the name line, degree-only lines, and action buttons.
    content = []
    for l in lines[1:]:
        low = l.lower()
        if "•" in l or low in _BUTTON_WORDS:
            continue
        if low.startswith(("view ", "status is", "message ")):
            continue
        content.append(l)

    title = content[0] if content else ""
    location = ""
    for l in content[1:]:
        if "," in l and "mutual" not in l.lower() and "connection" not in l.lower():
            location = l
            break

    return {
        "name": name,
        "title": title,
        "location": location,
        "linkedin_url": profile_url,
        "degree": degree,
    }


def search_linkedin_people(page, query: str, network: str = None) -> list[dict]:
    log(f"Searching LinkedIn for: '{query}'" + (f" (Network: {network})" if network else ""))
    encoded_query = urllib.parse.quote(query)
    search_url = f"https://www.linkedin.com/search/results/people/?keywords={encoded_query}"
    if network:
        search_url += f"&network={urllib.parse.quote(network)}"

    try:
        page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
        check_and_solve_captcha(page, log_fn=log)
        page.wait_for_timeout(4000)

        # Detect a block / auth-wall
        url = page.url
        is_blocked = any(p in url for p in ["/authwall", "/checkpoint", "/login", "/uas/login"])
        if not is_blocked:
            title = (page.title() or "").lower()
            if "sign in" in title or "security challenge" in title or "authwall" in title or "checkpoint" in title:
                is_blocked = True
            elif page.locator("form.login__form").count() > 0 or page.locator("#checkpoint-submit-button").count() > 0:
                is_blocked = True
            elif page.locator("input[name='session_key']").count() > 0:
                is_blocked = True

        if is_blocked:
            raise BlockedError(f"LinkedIn block/auth-wall during search: {url}")

        # Scroll to load lazy results.
        page.evaluate("window.scrollTo(0, document.body.scrollHeight / 2)")
        page.wait_for_timeout(1500)
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        page.wait_for_timeout(1500)

        # Each result is a role="listitem" block: Name / • degree / Title / Location.
        items = page.locator("[role='listitem']")
        results = []
        seen = set()
        for i in range(items.count()):
            it = items.nth(i)
            link = it.locator("a[href*='/in/']").first
            if link.count() == 0:
                continue
            url = (link.get_attribute("href") or "").split("?")[0].rstrip("/")
            if "/in/" not in url:
                continue
            if url.startswith("/"):
                url = "https://www.linkedin.com" + url
            if url in seen:
                continue
            seen.add(url)
            person = _parse_person_block(it.inner_text(), url)
            if person.get("name"):
                results.append(person)
            if len(results) >= 5:
                break
        return results
    except BlockedError:
        raise
    except Exception as e:
        log(f"Search failed for '{query}': {e}")
        return []

def find_contacts(page, company: str, role: str = "Business Analyst", location: str = "") -> dict:
    """Find hiring manager, same-team members, and best referral path for one company.

    Returns {hiring_manager, team_members, referrals}. Location, when given, is
    folded into the people-search query so geo-matching profiles rank higher.
    """
    loc = f" {location}" if location else ""
    has_searched = False

    def search_with_pacing(query: str, network: str = None) -> list[dict]:
        nonlocal has_searched
        if has_searched:
            page.wait_for_timeout(BETWEEN_SEARCH_SLEEP_MS)
        has_searched = True
        return search_linkedin_people(page, query, network=network)

    # 1. Hiring manager / recruiter (location-biased, then generic recruiter).
    hiring_managers = search_with_pacing(f"{company} Hiring Manager {role}{loc}")
    if not hiring_managers:
        hiring_managers = search_with_pacing(f"{company} recruiter{loc}")
    hiring_managers = prefer_insiders(hiring_managers, company)

    # 2. Same-team members (same role, same location).
    team_members = search_with_pacing(f'{company} "{role}"{loc}')
    team_members = prefer_insiders(team_members, company)

    # 3. Referral path: 1st-degree -> alumni (2nd) -> any 2nd-degree (warm).
    log("Searching for 1st-degree connections for referrals...")
    referrals = search_with_pacing(company, network='["F"]')
    if referrals:
        referrals = [r for r in referrals if title_matches_company(r.get("title", ""), company)]
    if not referrals:
        log("No 1st-degree. Trying Exeter alumni (2nd degree)...")
        alumni = search_with_pacing(f"{company} Exeter", network='["S"]')
        if not alumni:
            log("No Exeter alumni. Trying Sabarmati alumni...")
            alumni = search_with_pacing(f"{company} Sabarmati", network='["S"]')
        if alumni:
            alumni = [r for r in alumni if title_matches_company(r.get("title", ""), company)]
        if alumni:
            referrals = alumni
            for r in referrals:
                r["mutual_with_candidate"] = "Alumni (2nd Degree)"
    if not referrals:
        log("No alumni. Falling back to 2nd-degree warm targets...")
        warm = search_with_pacing(f"{company} {role}", network='["S"]')
        if warm:
            warm = [r for r in warm if title_matches_company(r.get("title", ""), company)]
        if warm:
            referrals = warm
            for r in referrals:
                r["mutual_with_candidate"] = "2nd Degree"

    if referrals:
        for r in referrals:
            r.setdefault("mutual_with_candidate", "1st Degree")

    return {
        "hiring_manager": hiring_managers[0] if hiring_managers else {},
        "team_members": team_members[:3] if team_members else [],
        "referrals": referrals[:3] if referrals else [],
    }


def _bootstrap(p):
    """Launch Comet on the saved profile and confirm LinkedIn is logged in.

    Returns (ctx, page). Raises RuntimeError if Comet is already running (profile
    lock) or LinkedIn is logged out.
    """
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    log(f"Launching Comet with profile {PROFILE_DIR}")
    try:
        ctx = p.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE_DIR),
            executable_path=COMET_BIN,
            headless=False,  # Headed so cookie reuse works securely
            args=["--no-first-run", "--no-default-browser-check"],
        )
    except Exception as e:
        raise RuntimeError(f"Comet launch failed (already running? quit Comet first): {e}")
    page = ctx.new_page()
    page.goto("https://www.linkedin.com/feed", wait_until="domcontentloaded", timeout=20000)
    check_and_solve_captcha(page, log_fn=log)
    page.wait_for_timeout(2000)
    if "/login" in page.url or "/uas/login" in page.url:
        ctx.close()
        raise RuntimeError("Not logged in to LinkedIn. Log in to LinkedIn in Comet first.")
    return ctx, page


def main():
    parser = argparse.ArgumentParser(description="LinkedIn session-based enrichment scraper")
    parser.add_argument("--company", help="Company name (single-company mode)")
    parser.add_argument("--role", default="Business Analyst", help="Role title")
    parser.add_argument("--location", default="", help="Location to bias the people search")
    parser.add_argument("--batch", help="Path to JSON array of {id,company,role,location}; "
                                        "outputs {id: contacts} to stdout. One Comet launch for all.")
    args = parser.parse_args()

    if not args.batch and not args.company:
        parser.error("provide either --company or --batch")

    with sync_playwright() as p:
        try:
            ctx, page = _bootstrap(p)
        except RuntimeError as e:
            log(str(e))
            sys.exit(1)

        try:
            if args.batch:
                jobs = json.loads(Path(args.batch).read_text(encoding="utf-8"))
                out = {}
                blocked = False
                for idx, j in enumerate(jobs):
                    jid = str(j.get("id"))
                    if blocked:
                        out[jid] = {"hiring_manager": {}, "team_members": [], "referrals": [], "_status": "blocked"}
                        continue
                    log(f"--- enriching {j.get('company')} ({jid}) ---")
                    try:
                        contacts = find_contacts(page, j.get("company") or "",
                                                 j.get("role") or "Business Analyst",
                                                 j.get("location") or "")
                        has_contacts = (
                            bool(contacts.get("hiring_manager", {}).get("name")) or
                            bool(contacts.get("team_members")) or
                            bool(contacts.get("referrals"))
                        )
                        contacts["_status"] = "ok" if has_contacts else "empty"
                        out[jid] = contacts
                    except BlockedError as e:
                        log(f"enrich failed (blocked) for {jid}: {e}")
                        out[jid] = {"hiring_manager": {}, "team_members": [], "referrals": [], "_status": "blocked"}
                        blocked = True
                        for rem_j in jobs[idx+1:]:
                            rem_jid = str(rem_j.get("id"))
                            out[rem_jid] = {"hiring_manager": {}, "team_members": [], "referrals": [], "_status": "blocked"}
                        break
                    except Exception as e:
                        log(f"enrich failed for {jid}: {e}")
                        out[jid] = {"hiring_manager": {}, "team_members": [], "referrals": [], "_status": "empty"}
                    
                    if not blocked:
                        page.wait_for_timeout(2000)  # gentle pacing between companies
                print(json.dumps(out, indent=2))
            else:
                try:
                    contacts = find_contacts(page, args.company, args.role, args.location)
                    has_contacts = (
                        bool(contacts.get("hiring_manager", {}).get("name")) or
                        bool(contacts.get("team_members")) or
                        bool(contacts.get("referrals"))
                    )
                    contacts["_status"] = "ok" if has_contacts else "empty"
                    print(json.dumps(contacts, indent=2))
                except BlockedError as e:
                    log(f"enrich failed (blocked): {e}")
                    print(json.dumps({"hiring_manager": {}, "team_members": [], "referrals": [], "_status": "blocked"}, indent=2))
        finally:
            ctx.close()


if __name__ == "__main__":
    main()
