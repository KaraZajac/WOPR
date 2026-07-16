"""Rolling-window rates at month grain: P(≥T deaths within the W months
starting at month m0) — the exact question a "next 12 months" or "H2 2026"
window asks, instead of the calendar-year approximation.

Same estimator family as the annual engine, ported to months, with three
covariates the arena demanded:

  bucket    trailing-12-month status, episode age in month-years
  tempo     active buckets carry the count of trailing months individually
            over the threshold (low 1–3 / mid 4–8 / high 9–12) — sustained
            wars and single-spike years are different classes
  neighbor  NON-active buckets carry a "+nbr" suffix when any ≤400km
            neighbor is in active conflict (trailing year ≥25 sb deaths) —
            spatial contagion, the strongest known onset covariate, applied
            exactly where onsets happen

and one estimator upgrade: **horizon-aware class rates**. A window starting
g months past the edge of observation is priced by class windows starting g
months after each class month — P(hit in [m+g, m+g+W)| bucket at m) — not by
the one-step rate applied flat.

All paths (single-question rate() and the benchmark's batch tables) share
build_state()/assemble(), so they cannot drift. Honesty notes: window-starts
overlap (rates and calibration read fine; dispersion slightly overstated);
tempo/neighbor bands were fixed a priori, never tuned against the arena.
Country and dyad grains; neighbor applies to countries only; pairs stay
annual.
"""

import csv
from collections import defaultdict
from dataclasses import dataclass

from tocsin.engine.baserate import (
    AGE_BANDS,
    MIN_CLASS_YEARS,
    Unit,
    coarse,
    eb_strength,
)
from tocsin.paths import TABLES

START = 1989 * 12  # month index of 1989-01; index = year*12 + (month-1)
MIN_CLASS_MONTHS = MIN_CLASS_YEARS * 12
NEIGHBOR_KM = 400

# tempo bands refine ACTIVE buckets only: the count of individual months over
# the threshold in the trailing year separates a sustained war (12/12) from a
# single-spike year (1/12) — the arena priced pooling them at ~0.017 Brier.
# A non-active unit necessarily has zero month-hits at the same threshold.
TEMPO_BANDS = ((1, 3, "low"), (4, 8, "mid"), (9, 12, "high"))


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


# ---------------------------------------------------------------- loading


def load_monthly(substrate: dict, tables=TABLES) -> dict:
    """Dense per-unit monthly death arrays layered over the annual substrate
    (which also supplies exposure, regions, and the neighbor map)."""
    final_end = mi(substrate["last_year"], 12)
    data_end = final_end
    arrays: dict[str, dict[int, list]] = {"country": {}, "dyad": {}}

    def arr_for(store: dict, uid: int, upto: int):
        a = store.get(uid)
        if a is None or len(a) < upto - START + 1:
            new = [None] * (upto - START + 1)
            if a:
                new[: len(a)] = a
            store[uid] = a = new
        return a

    with open(tables / "country-month.csv", newline="") as f:
        for r in csv.DictReader(f):
            data_end = max(data_end, mi(int(r["year"]), int(r["month"])))
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
    return {
        "country": arrays["country"],
        "dyad": arrays["dyad"],
        "final_end": final_end,
        "data_end": data_end,
    }


def prefixes(monthly: dict, uid: int, types: tuple, data_end: int, threshold: int = 25) -> tuple[list, list]:
    """(C, H): C[i] = deaths in months [START, START+i); H[i] = count of
    months in that span individually ≥ threshold (the tempo signal)."""
    raw = monthly.get(uid) or []
    n = data_end - START + 1
    C = [0] * (n + 1)
    H = [0] * (n + 1)
    for i in range(n):
        cell = raw[i] if i < len(raw) and raw[i] else {}
        d = sum(cell.get(t, 0) for t in types)
        C[i + 1] = C[i] + d
        H[i + 1] = H[i] + (1 if d >= threshold else 0)
    return C, H


def cumsum(monthly: dict, uid: int, types: tuple, data_end: int, threshold: int = 25) -> list:
    return prefixes(monthly, uid, types, data_end, threshold)[0]


def window_sum(C: list, m0: int, W: int) -> int | None:
    lo, hi = m0 - START, m0 - START + W
    if lo < 0 or hi > len(C) - 1:
        return None  # window not fully observable
    return C[hi] - C[lo]


