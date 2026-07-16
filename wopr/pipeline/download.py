"""Fetch UCDP releases and the Gleditsch–Ward state list into sources/.

Scrapes ucdp.uu.se/downloads/ once to discover the newest annual release
(e.g. ``261`` = version 26.1, events through 2025) and the current set of
candidate-GED monthly files (preliminary events past the annual cutoff),
downloads the CSV zips, extracts them under sources/, and writes
sources/manifest.yaml for the rest of the pipeline.
"""

import datetime
import io
import re
import sys
import zipfile
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import yaml

from wopr.paths import CANDIDATE, ROOT, SOURCES

UCDP = "https://ucdp.uu.se/downloads"
GW = "http://ksgleditsch.com/data"
UA = "WOPR-pipeline/0.1 (academic research)"

# logical name -> (subdirectory, file stem); url is {UCDP}/{subdir}/{stem}-{v}-csv.zip
ZIPS = {
    "ucdp-prio-acd": ("ucdpprio", "ucdp-prio-acd"),
    "ucdp-dyadic": ("dyadic", "ucdp-dyadic"),
    "ucdp-nonstate": ("nsos", "ucdp-nonstate"),
    "ucdp-onesided": ("nsos", "ucdp-onesided"),
    "ucdp-cy": ("organizedviolencecy", "organizedviolencecy"),
}
# v7 of the Gleditsch–Ward list (ksgmdw.txt, through 2020); the old
# iisystem.dat/microstatessystem.dat URLs are frozen at the 2017 revision.
GW_FILES = {
    "gw-states.tsv": f"{GW}/ksgmdw.txt",
    "gw-microstates.tsv": f"{GW}/microstates.txt",
}


def _get(url: str, timeout: int = 300) -> bytes:
    try:
        with urlopen(Request(url, headers={"User-Agent": UA}), timeout=timeout) as resp:
            return resp.read()
    except (HTTPError, URLError, TimeoutError) as e:
        raise SystemExit(f"download failed: {url} ({e})")


def scrape_downloads_page() -> tuple[str, list[str]]:
    """Return (release, candidate CSV urls) from the UCDP downloads page."""
    html = _get(f"{UCDP}/", timeout=60).decode("utf-8", "replace")
    releases = re.findall(r"/downloads/ged/ged(\d{3})-csv\.zip", html)
    if not releases:
        raise SystemExit("could not find a GED release link on ucdp.uu.se/downloads/")
    release = max(releases)
    candidates = sorted(
        set(re.findall(r'href="(https://ucdp\.uu\.se/downloads/candidateged/[^"]+?\.csv)"', html))
    )
    return release, candidates


def fetch_zip_csv(url: str, dest: Path) -> None:
    """Download a one-CSV zip and extract that CSV to dest."""
    print(f"  GET {url}")
    payload = _get(url)
    with zipfile.ZipFile(io.BytesIO(payload)) as zf:
        members = [m for m in zf.namelist() if m.lower().endswith(".csv")]
        if len(members) != 1:
            raise SystemExit(f"expected exactly one CSV in {url}, found {members}")
        dest.write_bytes(zf.read(members[0]))
    print(f"  -> {dest.relative_to(ROOT)} ({dest.stat().st_size:,} bytes)")


def fetch_file(url: str, dest: Path) -> None:
    print(f"  GET {url}")
    dest.write_bytes(_get(url))
    print(f"  -> {dest.relative_to(ROOT)} ({dest.stat().st_size:,} bytes)")


def main() -> None:
    force = "--force" in sys.argv
    SOURCES.mkdir(exist_ok=True)
    CANDIDATE.mkdir(exist_ok=True)

    release, candidate_urls = scrape_downloads_page()
    version = f"{release[:2]}.{release[2:]}"
    print(f"UCDP release: {version}; candidate files: {len(candidate_urls)}")

    manifest = {
        "downloaded": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "ucdp_release": version,
        "files": {},
        "candidate_files": [],
    }

    for logical, (subdir, stem) in ZIPS.items():
        url = f"{UCDP}/{subdir}/{stem}-{release}-csv.zip"
        dest = SOURCES / f"{logical}.csv"
        manifest["files"][logical] = dest.name
        if dest.exists() and not force:
            print(f"  cached {dest.relative_to(ROOT)} (use --force to re-download)")
            continue
        fetch_zip_csv(url, dest)

    url = f"{UCDP}/ged/ged{release}-csv.zip"
    dest = SOURCES / "ucdp-ged.csv"
    manifest["files"]["ucdp-ged"] = dest.name
    if dest.exists() and not force:
        print(f"  cached {dest.relative_to(ROOT)} (use --force to re-download)")
    else:
        fetch_zip_csv(url, dest)

    for url in candidate_urls:
        dest = CANDIDATE / url.rsplit("/", 1)[1]
        manifest["candidate_files"].append(dest.name)
        if dest.exists() and not force:
            print(f"  cached {dest.relative_to(ROOT)}")
            continue
        fetch_file(url, dest)

    for name, url in GW_FILES.items():
        dest = SOURCES / name
        manifest["files"][name.removesuffix(".tsv")] = dest.name
        if dest.exists() and not force:
            print(f"  cached {dest.relative_to(ROOT)}")
            continue
        fetch_file(url, dest)

    with open(SOURCES / "manifest.yaml", "w") as f:
        yaml.safe_dump(manifest, f, sort_keys=False)
    print("wrote sources/manifest.yaml")


if __name__ == "__main__":
    main()
