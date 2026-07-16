"""Walk-forward backtest: is the base-rate engine itself calibrated?

Walk each year Y through the substrate. For every unit whose outcome at Y is
observable, compute the engine's headline prior using ONLY years before Y
(recency buckets already look strictly backward; class counts accumulate
cumulatively as the walk advances), then score it against the outcome at Y.
Thousands of pseudo-forecasts later you get the engine's own reliability
curve — the thing to check before treating its priors as the baseline your
inside view must beat.

Mirrors the live engine's rules exactly (same EB shrinkage, headline pick,
Jeffreys floor); tests assert parity with rate() at the final year. Skill is
reported against a climatology baseline that predicts the running global
unconditional rate — beating it is the minimum bar for "conditioning helps".

Run: wopr backtest [--burn-in 5] — writes data/backtest.yaml.
"""

from collections import defaultdict

from wopr.engine.baserate import (
    BUCKETS,
    MIN_CLASS_YEARS,
    Spec,
    bucket_of,
    eb_strength,
    hit,
    load_substrate,
)
from wopr.journal.score import brier, log_score

SUITE = (
    ("country", "deaths", ("sb",), 25),
    ("country", "deaths", ("sb", "ns", "os"), 100),
    ("country", "acd-active", (), 25),
    ("dyad", "acd-active", (), 25),
    ("pair", "acd-active", (), 25),
)


def walk(grain: str, measure: str, types: tuple, threshold: int, substrate: dict, burn_in: int = 5) -> list[dict]:
    """Score every observable unit-year, walking forward. Returns records
    {year, unit, bucket, level, p, outcome}."""
    spec = Spec(grain, 0, measure, types, threshold).normalized(substrate["last_year"])
    lo, hi = spec.period
    units = list(substrate[grain].values())
    # class membership dedupes by region signature: units with the same region
    # set share exactly the same class, so counts and EB strength are computed
    # once per (signature, bucket, year) instead of per unit — identical math,
    # required for the ~4.5k-unit pair grain
    sig_of = {u.id: tuple(sorted(set(u.region))) or ("__all__",) for u in units}
    members_by_sig = {
        sig: (units if sig == ("__all__",) else [m for m in units if set(m.region) & set(sig)])
        for sig in set(sig_of.values())
    }
    members_by_sig[("__global__",)] = units
    # precompute observables (both look only backward / at Y itself)
    nbr = substrate.get("nbr_active") if grain == "country" else None
    hits: dict[int, dict[int, bool]] = {}
    buckets: dict[int, dict[int, str]] = {}
    for u in units:
        hu, bu = {}, {}
        for y in range(lo + 1, hi + 1):
            h = hit(u, y, spec)
            if h is None:
                continue
            b = bucket_of(u, y, spec, nbr)
            if b is None:
                continue
            hu[y], bu[y] = h, b
        hits[u.id], buckets[u.id] = hu, bu

    uk: dict[int, dict[str, int]] = defaultdict(lambda: defaultdict(int))  # unit -> bucket -> hits
    un: dict[int, dict[str, int]] = defaultdict(lambda: defaultdict(int))  # unit -> bucket -> years
    guk = gun = 0  # global unconditional running counts
    records = []
    for y in range(lo + 1, hi + 1):
        cache: dict[tuple, tuple] = {}  # (sig, bucket) -> (K, N, M)

        def stats(sig: tuple, b: str) -> tuple:
            key = (sig, b)
            if key not in cache:
                counts = [(uk[m.id][b], un[m.id][b]) for m in members_by_sig[sig]]
                K = sum(k for k, _ in counts)
                N = sum(n for _, n in counts)
                cache[key] = (K, N, eb_strength(counts) if N else 0.0)
            return cache[key]

        if y - lo > burn_in:
            for u in units:
                if y not in hits[u.id]:
                    continue
                b = buckets[u.id][y]
                posteriors = {}
                for level, sig in (("region", sig_of[u.id]), ("global", ("__global__",))):
                    K, N, M = stats(sig, b)
                    if not N:
                        continue
                    posteriors[level] = ((uk[u.id][b] + M * (K / N)) / (un[u.id][b] + M), N)
                if posteriors:
                    use = "region" if posteriors.get("region") and posteriors["region"][1] >= MIN_CLASS_YEARS else "global"
                    if use not in posteriors:
                        use = next(iter(posteriors))
                    p, n_level = posteriors[use]
                else:
                    use = "global-unconditional"
                    p, n_level = (guk / gun if gun else 0.0), max(gun, 1)
                floor = 0.5 / (n_level + 1)
                p = min(max(p, floor), 1 - floor)
                records.append(
                    {
                        "year": y,
                        "unit": u.id,
                        "bucket": b,
                        "level": use,
                        "p": p,
                        "climatology": min(max(guk / gun if gun else 0.5, floor), 1 - floor),
                        "outcome": int(hits[u.id][y]),
                    }
                )
        for u in units:  # fold year Y into the cumulative counts
            if y in hits[u.id]:
                b = buckets[u.id][y]
                un[u.id][b] += 1
                uk[u.id][b] += int(hits[u.id][y])
                gun += 1
                guk += int(hits[u.id][y])
    return records