def exposed(u: Unit, grain: str, m: int) -> bool:
    year = m // 12
    if grain == "country":
        return year in u.years
    return year >= max(u.first_year, 1989)


# ---------------------------------------------------------------- buckets


def bucket_series(C: list, spec: RollingSpec, H: list | None = None, nbr=None) -> dict[int, str]:
    """Bucket entering each month, from trailing-12-month records strictly
    before it — one forward pass, so episode runs cost O(1) per month.
    Active buckets carry a tempo suffix when the hit-prefix H is supplied;
    non-active buckets carry "+nbr" when nbr(m) says a neighbor is at war."""
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
                    if H is not None:
                        hits = H[m - START] - H[m - 12 - START]
                        tempo = next((t for lo_t, hi_t, t in TEMPO_BANDS if lo_t <= hits <= hi_t), "low")
                        name = f"{name}|{tempo}"
                    out[m] = name
                    break
        else:
            run = 0
            if last_R is None:
                base = "cold"
            else:
                # last_R trails the underlying activity by up to 12 months, so
                # these cutoffs sit 12 under the annual bands (2-3y recent,
                # 4-10y dormant) and align exactly in year terms at any phase
                gap = m - last_R
                base = "recent" if gap <= 24 else "dormant" if gap <= 108 else "cold"
            out[m] = f"{base}+nbr" if nbr is not None and nbr(m) else base
    return out


def bucket_m(C: list, m: int, spec: RollingSpec) -> str | None:
    return bucket_series(C, spec).get(m)


# ---------------------------------------------------------------- the core


