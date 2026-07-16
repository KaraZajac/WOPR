"""VIEWS (Uppsala Violence & Impacts Early-Warning System) — the first named
challenger. Their open API publishes monthly country-month runs
(fatalities002_YYYY_MM_t01); each run carries `main_dich`, a per-month
probability, and `main_mean`, expected state-based fatalities.

Two empirical anchors, because assuming either would be astrology:

  month alignment   VIEWS month_id 1 = 1980-01 (verified against row
                    year/month fields at fetch time)
  dich semantics    is main_dich P(≥1 sb death in the month) or P(≥25)?
                    detect_dich() joins old runs' near-horizon predictions to
                    realized UCDP monthly outcomes and reports which threshold
                    main_dich is actually calibrated against.

Runs are cached under sources/views/ (gitignored, regenerable).
"""

import json
import urllib.request

import yaml

from tocsin.engine.rolling import mi
from tocsin.paths import ROOT, SOURCES
from tocsin.pipeline.build import to_gw

API = "https://api.viewsforecasting.org"
UA = {"User-Agent": "TOCSIN-pipeline/0.3 (academic research)"}
DEST = SOURCES / "views"
KEEP = ("gwcode", "name", "month_id", "year", "month", "main_dich", "main_mean")


def _get(url: str):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=120) as r:
        return json.loads(r.read())


def list_runs() -> list[str]:
    return sorted(r for r in _get(API + "/")["runs"] if r.startswith("fatalities002_"))


def vantage_of(run: str) -> int:
    """Month index of the run's vantage (its name month); forecasts start +1."""
    _, y, m, _ = run.split("_")
    return mi(int(y), int(m))


def fetch_run(run: str, force: bool = False) -> list[dict]:
    DEST.mkdir(parents=True, exist_ok=True)
    cache = DEST / f"{run}.json"
    if cache.exists() and not force:
        return json.loads(cache.read_text())
    rows, url = [], f"{API}/{run}/cm?pagesize=1000"
    while url:
        page = _get(url)
        rows.extend({k: r.get(k) for k in KEEP} for r in page.get("data", []))
        url = page.get("next_page") or None
    # verify the month_id epoch against the row's own year/month fields
    for r in rows[:50]:
        if r["year"] and r["month"]:
            assert mi(int(r["year"]), int(r["month"])) == 1980 * 12 + int(r["month_id"]) - 1, (
                f"VIEWS month_id epoch drifted: {r}"
            )
    cache.write_text(json.dumps(rows, separators=(",", ":")))
    print(f"  -> {cache.relative_to(ROOT)} ({len(rows):,} rows)")
    return rows


def month_index(row: dict) -> int:
    return 1980 * 12 + int(row["month_id"]) - 1


def realized_hits(monthly: dict, threshold: int) -> dict:
    """(gwno, month_index) -> 0/1 for sb deaths ≥ threshold, from our tables."""
    out = {}
    for gwno, arr in monthly["country"].items():
        for i, cell in enumerate(arr or []):
            deaths = (cell or {}).get("sb", 0)
            out[(gwno, 1989 * 12 + i)] = 1 if deaths >= threshold else 0
    return out


def detect_dich(runs: list[str], monthly: dict, horizons=(1, 2, 3)) -> dict:
    """Which threshold is main_dich calibrated against? Compare mean predicted
    probability to realized frequency at ≥1 and ≥25 over near-horizon months
    of finalized (annual-covered) data."""
    hits1 = realized_hits(monthly, 1)
    hits25 = realized_hits(monthly, 25)
    final_end = monthly["final_end"]
    preds = []
    for run in runs:
        v = vantage_of(run)
        wanted = {v + h for h in horizons if v + h <= final_end}
        if not wanted:
            continue
        for r in fetch_run(run):
            m = month_index(r)
            if m in wanted and r["main_dich"] is not None:
                gwno = to_gw(int(r["gwcode"]), m // 12)
                if (gwno, m) in hits1:
                    preds.append((r["main_dich"], hits1[(gwno, m)], hits25[(gwno, m)]))
    n = len(preds)
    mean_p = sum(p for p, _, _ in preds) / n
    freq1 = sum(h for _, h, _ in preds) / n
    freq25 = sum(h for _, _, h in preds) / n
    verdict = 1 if abs(mean_p - freq1) < abs(mean_p - freq25) else 25
    return {
        "n": n,
        "mean_dich": round(mean_p, 4),
        "freq_ge1": round(freq1, 4),
        "freq_ge25": round(freq25, 4),
        "threshold": verdict,
    }


def write_manifest(runs: list[str], dich: dict) -> None:
    with open(DEST / "manifest.yaml", "w") as f:
        yaml.safe_dump({"runs_cached": runs, "dich_semantics": dich}, f, sort_keys=False)
