"""The arena: TOCSIN vs VIEWS vs naive baselines, head-to-head, retrospectively.

Target: P(≥25 state-based deaths in country c in month m) — VIEWS's native
main_dich semantics (detected empirically, not assumed), scored against
realized UCDP monthly outcomes. For each vantage run, every model predicts
the next 12 months using only information available at the vantage:

  views        main_dich at horizon h, untransformed
  tocsin         the rolling engine, W=1, walk-forward-clamped to the vantage;
               one-step by design, so its number is constant across horizons
  persistence  the country's trailing-12-month hit rate, (k+1)/(n+2)
  climatology  the country's full-history monthly hit rate, (k+0.5)/(n+1)

Months past the last annual release are provisional (candidate outcomes) and
flagged. Results land in data/benchmark.yaml; the methods page renders them.
"""

import datetime

import yaml

from tocsin.engine import baserate, rolling
from tocsin.engine.rolling import RollingSpec, mi, ym
from tocsin.paths import DATA, ROOT
from tocsin.pipeline import views
from tocsin.pipeline.build import to_gw

VANTAGE_RUNS = (
    "fatalities002_2023_04_t01",
    "fatalities002_2023_10_t01",
    "fatalities002_2024_04_t01",
    "fatalities002_2024_10_t01",
    "fatalities002_2025_04_t01",
)
HORIZON = 12
MODELS = ("views", "tocsin", "persistence", "climatology")
# equal-weight opinion pools — zero fitted parameters, so scoring them on the
# same vantages is measurement, not tuning. The pool result is the arena's
# central lesson: combining diverse forecasters beats the best member
# (views+persist beats views), while adding a redundant one subtracts
# (tocsin duplicates persistence's recency signal at this grain).
POOLS = {
    "pool:views+persist": ("views", "persistence"),
    "pool:all-three": ("views", "tocsin", "persistence"),
}


def brier(p, o):
    return (p - o) ** 2