def build_state(grain, substrate, monthly, types=("sb",), threshold=25, window=1, class_end=0, gaps=(0,)):
    """Everything a query needs, computed once: per-unit bucket series (tempo
    + neighbor suffixes), and per-(unit, bucket, gap) window-hit counts over
    class months whose windows complete inside final data. Shared by rate()
    and the benchmark so the two cannot diverge."""
    units = substrate[grain]
    final_end, data_end = monthly["final_end"], monthly["data_end"]
    if class_end:
        final_end = min(final_end, class_end)
        data_end = min(data_end, class_end)

    spec = RollingSpec(grain, 0, tuple(types), threshold, window, 0, class_end)
    pref = {uid: prefixes(monthly[grain], uid, tuple(types), data_end, threshold) for uid in units}

    nbr_of = {}
    if grain == "country":
        # a neighbor is "at war" when its own trailing year has ≥25 sb deaths
        if tuple(types) == ("sb",) and threshold == 25:
            p25 = pref
        else:
            p25 = {uid: prefixes(monthly[grain], uid, ("sb",), data_end, 25) for uid in units}
        active25 = {}
        for uid, (C25, _) in p25.items():
            arr = [False] * (data_end + 2 - START)
            for m in range(START + 12, data_end + 2):
                s = window_sum(C25, m - 12, 12)
                arr[m - START] = s is not None and s >= 25
            active25[uid] = arr
        neighbors = substrate.get("neighbors", {})

        def make_nbr(uid):
            def nbr(m):
                for n in neighbors.get(uid, {}).get(m // 12, ()):
                    a = active25.get(n)
                    if a and m - START < len(a) and a[m - START]:
                        return True
                return False

            return nbr

        nbr_of = {uid: make_nbr(uid) for uid in units}

    buckets = {
        uid: bucket_series(pref[uid][0], spec, pref[uid][1], nbr_of.get(uid))
        for uid in units
    }

    per_unit: dict[tuple, list] = defaultdict(lambda: [0, 0])  # (uid,b,g) -> [k,n]
    for uid, u in units.items():
        C = pref[uid][0]
        bs = buckets[uid]
        for m, b in bs.items():
            if not exposed(u, grain, m):
                continue
            for g in gaps:
                s = window_sum(C, m + g, window)
                if s is None or m + g + window - 1 > final_end:
                    continue
                cell = per_unit[(uid, b, g)]
                cell[1] += 1
                cell[0] += int(s >= threshold)

    sig_of = {uid: tuple(sorted(set(u.region))) or ("__all__",) for uid, u in units.items()}
    members_by_sig = {
        sig: [uid for uid, u in units.items() if sig == ("__all__",) or set(u.region) & set(sig)]
        for sig in set(sig_of.values())
    }
    members_by_sig[("__global__",)] = list(units)

    return {
        "grain": grain,
        "units": units,
        "threshold": threshold,
        "types": tuple(types),
        "window": window,
        "gaps": tuple(gaps),
        "final_end": final_end,
        "data_end": data_end,
        "buckets": buckets,
        "per_unit": per_unit,
        "sig_of": sig_of,
        "members_by_sig": members_by_sig,
        "_cell_cache": {},
    }


def _class_cell(state, sig, bucket, g):
    key = (sig, bucket, g)
    if key not in state["_cell_cache"]:
        counts = [tuple(state["per_unit"].get((uid, bucket, g), (0, 0))) for uid in state["members_by_sig"][sig]]
        K = sum(k for k, _ in counts)
        N = sum(n for _, n in counts)
        state["_cell_cache"][key] = (K, N, eb_strength(counts) if N else 0.0)
    return state["_cell_cache"][key]


def assemble(state, uid: int, target_month: int) -> dict:
    """Price one unit-window using the state's cells: bucket at the edge of
    observation, class windows offset by the same staleness gap."""
    edge = min(target_month, state["data_end"] + 1)
    g = target_month - edge
    g = min(state["gaps"], key=lambda x: abs(x - g)) if g not in state["gaps"] else g
    bucket = state["buckets"][uid].get(edge) or "cold"
    k_self, n_self = state["per_unit"].get((uid, bucket, g), (0, 0))

    out = {"bucket": bucket, "bucket_coarse": coarse(bucket), "gap": g, "edge": ym(edge), "levels": {}}
    posteriors = {}
    for level, sig in (("self", None), ("region", state["sig_of"][uid]), ("global", ("__global__",))):
        if level == "self":
            out["levels"]["self"] = {
                "units": 1,
                "months": n_self,
                "hits": k_self,
                "rate": round(k_self / n_self, 4) if n_self else None,
            }
            continue
        K, N, M = _class_cell(state, sig, bucket, g)
        entry = {
            "units": len(state["members_by_sig"][sig]),
            "months": N,
            "hits": K,
            "rate": round(K / N, 4) if N else None,
        }
        if N:
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
    return out


# ---------------------------------------------------------------- queries


def rate(spec: RollingSpec, substrate: dict, monthly: dict) -> dict:
    units = substrate[spec.grain]
    if spec.unit not in units:
        raise KeyError(f"unknown {spec.grain} id {spec.unit}")
    me = units[spec.unit]
    data_end = min(monthly["data_end"], spec.class_end) if spec.class_end else monthly["data_end"]
    gap = max(0, spec.start - (data_end + 1))
    # one-step frozen, deliberately: horizon-aware class decay was measured
    # WORSE in the arena (+0.003 Brier) — class-level decay pools units that
    # exit conflict, underpricing the ones that persist. See docs/method.md.
    state = build_state(
        spec.grain, substrate, monthly,
        types=spec.types, threshold=spec.threshold, window=spec.window,
        class_end=spec.class_end, gaps=(0,),
    )
    out = assemble(state, spec.unit, spec.start)
    out["spec"] = {
        "grain": spec.grain,
        "unit": spec.unit,
        "measure": "deaths",
        "types": list(spec.types),
        "threshold": spec.threshold,
        "window_months": spec.window,
        "start_month": ym(spec.start),
    }
    out["unit_name"] = me.name or str(me.id)
    out["bucket_data_end"] = out.pop("edge")
    out["notes"] = [
        f"rolling {spec.window}-month window from {ym(spec.start)}; class counts are overlapping "
        "window-starts (rates read fine; dispersion slightly overstated)"
    ]
    if gap:
        out["notes"].append(
            f"window starts {gap} month(s) past the data edge: bucket taken at the edge, one-step "
            "rate applied frozen (horizon-aware class decay measured worse — see method.md)"
        )
    if spec.start - 1 > state["final_end"]:
        out["notes"].append("target bucket uses preliminary candidate months")
    if "+nbr" in out["bucket"]:
        out["notes"].append("a ≤400km neighbor is in active conflict (spatial-contagion class)")
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
