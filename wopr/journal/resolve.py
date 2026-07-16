"""Auto-resolution: grade open questions against the UCDP event record.

Counts matching events from the annual GED (authoritative through
``annual_coverage_end``) plus deduplicated candidate files (preliminary,
strictly after that). Rules:

  yes  the cumulative measure crossed the threshold inside the window;
       decided_on = the crossing date (early resolution is fine — the
       outcome is already determined)
  no   the window has fully ended within available data coverage
  …    otherwise the question stays open pending data

A resolution is *provisional* when it leans on candidate data (its deciding
date lies past the annual cutoff). Re-running ``wopr resolve`` after the next
annual release re-grades provisional questions: normally they just finalize,
but candidate-era revisions can flip one — that gets a note, and the score
moves. Candidate events whose dyad/actor identities are UCDP ``XXX``
placeholders cannot match id-scoped questions; they are counted and reported
as excluded so you can see when a question was decided on incomplete
attribution.
"""

import csv
import datetime

import yaml

from wopr.paths import DATA, SOURCES
from wopr.pipeline.build import VIOLENCE, is_placeholder, load_candidates, parse_date, to_gw

csv.field_size_limit(10_000_000)

TYPE_CODES = {v: k for k, v in VIOLENCE.items()}  # sb -> "1", …


def load_meta() -> dict:
    meta_path = DATA / "meta.yaml"
    if not meta_path.exists():
        raise SystemExit("data/meta.yaml missing — run `wopr build` first")
    meta = yaml.safe_load(meta_path.read_text())
    meta["annual_end"] = datetime.date.fromisoformat(meta["annual_coverage_end"])
    meta["through"] = datetime.date.fromisoformat(meta["data_through"])
    return meta


def match(row: dict, criteria: dict, year: int) -> bool:
    """Does a GED event row fall inside the question's scope and types?"""
    if row["type_of_violence"] not in {TYPE_CODES[t] for t in criteria["types"]}:
        return False
    scope = criteria["scope"]
    sid = scope["id"]
    kind = scope["kind"]
    if kind == "country":
        return to_gw(int(row["country_id"]), year) == sid
    if is_placeholder(row):
        return False  # unattributable to any dyad/conflict/actor id
    if kind == "dyad":
        return int(row["dyad_new_id"]) == sid
    if kind == "conflict":
        return int(row["conflict_new_id"]) == sid
    if kind == "actor":
        return sid in (int(row["side_a_new_id"]), int(row["side_b_new_id"]))
    raise ValueError(f"unknown scope kind {kind}")


def accumulate(counted: list[tuple], threshold: int) -> dict:
    """Given matched (date, value, provisional) tuples, total up and find the
    threshold-crossing date."""
    counted.sort(key=lambda t: t[0])
    total = 0
    cross = None
    used_provisional = False
    for date, value, prov in counted:
        total += value
        if prov:
            used_provisional = True
        if cross is None and total >= threshold:
            cross = date
    return {
        "total": total,
        "events": len(counted),
        "cross_date": cross,
        "used_provisional": used_provisional,
    }


def evaluate(criteria: dict, meta: dict) -> dict:
    """Count matching events in the window across annual + candidate data."""
    ged = SOURCES / "ucdp-ged.csv"
    if not ged.exists():
        raise SystemExit("sources/ missing — run `wopr pull` first")
    w = criteria["window"]
    start = datetime.date.fromisoformat(str(w["start"]))
    end = datetime.date.fromisoformat(str(w["end"]))
    counted, excluded = [], 0
    value_of = (lambda r: int(r["best"] or 0)) if criteria["measure"] == "deaths" else (lambda r: 1)

    def consider(row: dict, provisional: bool) -> None:
        nonlocal excluded
        date = row.get("_date") or parse_date(row["date_start"])
        if date is None or not (start <= date <= end):
            return
        if criteria["scope"]["kind"] != "country" and provisional and is_placeholder(row):
            excluded += 1
            return
        if match(row, criteria, date.year):
            counted.append((date, value_of(row), provisional))

    if start <= meta["annual_end"]:
        with open(ged, newline="", encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                consider(row, provisional=False)
    if end > meta["annual_end"]:
        for row in load_candidates(meta["annual_end"])["events"]:
            consider(row, provisional=True)

    result = accumulate(counted, criteria["threshold"])
    result["excluded_unattributed"] = excluded
    result["window"] = (start, end)
    return result


def decide(evaluation: dict, meta: dict) -> dict | None:
    """Resolution block, or None while the question must stay open."""
    start, end = evaluation["window"]
    if evaluation["cross_date"]:
        decided_on = evaluation["cross_date"]
        outcome = "yes"
    elif end <= meta["through"]:
        decided_on = end
        outcome = "no"
    else:
        return None
    return {
        "outcome": outcome,
        "decided_on": str(decided_on),
        "resolved": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "method": "auto",
        "provisional": decided_on > meta["annual_end"],
        "basis": {
            "release": meta["ucdp_release"],
            "data_through": str(meta["through"]),
            "total": evaluation["total"],
            "events": evaluation["events"],
            "excluded_unattributed": evaluation["excluded_unattributed"],
        },
    }


def run(questions: list[dict], dry_run: bool = False) -> list[tuple[dict, dict | None, str]]:
    """Resolve due questions and re-grade provisional ones. Returns
    (question, resolution|None, action) triples; caller saves."""
    meta = load_meta()
    out = []
    for q in questions:
        auto = (q.get("resolution_policy") or {}).get("method") == "auto"
        if not auto:
            continue
        if q["status"] == "open":
            res = decide(evaluate(q["criteria"], meta), meta)
            if res is None:
                out.append((q, None, "pending"))
                continue
            if not dry_run:
                q["status"] = "resolved"
                q["resolution"] = res
            out.append((q, res, "resolved"))
        elif q["status"] == "resolved" and (q.get("resolution") or {}).get("provisional"):
            old = q["resolution"]
            if datetime.date.fromisoformat(str(old["decided_on"])) > meta["annual_end"]:
                out.append((q, old, "still-provisional"))
                continue
            res = decide(evaluate(q["criteria"], meta), meta)
            if res is None:  # coverage regressed; leave as-is
                out.append((q, old, "still-provisional"))
                continue
            if res["outcome"] != old["outcome"]:
                res["note"] = (
                    f"flipped from provisional {old['outcome']} "
                    f"(decided {old['decided_on']}) on annual release {meta['ucdp_release']}"
                )
                action = "flipped"
            else:
                action = "confirmed"
            if not dry_run:
                q["resolution"] = res
            out.append((q, res, action))
    return out
