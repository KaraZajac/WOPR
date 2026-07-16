"""ACLED integration: aggregate pulls today, event-level API when entitled.

ACLED's myACLED system (2025+) assigns access levels per account. The *Open*
level — what an unrecognized org domain gets automatically — includes the
aggregated data files but NOT the event-level read API; that needs a higher
level from ACLED's Access Team (trials and licenses via the portal's
"Request further access"). This module therefore does two jobs:

  pull()      log in with ACLED_USERNAME/ACLED_PASSWORD (repo-root .env),
              discover the current aggregate file behind each landing page
              (filenames change per release), download the xlsx, and convert
              to CSV under sources/acled/ with a manifest.
  api_read()  the OAuth bearer flow for https://acleddata.com/api/acled/read,
              ready for an entitled account; on 403 it explains the access
              level instead of pretending it's a bug.

Aggregate files are ACLED's political-violence ontology (battles, explosions/
remote violence, violence against civilians), NOT UCDP's sb/ns/os categories
or its 25-death inclusion rule — keep them as tempo signals and cross-checks,
not as resolution authorities for UCDP-pinned questions.

Run: python3 -m tocsin.pipeline.acled [--force] [--api-check]
"""

import csv
import datetime
import http.cookiejar
import json
import os
import re
import urllib.parse
import urllib.request
from pathlib import Path

import yaml

import tocsin._env  # noqa: F401  (loads .env)
from tocsin.paths import ROOT, SOURCES
from tocsin.pipeline.xlsx import xlsx_rows

ACLED = "https://acleddata.com"
UA = "TOCSIN-pipeline/0.1 (academic research)"
DEST = SOURCES / "acled"

# logical name -> landing page under /aggregated/ that links the current file
AGGREGATES = {
    "pv-country-month": "number-political-violence-events-country-month-year",
    "pv-country-year": "number-political-violence-events-country-year",
    "demos-country-year": "number-demonstration-events-country-year",
    "fatalities-country-year": "number-reported-fatalities-country-year",
    "civilian-fatalities-country-year": "number-reported-civilian-fatalities-direct-targeting-country-year",
    "civilian-targeting-country-year": "number-events-targeting-civilians-country-year",
    "weekly-africa": "aggregated-data-africa",
    "weekly-asia-pacific": "aggregated-data-asia-pacific",
    "weekly-europe-central-asia": "aggregated-data-europe-and-central-asia",
    "weekly-latam-caribbean": "aggregated-data-latin-america-caribbean",
    "weekly-middle-east": "aggregated-data-middle-east",
    "weekly-us-canada": "aggregated-data-united-states-canada",
}


def credentials() -> tuple[str, str]:
    user = os.environ.get("ACLED_USERNAME", "")
    pw = os.environ.get("ACLED_PASSWORD", "")
    if not user or not pw:
        raise SystemExit("set ACLED_USERNAME and ACLED_PASSWORD in the repo-root .env")
    return user, pw


def session() -> urllib.request.OpenerDirector:
    """Cookie-authenticated opener (Drupal login) for pages and file downloads."""
    user, pw = credentials()
    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    opener.addheaders = [("User-Agent", UA), ("Accept", "application/json, text/html")]
    body = json.dumps({"name": user, "pass": pw}).encode()
    req = urllib.request.Request(
        f"{ACLED}/user/login?_format=json", data=body, headers={"Content-Type": "application/json"}
    )
    with opener.open(req, timeout=60) as r:
        who = json.loads(r.read())
    print(f"  logged in as {who['current_user']['name']} (uid {who['current_user']['uid']})")
    return opener


def oauth_token() -> str:
    """Bearer token (password grant, scope=authenticated), cached until expiry."""
    cache = DEST / ".token.json"
    if cache.exists():
        tok = json.loads(cache.read_text())
        if tok.get("expires_at", 0) > datetime.datetime.now().timestamp() + 60:
            return tok["access_token"]
    user, pw = credentials()
    data = urllib.parse.urlencode(
        {"grant_type": "password", "client_id": "acled", "scope": "authenticated", "username": user, "password": pw}
    ).encode()
    req = urllib.request.Request(
        f"{ACLED}/oauth/token",
        data=data,
        headers={"User-Agent": UA, "Content-Type": "application/x-www-form-urlencoded"},
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        tok = json.loads(r.read())
    tok["expires_at"] = datetime.datetime.now().timestamp() + int(tok.get("expires_in", 3600))
    DEST.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(tok))
    cache.chmod(0o600)
    return tok["access_token"]


def api_read(params: dict) -> list[dict]:
    """Event-level read API. Requires an access level above Open myACLED."""
    query = urllib.parse.urlencode({"_format": "json", **params})
    req = urllib.request.Request(
        f"{ACLED}/api/acled/read?{query}",
        headers={"User-Agent": UA, "Authorization": f"Bearer {oauth_token()}", "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            body = json.loads(r.read())
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            raise SystemExit(
                "ACLED read API refused (HTTP %d): this account's myACLED level does not include "
                "event-level API access. Request an upgrade/trial via the portal, then retry." % e.code
            )
        raise
    return body.get("data", [])


# ---------------------------------------------------------------- pull


def discover_file(opener, page: str) -> str:
    with opener.open(f"{ACLED}/aggregated/{page}", timeout=60) as r:
        raw = r.read().decode("utf-8", "replace")
    links = sorted(set(re.findall(r'href="(https://acleddata\.com/system/files/[^"]+\.xlsx)"', raw)))
    if not links:
        raise SystemExit(f"no .xlsx link found on /aggregated/{page} — page layout changed?")
    return links[-1]


def pull(force: bool = False) -> None:
    DEST.mkdir(parents=True, exist_ok=True)
    opener = session()
    manifest = {"pulled": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "files": {}}
    for logical, page in AGGREGATES.items():
        url = discover_file(opener, page)
        upstream = url.rsplit("/", 1)[1]
        xlsx = DEST / f"{logical}.xlsx"
        csv_path = DEST / f"{logical}.csv"
        manifest["files"][logical] = {"upstream": upstream, "csv": csv_path.name}
        marker = DEST / f".{logical}.src"
        if csv_path.exists() and marker.exists() and marker.read_text() == upstream and not force:
            print(f"  cached {csv_path.relative_to(ROOT)} ({upstream})")
            continue
        with opener.open(url, timeout=300) as r:
            xlsx.write_bytes(r.read())
        rows = xlsx_rows(xlsx)
        with open(csv_path, "w", newline="") as f:
            csv.writer(f).writerows(rows)
        marker.write_text(upstream)
        xlsx.unlink()
        print(f"  -> {csv_path.relative_to(ROOT)} ({len(rows):,} rows, from {upstream})")
    with open(DEST / "manifest.yaml", "w") as f:
        yaml.safe_dump(manifest, f, sort_keys=False)
    print("wrote sources/acled/manifest.yaml")


def api_check() -> None:
    print("checking event-level API entitlement…")
    rows = api_read({"limit": 1})
    print(f"  ✓ read API works — sample event keys: {sorted(rows[0])[:8]}…" if rows else "  API ok, empty result")


def main() -> None:
    import sys

    if "--api-check" in sys.argv:
        api_check()
        return
    pull(force="--force" in sys.argv)


if __name__ == "__main__":
    main()