def collect(force_pull: bool = False) -> tuple[list[dict], dict]:
    substrate = baserate.load_substrate()
    monthly = rolling.load_monthly(substrate)
    hits = views.realized_hits(monthly, 25)
    final_end, data_end = monthly["final_end"], monthly["data_end"]
    dich = views.detect_dich(list(VANTAGE_RUNS), monthly)
    if dich["threshold"] != 25:
        raise SystemExit(f"main_dich no longer reads as P(≥25): {dich} — realign before scoring")

    records = []
    for run in VANTAGE_RUNS:
        v = views.vantage_of(run)
        months = [v + h for h in range(1, HORIZON + 1)]
        if months[-1] > data_end:
            print(f"  {run}: horizon outruns data ({ym(months[-1])} > {ym(data_end)}) — skipped")
            continue
        vrows = {}
        for r in views.fetch_run(run, force=force_pull):
            m = views.month_index(r)
            if v + 1 <= m <= v + HORIZON and r["main_dich"] is not None:
                vrows[(to_gw(int(r["gwcode"]), m // 12), m)] = float(r["main_dich"])

        # gaps=(0,): one-step frozen across the horizon — the horizon-aware
        # variant was ablated and measured worse (see docs/method.md)
        state = rolling.build_state(
            "country", substrate, monthly, types=("sb",), threshold=25, window=1,
            class_end=v, gaps=(0,),
        )
        tocsin_p, base = {}, {}
        for gwno, u in substrate["country"].items():
            if (gwno, months[0]) not in vrows and (gwno, months[-1]) not in vrows:
                continue
            # horizon-aware: one price per (country, horizon month)
            tocsin_p[gwno] = {m: rolling.assemble(state, gwno, m)["p"] for m in months}
            k = n = k12 = n12 = 0
            for m in range(rolling.START, v + 1):
                h = hits.get((gwno, m))
                if h is None:
                    continue
                n += 1
                k += h
                if m > v - 12:
                    n12 += 1
                    k12 += h
            base[gwno] = ((k + 0.5) / (n + 1) if n else 0.5, (k12 + 1) / (n12 + 2))

        for gwno in tocsin_p:
            for h, m in enumerate(months, start=1):
                p_views = vrows.get((gwno, m))
                outcome = hits.get((gwno, m))
                if p_views is None or outcome is None:
                    continue
                records.append(
                    {
                        "run": run,
                        "gwno": gwno,
                        "month": ym(m),
                        "h": h,
                        "outcome": outcome,
                        "provisional": m > final_end,
                        "views": p_views,
                        "tocsin": tocsin_p[gwno][m],
                        "climatology": round(base[gwno][0], 4),
                        "persistence": round(base[gwno][1], 4),
                    }
                )
        print(f"  {run}: {sum(1 for r in records if r['run'] == run):,} scored country-months")
    return records, dich


def summarize(records: list[dict], dich: dict) -> dict:
    n = len(records)
    for r in records:  # materialize pool probabilities per record
        for name, members in POOLS.items():
            r[name] = sum(r[m] for m in members) / len(members)
    scored = MODELS + tuple(POOLS)
    out = {
        "target": "P(>=25 state-based deaths in a country-month), UCDP best estimate",
        "dich_semantics": dich,
        "vantages": sorted({r["run"] for r in records}),
        "n": n,
        "provisional_share": round(sum(r["provisional"] for r in records) / n, 3),
        "models": {},
        "by_horizon": {},
        "head_to_head": {},
    }
    clim = sum(brier(r["climatology"], r["outcome"]) for r in records) / n
    for m in scored:
        b = sum(brier(r[m], r["outcome"]) for r in records) / n
        bins = []
        for i in range(10):
            got = [r for r in records if i / 10 <= r[m] < (i + 1) / 10 or (i == 9 and r[m] == 1)]
            if got:
                bins.append(
                    {
                        "bin": f"{i * 10}–{i * 10 + 10}%",
                        "n": len(got),
                        "mean_p": round(sum(r[m] for r in got) / len(got), 3),
                        "observed": round(sum(r["outcome"] for r in got) / len(got), 3),
                    }
                )
        out["models"][m] = {
            "brier": round(b, 5),
            "skill_vs_climatology": round(1 - b / clim, 4) if clim else None,
            "calibration": bins,
        }
    for label, lo, hi in (("h1-3", 1, 3), ("h4-6", 4, 6), ("h7-12", 7, 12)):
        got = [r for r in records if lo <= r["h"] <= hi]
        out["by_horizon"][label] = {
            m: round(sum(brier(r[m], r["outcome"]) for r in got) / len(got), 5) for m in scored
        }
    wins = sum(1 for r in records if brier(r["tocsin"], r["outcome"]) < brier(r["views"], r["outcome"]))
    ties = sum(1 for r in records if r["tocsin"] == r["views"])
    out["head_to_head"] = {
        "tocsin_better_on": wins,
        "views_better_on": n - wins - ties,
        "delta_brier_tocsin_minus_views": round(
            out["models"]["tocsin"]["brier"] - out["models"]["views"]["brier"], 5
        ),
    }
    return out


def render(s: dict) -> str:
    lines = [
        f"the arena — {s['target']}",
        f"{s['n']:,} country-months across {len(s['vantages'])} vantages · "
        f"{s['provisional_share']:.0%} provisional outcomes",
        "",
        f"{'model':<19} {'Brier':>8} {'skill':>7}    {'h1-3':>8} {'h4-6':>8} {'h7-12':>8}",
    ]
    for m in sorted(s["models"], key=lambda k: s["models"][k]["brier"]):
        e = s["models"][m]
        lines.append(
            f"{m:<19} {e['brier']:>8} {e['skill_vs_climatology']:>+6.1%}    "
            f"{s['by_horizon']['h1-3'][m]:>8} {s['by_horizon']['h4-6'][m]:>8} {s['by_horizon']['h7-12'][m]:>8}"
        )
    hh = s["head_to_head"]
    d = hh["delta_brier_tocsin_minus_views"]
    verdict = "TOCSIN ahead" if d < 0 else "VIEWS ahead" if d > 0 else "dead heat"
    lines.append("")
    lines.append(
        f"head-to-head: ΔBrier (tocsin − views) {d:+} · "
        f"tocsin better on {hh['tocsin_better_on']:,}, views on {hh['views_better_on']:,} — {verdict}"
    )
    return "\n".join(lines)


def main(force_pull: bool = False, write: bool = True) -> dict:
    print("collecting predictions…")
    records, dich = collect(force_pull=force_pull)
    summary = summarize(records, dich)
    summary["generated_from"] = {"records": len(records)}
    print()
    print(render(summary))
    if write:
        with open(DATA / "benchmark.yaml", "w") as f:
            yaml.safe_dump(summary, f, sort_keys=False, allow_unicode=True)
        print(f"\nwrote {(DATA / 'benchmark.yaml').relative_to(ROOT)}")
    views.write_manifest(list(VANTAGE_RUNS), dich)
    return summary


if __name__ == "__main__":
    main()