def summarize(records: list[dict]) -> dict:
    n = len(records)
    if not n:
        return {"n": 0}
    be = sum(brier(r["p"], r["outcome"]) for r in records) / n
    bc = sum(brier(r["climatology"], r["outcome"]) for r in records) / n
    out = {
        "n": n,
        "base_rate": round(sum(r["outcome"] for r in records) / n, 4),
        "brier_engine": round(be, 4),
        "brier_climatology": round(bc, 4),
        "skill_vs_climatology": round(1 - be / bc, 4) if bc else None,
        "log_engine": round(sum(log_score(r["p"], r["outcome"]) for r in records) / n, 4),
        "calibration": [],
        "by_bucket": {},
    }
    for i in range(10):
        lo_, hi_ = i / 10, (i + 1) / 10
        got = [r for r in records if lo_ <= r["p"] < hi_ or (i == 9 and r["p"] == 1.0)]
        if got:
            out["calibration"].append(
                {
                    "bin": f"{int(lo_ * 100)}–{int(hi_ * 100)}%",
                    "n": len(got),
                    "mean_p": round(sum(r["p"] for r in got) / len(got), 3),
                    "observed": round(sum(r["outcome"] for r in got) / len(got), 3),
                }
            )
    for b in BUCKETS:
        got = [r for r in records if r["bucket"] == b]
        if got:
            out["by_bucket"][b] = {
                "n": len(got),
                "mean_p": round(sum(r["p"] for r in got) / len(got), 3),
                "observed": round(sum(r["outcome"] for r in got) / len(got), 3),
                "brier": round(sum(brier(r["p"], r["outcome"]) for r in got) / len(got), 4),
            }
    return out


def render(name: str, s: dict) -> str:
    if not s.get("n"):
        return f"{name}: no scoreable unit-years"
    lines = [
        f"{name}: n={s['n']:,}  base rate {s['base_rate']}  "
        f"Brier {s['brier_engine']} vs climatology {s['brier_climatology']}  "
        f"skill {s['skill_vs_climatology']:+.1%}",
        f"  {'bin':<9} {'n':>6} {'mean p':>7} {'observed':>9}     {'bucket':<8} {'n':>6} {'mean p':>7} {'observed':>9}",
    ]
    cal = s["calibration"]
    buckets = list(s["by_bucket"].items())
    for i in range(max(len(cal), len(buckets))):
        left = (
            f"  {cal[i]['bin']:<9} {cal[i]['n']:>6} {cal[i]['mean_p']:>7} {cal[i]['observed']:>9}"
            if i < len(cal)
            else " " * 35
        )
        right = ""
        if i < len(buckets):
            b, v = buckets[i]
            right = f"     {b:<8} {v['n']:>6} {v['mean_p']:>7} {v['observed']:>9}"
        lines.append(left + right)
    return "\n".join(lines)


def run(burn_in: int = 5) -> dict:
    substrate = load_substrate()
    report = {}
    for grain, measure, types, threshold in SUITE:
        name = f"{grain}/{measure}" + (f"/{'+'.join(types)}≥{threshold}" if measure == "deaths" else "")
        records = walk(grain, measure, types, threshold, substrate, burn_in=burn_in)
        report[name] = summarize(records)
        print(render(name, report[name]))
        print()
    return report
