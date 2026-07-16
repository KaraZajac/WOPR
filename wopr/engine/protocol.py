"""The tune/validate protocol — how a covariate earns its way into the engine.

The rule that makes the arena and backtest mean anything: you may search for
a conditioning scheme only on data you agree never to score, and you look at
the held-out data exactly once. This module enforces that for the youth
covariate (the descriptive-test winner), and it is the template for every
future covariate.

Split (by time, matching real deployment — fit on the past, judge on the
more-recent future):

  TUNE      scored years ≤ SPLIT — where candidate schemes compete
  VALIDATE  scored years >  SPLIT — untouched until the single final read

Procedure:
  1. Run the baseline engine and every candidate youth scheme walk-forward.
  2. On TUNE only, pick the youth scheme with the best Brier (the search).
  3. On VALIDATE only, compare that one scheme to the baseline. That ΔBrier
     is the verdict — and it is the only time VALIDATE is consulted.

A covariate is adopted iff it improves VALIDATE Brier. Anything else — a win
on TUNE that doesn't survive, a wash — means it stays out, and the negative
result is recorded (see docs/method.md). Whatever this prints, the live
engine is not changed by running it; adoption is a separate, deliberate edit.
"""

from wopr.engine import baserate
from wopr.engine.backtest import walk
from wopr.journal.score import brier

SPLIT = 2007  # scored years ≤ 2007 tune; ≥ 2008 validate (covariates begin ~1961)
# candidate youth schemes: the percentile cut that defines "young", built on
# TUNE-era data only so the threshold itself isn't fit on VALIDATE
CANDIDATE_PCTL = (0.50, 0.60, 0.66, 0.75)
SUITE = ("country", "acd-active", (), 25)  # youth predicts onset → the activity measure
# a covariate must beat the baseline on VALIDATE by at least this *relative*
# margin to be adopted. Set a priori: below it, the gain is noise-level and
# not worth the cell fragmentation a new bucket dimension costs. 1% of a
# ~0.04 Brier is ~0.0004 absolute — a low but non-trivial bar.
MIN_REL_GAIN = 0.01


def young_set(youth: dict, pctl: float, tune_only_years) -> set:
    """(gwno, year) whose under-14 share is above the `pctl` cut. The cut is
    computed from TUNE-era values only — never from validate years."""
    tune_vals = [v for (g, y), v in youth.items() if y <= tune_only_years]
    if not tune_vals:
        return set()
    tune_vals.sort()
    cut = tune_vals[int(len(tune_vals) * pctl)]
    return {(g, y) for (g, y), v in youth.items() if v > cut}


def split_brier(records, lo=None, hi=None):
    rows = [r for r in records if (lo is None or r["year"] >= lo) and (hi is None or r["year"] <= hi)]
    if not rows:
        return None, 0
    return sum(brier(r["p"], r["outcome"]) for r in rows) / len(rows), len(rows)


def run() -> dict:
    substrate = baserate.load_substrate()
    youth = substrate["youth"]
    if not youth:
        raise SystemExit("no covariates built — run `wopr pull && wopr build` first")
    grain, measure, types, threshold = SUITE

    baseline = walk(grain, measure, types, threshold, substrate)
    schemes = {}
    for pctl in CANDIDATE_PCTL:
        ys = young_set(youth, pctl, SPLIT)
        schemes[pctl] = walk(grain, measure, types, threshold, substrate, youth=ys)

    # 1) search on TUNE only
    base_tune, n_tune = split_brier(baseline, hi=SPLIT)
    tune_scores = {p: split_brier(recs, hi=SPLIT)[0] for p, recs in schemes.items()}
    best_pctl = min(tune_scores, key=lambda p: tune_scores[p])

    # 2) single read on VALIDATE
    base_val, n_val = split_brier(baseline, lo=SPLIT + 1)
    best_val, _ = split_brier(schemes[best_pctl], lo=SPLIT + 1)
    delta = best_val - base_val
    rel_gain = -delta / base_val if base_val else 0.0
    # honesty guard: a genuine covariate helps most cuts on tune, not one
    tune_helped = sum(1 for v in tune_scores.values() if v < base_tune)
    adopt = rel_gain >= MIN_REL_GAIN and tune_helped > len(tune_scores) / 2

    return {
        "split": SPLIT,
        "suite": f"{grain}/{measure}",
        "min_rel_gain": MIN_REL_GAIN,
        "tune": {
            "n": n_tune,
            "baseline_brier": round(base_tune, 5),
            "scheme_brier": {p: round(v, 5) for p, v in tune_scores.items()},
            "selected_pctl": best_pctl,
            "cuts_beating_baseline": f"{tune_helped}/{len(tune_scores)}",
        },
        "validate": {
            "n": n_val,
            "baseline_brier": round(base_val, 5),
            "selected_brier": round(best_val, 5),
            "delta_brier": round(delta, 5),
            "rel_gain": round(rel_gain, 4),
            "verdict": "ADOPT" if adopt else "REJECT — gain below the 1% bar / inconsistent on tune",
        },
    }


def render(r: dict) -> str:
    t, v = r["tune"], r["validate"]
    lines = [
        f"tune/validate protocol — youth conditioning on {r['suite']} (split at {r['split']})",
        "",
        f"TUNE ({t['n']:,} unit-years, ≤{r['split']}): baseline {t['baseline_brier']}",
        "  candidate youth cuts (Brier, lower=better):",
    ]
    for p, b in sorted(t["scheme_brier"].items()):
        mark = " ← selected" if p == t["selected_pctl"] else ""
        lines.append(f"    top-{int((1 - p) * 100)}% youngest: {b}{mark}")
    lines += [
        f"  cuts beating baseline on tune: {t['cuts_beating_baseline']}",
        "",
        f"VALIDATE ({v['n']:,} unit-years, >{r['split']}) — read once:",
        f"  baseline           {v['baseline_brier']}",
        f"  selected youth     {v['selected_brier']}",
        f"  ΔBrier             {v['delta_brier']:+}  ({v['rel_gain']:+.1%} relative)",
        f"  adoption bar       {r['min_rel_gain']:.0%} relative + majority of tune cuts helping",
        f"  → {v['verdict']}",
    ]
    return "\n".join(lines)
