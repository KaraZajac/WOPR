"""The tune/validate protocol — how a covariate earns its way into the engine.

The rule that makes the arena and backtest mean anything: you may search for
a conditioning scheme only on data you agree never to score, and you look at
the held-out data exactly once. Two studies live here — youth on the country
grain (run/render) and the COW pair covariates (run_pair/render_pair) — and
they are the template for every future covariate. Verdicts so far: youth
REJECTED, all four COW pair features REJECTED (see docs/method.md; the pair
study also exposed that Brier is nearly blind at pair-grain base rates).

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

from tocsin.engine import baserate
from tocsin.engine.backtest import walk
from tocsin.journal.score import brier

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
        raise SystemExit("no covariates built — run `tocsin pull && tocsin build` first")
    grain, measure, types, threshold = SUITE

    baseline = walk(grain, measure, types, threshold, substrate)
    schemes = {}
    for pctl in CANDIDATE_PCTL:
        ys = young_set(youth, pctl, SPLIT)
        schemes[pctl] = walk(grain, measure, types, threshold, substrate, flag=ys)

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


PAIR_SUITE = ("pair", "acd-active", (), 25)


def pair_candidates(substrate: dict) -> dict[str, set]:
    """Pre-registered pair-level covariate candidates from COW, each a set of
    (pair_id, year) keys meaning "true as of the end of `year`". All are
    walk-forward-safe: membership at year Y uses only events ≤ Y.

    Censoring note, fixed before looking at any score: MID coding ends 2014
    and alliances end 2012. ever-/fatal-mid don't censor (history is
    permanent). mid-25yr sees a shrinking window after 2014. defense-pact
    carries the last observed (2012) status forward, the same rule as the
    population table."""
    pair_ids, mids, alliances = substrate["pair_ids"], substrate["mids"], substrate["alliances"]
    last = substrate["last_year"]
    ever, fatal, recent, defense = set(), set(), set(), set()
    for key, disputes in mids.items():
        pid = pair_ids.get(key)
        if pid is None:
            continue
        years = sorted(y for y, _, _ in disputes)
        for y in range(years[0], last + 1):
            ever.add((pid, y))
        fyears = sorted(y for y, _, f in disputes if f)
        for y in range(fyears[0], last + 1) if fyears else ():
            fatal.add((pid, y))
        for y in range(years[0], last + 1):
            if any(y - 24 <= d <= y for d in years):
                recent.add((pid, y))
    for key, years in alliances.items():
        pid = pair_ids.get(key)
        if pid is None:
            continue
        for y in years:
            defense.add((pid, y))
        if max(years) >= 2012:  # in force at the data edge -> carry forward
            for y in range(2013, last + 1):
                defense.add((pid, y))
    return {"ever-mid": ever, "mid-25yr": recent, "fatal-mid": fatal, "defense-pact": defense}


def run_pair() -> dict:
    """The pair study: does COW dispute/alliance history earn a bucket split
    in the pair universe? Same split and bar as the youth study; because the
    candidates are heterogeneous features (not cuts of one variable), the
    consistency guard becomes: the selected candidate must itself beat the
    baseline on TUNE, not merely be the least bad."""
    substrate = baserate.load_substrate()
    if not substrate["mids"]:
        raise SystemExit("no mids.csv built — run `tocsin pull && tocsin build` first")
    grain, measure, types, threshold = PAIR_SUITE

    baseline = walk(grain, measure, types, threshold, substrate)
    candidates = pair_candidates(substrate)
    schemes = {name: walk(grain, measure, types, threshold, substrate, flag=fs) for name, fs in candidates.items()}

    base_tune, n_tune = split_brier(baseline, hi=SPLIT)
    tune_scores = {name: split_brier(recs, hi=SPLIT)[0] for name, recs in schemes.items()}
    best = min(tune_scores, key=lambda k: tune_scores[k])

    base_val, n_val = split_brier(baseline, lo=SPLIT + 1)
    best_val, _ = split_brier(schemes[best], lo=SPLIT + 1)
    delta = best_val - base_val
    rel_gain = -delta / base_val if base_val else 0.0
    helped = sum(1 for v in tune_scores.values() if v < base_tune)
    adopt = rel_gain >= MIN_REL_GAIN and tune_scores[best] < base_tune

    return {
        "split": SPLIT,
        "suite": f"{grain}/{measure}",
        "min_rel_gain": MIN_REL_GAIN,
        "flag_sizes": {k: len(v) for k, v in candidates.items()},
        "tune": {
            "n": n_tune,
            "baseline_brier": round(base_tune, 6),
            "scheme_brier": {k: round(v, 6) for k, v in tune_scores.items()},
            "selected": best,
            "candidates_beating_baseline": f"{helped}/{len(tune_scores)}",
        },
        "validate": {
            "n": n_val,
            "baseline_brier": round(base_val, 6),
            "selected_brier": round(best_val, 6),
            "delta_brier": round(delta, 6),
            "rel_gain": round(rel_gain, 4),
            "verdict": "ADOPT" if adopt else "REJECT — below the 1% bar / doesn't beat baseline on tune",
        },
    }


def run_joint() -> dict:
    """The joint study — "what if the covariates were combined?" Answered
    narrowly and finally: the one untested, descriptively-motivated
    combination is youth × ethnic exclusion (the 2×2 showed 8.6% onset for
    young+excluded vs 2.9% for older/low-exclusion). Pre-registered
    candidates, all cuts at the top-third computed on TUNE years only:

      excluded        top-third excluded_share alone (never tested solo)
      young+excluded  AND of the two flags — a 2-cell split, deliberately
                      NOT a cross-product, to avoid regime-style
                      fragmentation
      young|excluded  OR of the two (the broad version)

    Combinations excluded a priori: anything at pair grain (Brier is blind
    there regardless — see the COW study), and regime × anything (regime
    fragmented cells and measured worse everywhere).

    THIS IS THE LAST STUDY ON THE 2007 VANTAGE SPLIT. Country-grain validate
    has now been consulted twice (youth, this); further covariate work must
    pre-register on a fresh era (2026+ outcomes) or the split stops meaning
    anything."""
    substrate = baserate.load_substrate()
    youth, excluded = substrate["youth"], substrate["excluded"]
    if not excluded:
        raise SystemExit("no covariates built — run `tocsin pull && tocsin build` first")
    grain, measure, types, threshold = SUITE

    young = young_set(youth, 0.66, SPLIT)
    excl = young_set(excluded, 0.66, SPLIT)
    candidates = {
        "excluded": excl,
        "young+excluded": young & excl,
        "young|excluded": young | excl,
    }

    baseline = walk(grain, measure, types, threshold, substrate)
    schemes = {name: walk(grain, measure, types, threshold, substrate, flag=fs) for name, fs in candidates.items()}

    base_tune, n_tune = split_brier(baseline, hi=SPLIT)
    tune_scores = {name: split_brier(recs, hi=SPLIT)[0] for name, recs in schemes.items()}
    best = min(tune_scores, key=lambda k: tune_scores[k])

    base_val, n_val = split_brier(baseline, lo=SPLIT + 1)
    best_val, _ = split_brier(schemes[best], lo=SPLIT + 1)
    delta = best_val - base_val
    rel_gain = -delta / base_val if base_val else 0.0
    helped = sum(1 for v in tune_scores.values() if v < base_tune)
    adopt = rel_gain >= MIN_REL_GAIN and tune_scores[best] < base_tune

    return {
        "split": SPLIT,
        "suite": f"{grain}/{measure}",
        "min_rel_gain": MIN_REL_GAIN,
        "flag_sizes": {k: len(v) for k, v in candidates.items()},
        "tune": {
            "n": n_tune,
            "baseline_brier": round(base_tune, 5),
            "scheme_brier": {k: round(v, 5) for k, v in tune_scores.items()},
            "selected": best,
            "candidates_beating_baseline": f"{helped}/{len(tune_scores)}",
        },
        "validate": {
            "n": n_val,
            "baseline_brier": round(base_val, 5),
            "selected_brier": round(best_val, 5),
            "delta_brier": round(delta, 5),
            "rel_gain": round(rel_gain, 4),
            "verdict": "ADOPT" if adopt else "REJECT — below the 1% bar / doesn't beat baseline on tune",
        },
    }


def render_joint(r: dict) -> str:
    t, v = r["tune"], r["validate"]
    lines = [
        f"tune/validate protocol — joint covariates on {r['suite']} (split at {r['split']}; FINAL study on this split)",
        "",
        f"TUNE ({t['n']:,} unit-years, ≤{r['split']}): baseline {t['baseline_brier']}",
        "  candidates (Brier, lower=better):",
    ]
    for name, b in sorted(t["scheme_brier"].items(), key=lambda kv: kv[1]):
        mark = " ← selected" if name == t["selected"] else ""
        lines.append(f"    {name:<15} {b}  ({r['flag_sizes'][name]:,} flagged unit-years){mark}")
    lines += [
        f"  candidates beating baseline on tune: {t['candidates_beating_baseline']}",
        "",
        f"VALIDATE ({v['n']:,} unit-years, >{r['split']}) — read once:",
        f"  baseline           {v['baseline_brier']}",
        f"  selected           {v['selected_brier']}",
        f"  ΔBrier             {v['delta_brier']:+}  ({v['rel_gain']:+.1%} relative)",
        f"  adoption bar       {r['min_rel_gain']:.0%} relative + selected beats baseline on tune",
        f"  → {v['verdict']}",
    ]
    return "\n".join(lines)


def render_pair(r: dict) -> str:
    t, v = r["tune"], r["validate"]
    lines = [
        f"tune/validate protocol — COW pair covariates on {r['suite']} (split at {r['split']})",
        "",
        f"TUNE ({t['n']:,} pair-years, ≤{r['split']}): baseline {t['baseline_brier']}",
        "  candidates (Brier, lower=better):",
    ]
    for name, b in sorted(t["scheme_brier"].items(), key=lambda kv: kv[1]):
        mark = " ← selected" if name == t["selected"] else ""
        lines.append(f"    {name:<14} {b}  ({r['flag_sizes'][name]:,} flagged pair-years){mark}")
    lines += [
        f"  candidates beating baseline on tune: {t['candidates_beating_baseline']}",
        "",
        f"VALIDATE ({v['n']:,} pair-years, >{r['split']}) — read once:",
        f"  baseline           {v['baseline_brier']}",
        f"  selected           {v['selected_brier']}",
        f"  ΔBrier             {v['delta_brier']:+}  ({v['rel_gain']:+.1%} relative)",
        f"  adoption bar       {r['min_rel_gain']:.0%} relative + selected beats baseline on tune",
        f"  → {v['verdict']}",
    ]
    return "\n".join(lines)


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
