"""Scoring: Brier, log score, calibration curve, and you-versus-the-prior.

The headline table almost nobody else computes: on the same resolved
questions, did your adjusted forecasts beat the naive base-rate prior the
engine handed you? A negative Brier delta means your inside view added
information; a positive one means you added noise.

Anti-gaming rule: the scored forecast is the last one made on or before the
question's ``decided_on`` date (the day the threshold was crossed, or the
window's end) — forecasts logged after the outcome was effectively knowable
never count.
"""

import datetime
import math


def brier(p: float, outcome: int) -> float:
    return (p - outcome) ** 2


def log_score(p: float, outcome: int) -> float:
    return math.log(p if outcome else 1.0 - p)


def scored_forecast(q: dict) -> dict | None:
    """Last forecast made on or before decided_on (see module docstring)."""
    cutoff = str((q.get("resolution") or {}).get("decided_on", "9999-12-31"))
    eligible = [f for f in q.get("forecasts", []) if str(f["t"])[:10] <= cutoff]
    return eligible[-1] if eligible else None


def question_rows(questions: list[dict]) -> list[dict]:
    rows = []
    for q in questions:
        if q.get("status") != "resolved":
            continue
        outcome = 1 if q["resolution"]["outcome"] == "yes" else 0
        cutoff = str(q["resolution"].get("decided_on", "9999-12-31"))
        prior = (q.get("prior") or {}).get("p")
        if prior is not None and str((q["prior"].get("computed") or ""))[:10] > cutoff:
            prior = None  # prior computed after the outcome was knowable: same rule as forecasts
        fc = scored_forecast(q)
        rows.append(
            {
                "id": q["id"],
                "title": q["title"],
                "outcome": outcome,
                "provisional": bool(q["resolution"].get("provisional")),
                "prior_p": prior,
                "user_p": fc["p"] if fc else None,
                "brier_prior": brier(prior, outcome) if prior is not None else None,
                "brier_user": brier(fc["p"], outcome) if fc else None,
                "log_prior": log_score(prior, outcome) if prior is not None else None,
                "log_user": log_score(fc["p"], outcome) if fc else None,
            }
        )
    return rows


def aggregate(rows: list[dict]) -> dict:
    paired = [r for r in rows if r["user_p"] is not None and r["prior_p"] is not None]
    out = {
        "resolved": len(rows),
        "paired": len(paired),
        "generated": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    if rows:
        withprior = [r for r in rows if r["prior_p"] is not None]
        if withprior:
            out["prior"] = {
                "n": len(withprior),
                "brier": round(sum(r["brier_prior"] for r in withprior) / len(withprior), 4),
                "log": round(sum(r["log_prior"] for r in withprior) / len(withprior), 4),
            }
    if paired:
        bu = sum(r["brier_user"] for r in paired) / len(paired)
        bp = sum(r["brier_prior"] for r in paired) / len(paired)
        out["you"] = {
            "n": len(paired),
            "brier": round(bu, 4),
            "log": round(sum(r["log_user"] for r in paired) / len(paired), 4),
        }
        out["you_vs_prior"] = {
            "brier_delta": round(bu - bp, 4),  # negative = you beat the base rate
            "prior_brier_on_paired": round(bp, 4),
            "you_better_on": sum(1 for r in paired if r["brier_user"] < r["brier_prior"]),
            "prior_better_on": sum(1 for r in paired if r["brier_user"] > r["brier_prior"]),
        }
    return out


def calibration(rows: list[dict], key: str = "user_p") -> list[dict]:
    bins = []
    for i in range(10):
        lo, hi = i / 10, (i + 1) / 10
        got = [r for r in rows if r[key] is not None and (lo <= r[key] < hi or (i == 9 and r[key] == 1.0))]
        if not got:
            continue
        bins.append(
            {
                "bin": f"{int(lo * 100)}–{int(hi * 100)}%",
                "n": len(got),
                "mean_p": round(sum(r[key] for r in got) / len(got), 3),
                "observed": round(sum(r["outcome"] for r in got) / len(got), 3),
            }
        )
    return bins


def render(rows: list[dict], agg: dict) -> str:
    lines = []
    if not rows:
        return "no resolved questions yet — nothing to score"
    lines.append(f"{'id':<10} {'out':<4} {'prior':>6} {'you':>6} {'B(prior)':>9} {'B(you)':>8}  title")
    for r in rows:
        lines.append(
            f"{r['id']:<10} {'YES' if r['outcome'] else 'no':<4} "
            f"{r['prior_p'] if r['prior_p'] is not None else '—':>6} "
            f"{r['user_p'] if r['user_p'] is not None else '—':>6} "
            f"{round(r['brier_prior'], 3) if r['brier_prior'] is not None else '—':>9} "
            f"{round(r['brier_user'], 3) if r['brier_user'] is not None else '—':>8}  "
            f"{r['title'][:44]}{' *' if r['provisional'] else ''}"
        )
    lines.append("")
    if "prior" in agg:
        lines.append(f"base rate alone : Brier {agg['prior']['brier']}  log {agg['prior']['log']}  (n={agg['prior']['n']})")
    if "you" in agg:
        lines.append(f"you             : Brier {agg['you']['brier']}  log {agg['you']['log']}  (n={agg['you']['n']})")
    if "you_vs_prior" in agg:
        v = agg["you_vs_prior"]
        verdict = "you BEAT the base rate" if v["brier_delta"] < 0 else "the base rate beat you"
        lines.append(
            f"you vs prior    : ΔBrier {v['brier_delta']:+} on {agg['paired']} paired questions "
            f"({v['you_better_on']} you / {v['prior_better_on']} prior) — {verdict}"
        )
    cal = calibration(rows)
    if cal:
        lines.append("")
        lines.append("calibration (your forecasts):")
        lines.append(f"  {'bin':<9} {'n':>4} {'mean p':>7} {'observed':>9}")
        for b in cal:
            lines.append(f"  {b['bin']:<9} {b['n']:>4} {b['mean_p']:>7} {b['observed']:>9}")
    if any(r["provisional"] for r in rows):
        lines.append("")
        lines.append("* provisional resolution (candidate data; confirmed at the next annual release)")
    return "\n".join(lines)
