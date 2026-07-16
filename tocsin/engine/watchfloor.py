"""The watchfloor: which places are diverging from their own base rate right
now? The original vision's early-warning board — "heating up faster than
history says it should" — made honest.

Signal, per country, entirely from committed UCDP data (displayable, CC BY):

  baseline    the unit's typical annual organized-violence deaths — the
              median of its trailing 5 complete years
  current     this year's pace annualized from candidate months
              (deaths so far ÷ months observed × 12)
  ratio       current ÷ max(baseline, FLOOR); >1 heating, <1 cooling
  onset       the engine bucket entering this year was cold/dormant, yet
              candidate months already crossed the activity line — the
              highest-value flag, a base-rate surprise in progress

Ranking is by a magnitude-weighted surprise so a village-scale doubling
never outranks a war-scale one; tiny absolute paces are floored out.

ACLED weeklies (through a more recent week than UCDP's candidate cutoff)
give an INDEPENDENT corroboration direction — rising/falling over the last
eight weeks vs the prior eight. Per ACLED's terms this is a derived signal
only: a direction flag, never their series. Absent ACLED data, the flag is
simply omitted.
"""

import csv
import datetime

from tocsin.engine import baserate
from tocsin.paths import SOURCES, TABLES

FLOOR = 25  # annualized-death floor: below this a ratio is noise, not a signal
TRAILING = 5  # complete years of baseline
HEAT = 1.5
COOL = 0.67
ACLED_EPOCH = datetime.date(1899, 12, 30)  # Excel serial origin


def _log2(x: float) -> float:
    import math

    return math.log2(x) if x > 0 else -99.0


def acled_direction(weeks=8) -> dict:
    """country name -> 'rising'|'falling'|'steady' over the last `weeks` vs
    the prior `weeks`, from the ACLED regional weeklies. Derived flag only —
    no counts leave this function (ACLED Content Usage Terms)."""
    import glob

    latest = 0
    fat: dict[str, dict[int, int]] = {}
    files = glob.glob(str(SOURCES / "acled" / "weekly-*.csv"))
    for path in files:
        with open(path, newline="") as f:
            for r in csv.DictReader(f):
                if not r["WEEK"].isdigit():
                    continue
                wk = int(r["WEEK"])
                latest = max(latest, wk)
                fat.setdefault(r["COUNTRY"], {})
                fat[r["COUNTRY"]][wk] = fat[r["COUNTRY"]].get(wk, 0) + int(r["FATALITIES"] or 0)
    if not latest:
        return {}
    recent = range(latest - 7 * weeks, latest + 1, 7)
    prior = range(latest - 7 * 2 * weeks, latest - 7 * weeks, 7)
    out = {}
    for country, series in fat.items():
        r = sum(series.get(w, 0) for w in recent)
        p = sum(series.get(w, 0) for w in prior)
        if r + p < 20:  # too little signal to call a direction
            continue
        out[country] = "rising" if r > p * 1.3 else "falling" if r < p * 0.7 else "steady"
    return out


def compute(substrate: dict | None = None, acled: dict | None = None) -> dict:
    substrate = substrate or baserate.load_substrate()
    partial = substrate.get("partial")
    if not partial:
        return {"year": None, "units": [], "acled_available": False}
    year, months = partial["year"], partial["months"]
    countries = substrate["country"]
    if acled is None:
        acled = acled_direction()

    units = []
    for g, cur in partial["country"].items():
        u = countries.get(g)
        if u is None:
            continue
        current_deaths = sum(cur.get(t, 0) for t in ("sb", "ns", "os"))
        annualized = round(current_deaths / months * 12)
        hist = [
            sum((u.years.get(y) or {}).get(t) or 0 for t in ("sb", "ns", "os"))
            for y in range(year - TRAILING, year)
            if y in u.years
        ]
        baseline = sorted(hist)[len(hist) // 2] if hist else 0
        name_g, region_g = u.name, (u.region[0] if u.region else "")
        ratio = annualized / max(baseline, FLOOR)
        # engine occurrence prior + whether candidate months forced a nowcast
        try:
            r = baserate.rate(baserate.Spec("country", g, "deaths", ("sb",), 25, year + 1), substrate)
            p, bucket, onset = r["p"], r["bucket_coarse"], "nowcast" in r
        except (KeyError, ValueError):
            p, bucket, onset = None, "cold", False
        direction = (
            "onset" if onset and baseline < FLOOR
            else "heating" if ratio >= HEAT and annualized >= FLOOR * 2
            else "cooling" if ratio <= COOL and baseline >= FLOOR * 2
            else "steady"
        )
        if direction == "steady":
            continue
        import math

        surprise = round(abs(_log2(ratio)) * math.log10(10 + annualized + baseline), 3)
        units.append(
            {
                "gwno": g,
                "name": name_g,
                "region": region_g,
                "direction": direction,
                "baseline": baseline,
                "annualized": annualized,
                "observed": current_deaths,
                "ratio": round(ratio, 2),
                "p": p,
                "bucket": bucket,
                "surprise": surprise,
                "acled": acled.get(name_g),
            }
        )
    units.sort(key=lambda u: -u["surprise"])
    return {
        "year": year,
        "months": months,
        "acled_available": bool(acled),
        "units": units,
    }


def render(board: dict) -> str:
    if not board["units"]:
        return "watchfloor: no candidate-year data to diverge against"
    lines = [
        f"watchfloor — {board['year']} pace vs trailing-5-year baseline ({board['months']} candidate months)",
        f"{'country':<24} {'dir':<8} {'base/yr':>8} {'now/yr':>8} {'×':>6} {'P(≥25)':>7} {'acled':>8}",
    ]
    for u in board["units"][:24]:
        lines.append(
            f"{u['name'][:24]:<24} {u['direction']:<8} {u['baseline']:>8} {u['annualized']:>8} "
            f"{u['ratio']:>6} {u['p'] if u['p'] is not None else '—':>7} {u['acled'] or '—':>8}"
        )
    return "\n".join(lines)
