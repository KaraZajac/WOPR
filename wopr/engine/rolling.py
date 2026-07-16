"""Rolling-window rates at month grain: P(≥T deaths within the W months
starting at month m0) — the exact question a "next 12 months" or "H2 2026"
window asks, instead of the calendar-year approximation.

Same estimator as the annual engine, ported to months. A unit's status
entering month m is its trailing-12-month record R(m); buckets band the
consecutive-R run (episode age) or the gap since R last held, in month units
that mirror the annual bands. Class rates count member window-starts in the
same bucket whose windows complete inside final (non-candidate) data; the
target's own bucket may use candidate months — they are real observations at
this grain, just provisional (noted).

Honesty notes: window-starts overlap (a 12-month window shares 11 months
with its neighbor), so counts are not independent observations — rates and
calibration read fine, but dispersion-based shrinkage and floors treat
months as independent and thus overstate certainty a little. January-start
12-month windows are calendar years, where this engine provably matches the
annual one (tested). Country and dyad grains only; pairs stay annual.
"""

import csv
from dataclasses import dataclass

from wopr.engine.baserate import (
    AGE_BANDS,
    MIN_CLASS_YEARS,
    Unit,
    class_units,
    coarse,
    eb_strength,
)
from wopr.paths import TABLES

START = 1989 * 12  # month index of 1989-01; index = year*12 + (month-1)
MIN_CLASS_MONTHS = MIN_CLASS_YEARS * 12


def mi(year: int, month: int) -> int:
    return year * 12 + (month - 1)


def ym(index: int) -> str:
    return f"{index // 12:04d}-{index % 12 + 1:02d}"


@dataclass
class RollingSpec:
    grain: str  # country | dyad
    unit: int
    types: tuple = ("sb",)
    threshold: int = 25
    window: int = 12  # months
    start: int = 0  # month index of the window's first month
    class_end: int = 0  # walk-forward clamp: use no data past this month (0 = all)


def load_monthly(substrate: dict, tables=TABLES) -> dict:
    """Dense per-unit monthly death arrays layered over the annual substrate
    (which supplies exposure and regions). Returns {"country": {gwno: arr},
    "dyad": {...}, "start": START, "final_end": mi, "data_end": mi}."""
    final_end = mi(substrate["last_year"], 12)
    data_end = final_end
    arrays: dict[str, dict[int, list]] = {"country": {}, "dyad": {}}

    def arr_for(store: dict, uid: int, upto: int):
        a = store.get(uid)
        if a is None or len(a) < upto - START + 1:
            new = [0] * (upto - START + 1)
            if a:
                new[: len(a)] = a
            store[uid] = a = new
        return a

    with open(tables / "country-month.csv", newline="") as f:
        for r in csv.DictReader(f):
            m = mi(int(r["year"]), int(r["month"]))
            data_end = max(data_end, m)
    with open(tables / "country-month.csv", newline="") as f:
        for r in csv.DictReader(f):
            m = mi(int(r["year"]), int(r["month"]))
            a = arr_for(arrays["country"], int(r["gwno"]), data_end)
            a[m - START] = {t: int(r[f"{t}_deaths"]) for t in ("sb", "ns", "os")}
    with open(tables / "dyad-month.csv", newline="") as f:
        for r in csv.DictReader(f):
            if r["type"] != "sb":
                continue
            m = mi(int(r["year"]), int(r["month"]))
            a = arr_for(arrays["dyad"], int(r["dyad_id"]), data_end)
            a[m - START] = {"sb": int(r["deaths"])}
    return {"country": arrays["country"], "dyad": arrays["dyad"], "final_end": final_end, "data_end": data_end}


def cumsum(monthly: dict, uid: int, types: tuple, data_end: int) -> list:
    """Prefix sums C where C[i] = deaths in months [START, START+i)."""
    raw = monthly.get(uid) or []
    n = data_end - START + 1
    C = [0] * (n + 1)
    for i in range(n):
        cell = raw[i] if i < len(raw) and raw[i] else {}
        C[i + 1] = C[i] + sum(cell.get(t, 0) for t in types)
    return C


def window_sum(C: list, m0: int, W: int) -> int | None:
    lo, hi = m0 - START, m0 - START + W
    if lo < 0 or hi > len(C) - 1:
        return None  # window not fully observable
    return C[hi] - C[lo]


def exposed(u: Unit, spec: RollingSpec, m: int) -> bool:
    year = m // 12
    if spec.grain == "country":
        return year in u.years
    return year >= max(u.first_year, 1989)


def bucket_series(C: list, spec: RollingSpec) -> dict[int, str]:
    """Bucket entering each month, from trailing-12-month records strictly
    before it — one forward pass, so episode runs cost O(1) per month.
    Defined from START+12 (a full trailing year of history) through the last
    month with a complete trailing window."""
    out: dict[int, str] = {}
    run = 0
    last_R = None
    for m in range(START + 12, START + len(C)):
        s = window_sum(C, m - 12, 12)
        if s is None:
            break
        if s >= spec.threshold:
            run += 1
            last_R = m
            years = (run + 11) // 12
            for lo, hi, name in AGE_BANDS:
                if lo <= years <= hi:
                    out[m] = name
                    break
        else:
            run = 0
            if last_R is None:
                out[m] = "cold"
            else:
                # last_R trails the underlying activity by up to 12 months, so
                # these cutoffs sit 12 under the annual bands (2-3y recent,
                # 4-10y dormant) and align exactly in year terms at any phase
                gap = m - last_R
                out[m] = "recent" if gap <= 24 else "dormant" if gap <= 108 else "cold"
    return out


def bucket_m(C: list, m: int, spec: RollingSpec) -> str | None:
    return bucket_series(C, spec).get(m)


def unit_counts(
    C: list, buckets: dict[int, str], u: Unit, spec: RollingSpec, bucket: str, last_start: int
) -> tuple[int, int]:
    """(hits, window-starts) for u in `bucket`, windows completing in final data."""
    k = n = 0
    for m in range(START + 12, last_start + 1):
        if buckets.get(m) != bucket or not exposed(u, spec, m):
            continue
        s = window_sum(C, m, spec.window)
        if s is None:
            continue
        n += 1
        k += int(s >= spec.threshold)
    return k, n


def rate(spec: RollingSpec, substrate: dict, monthly: dict) -> dict:
    units = substrate[spec.grain]
    if spec.unit not in units:
        raise KeyError(f"unknown {spec.grain} id {spec.unit}")
    me = units[spec.unit]
    final_end, data_end = monthly["final_end"], monthly["data_end"]
    if spec.class_end:  # retrospective vantage: nothing after class_end exists
        final_end = min(final_end, spec.class_end)
        data_end = min(data_end, spec.class_end)
    last_start = final_end - spec.window + 1  # class windows stay inside final data

    csums: dict[int, list] = {}
    bseries: dict[int, dict] = {}

    def C(uid: int) -> list:
        if uid not in csums:
            csums[uid] = cumsum(monthly[spec.grain], uid, spec.types, data_end)
        return csums[uid]

    def B(uid: int) -> dict:
        if uid not in bseries:
            bseries[uid] = bucket_series(C(uid), spec)
        return bseries[uid]

    bucket_at = min(spec.start, data_end + 1)
    bucket = B(me.id).get(bucket_at) or "cold"
    provisional = bucket_at - 1 > final_end
    k_self, n_self = unit_counts(C(me.id), B(me.id), me, spec, bucket, last_start)

    # borrow the annual engine's class machinery via a shim spec
    class _S:
        grain = spec.grain
        unit = spec.unit

    out = {
        "spec": {
            "grain": spec.grain,
            "unit": spec.unit,
            "measure": "deaths",
            "types": list(spec.types),
            "threshold": spec.threshold,
            "window_months": spec.window,
            "start_month": ym(spec.start),
        },
        "unit_name": me.name or str(me.id),
        "bucket": bucket,
        "bucket_coarse": coarse(bucket),
        "bucket_data_end": ym(min(spec.start - 1, data_end)),
        "levels": {},
        "notes": [],
    }
    posteriors = {}
    for level in ("self", "region", "global"):
        members = class_units(_S, substrate, level)
        counts = [unit_counts(C(m.id), B(m.id), m, spec, bucket, last_start) for m in members]
        K = sum(k for k, _ in counts)
        N = sum(n for _, n in counts)
        entry = {"units": len(members), "months": N, "hits": K, "rate": round(K / N, 4) if N else None}
        if level != "self" and N:
            M = eb_strength(counts)
            post = (k_self + M * (K / N)) / (n_self + M)
            entry["M"] = round(M, 1)
            entry["posterior"] = round(post, 4)
            posteriors[level] = (post, N)
        out["levels"][level] = entry

    if posteriors:
        use = "region" if posteriors.get("region") and posteriors["region"][1] >= MIN_CLASS_MONTHS else "global"
        if use not in posteriors:
            use = next(iter(posteriors))
        p, n_level = posteriors[use]
    else:
        use, p, n_level = "global-unconditional", 0.0, 1
    floor = 0.5 / (n_level + 1)
    out["headline_level"] = use
    out["p"] = round(min(max(p, floor), 1 - floor), 4)
    out["notes"].append(
        f"rolling {spec.window}-month window from {ym(spec.start)}; class counts are overlapping "
        "window-starts (rates read fine; dispersion slightly overstated)"
    )
    if provisional:
        out["notes"].append("target bucket uses preliminary candidate months")
    if spec.grain == "dyad":
        out["notes"].append("dyad universe = dyads UCDP ever observed; recurrence rate, not an arbitrary-pair rate")
    return out


def render(result: dict) -> str:
    spec = result["spec"]
    lines = [
        f"{result['unit_name']} ({spec['grain']} {spec['unit']}) — "
        f"P({'/'.join(spec['types'])} deaths ≥ {spec['threshold']} within {spec['window_months']} months)",
        f"window starts {spec['start_month']} · bucket: {result['bucket']} "
        f"(history through {result['bucket_data_end']}) · monthly substrate 1989–",
        "",
        f"{'level':<8} {'units':>6} {'months':>8} {'hits':>6} {'rate':>7} {'M':>7} {'posterior':>10}",
    ]
    for level, e in result["levels"].items():
        lines.append(
            f"{level:<8} {e['units']:>6} {e['months']:>8} {e['hits']:>6} "
            f"{e['rate'] if e['rate'] is not None else '—':>7} "
            f"{e.get('M', '—'):>7} {e.get('posterior', '—'):>10}"
        )
    lines.append("")
    lines.append(f"headline: p = {result['p']}  ({result['headline_level']} posterior, bucket-conditional)")
    for n in result["notes"]:
        lines.append(f"note: {n}")
    return "\n".join(lines)
