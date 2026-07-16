"""Validation gate: is the built data internally consistent, and is every
journal entry well-formed? Run via `wopr verify` or `make verify` (which adds
the unit tests). Exits nonzero on hard failures; cross-checks that depend on
absent sources/ are skipped so the gate still works on a fresh clone.
"""

import csv
import sys
from collections import defaultdict

import yaml

from wopr.journal import store
from wopr.paths import DATA, REGISTRY, SOURCES, TABLES

REGIONS = {"Africa", "Americas", "Asia", "Europe", "Middle East"}
failures = []


def check(ok: bool, label: str, detail: str = "") -> None:
    mark = "✓" if ok else "✗"
    print(f"{mark} {label}" + (f" — {detail}" if detail and not ok else ""))
    if not ok:
        failures.append(label)


def note(label: str) -> None:
    print(f"• {label}")


def rows_of(name: str) -> list[dict]:
    with open(TABLES / name, newline="") as f:
        return list(csv.DictReader(f))


def main() -> None:
    if not (DATA / "meta.yaml").exists():
        raise SystemExit("data/meta.yaml missing — run `wopr build` first")
    meta = yaml.safe_load((DATA / "meta.yaml").read_text())

    manifest_path = SOURCES / "manifest.yaml"
    if manifest_path.exists():
        manifest = yaml.safe_load(manifest_path.read_text())
        check(
            manifest["ucdp_release"] == meta["ucdp_release"],
            "meta release matches downloaded sources",
            f"meta {meta['ucdp_release']} vs sources {manifest['ucdp_release']} — rebuild",
        )
    else:
        note("sources/ absent — skipping source-dependent checks (fine on a fresh clone)")

    states = yaml.safe_load((REGISTRY / "states.yaml").read_text())
    check(len({s["gwno"] for s in states}) == len(states), "state gwnos unique")
    check(all(s["region"] in REGIONS for s in states), "state regions canonical")
    check(
        all(sp["to"] is None or sp["to"] >= sp["from"] for s in states for sp in s["system"]),
        "state system spells ordered",
    )

    conflicts = yaml.safe_load((REGISTRY / "conflicts.yaml").read_text())
    dyads = yaml.safe_load((REGISTRY / "dyads.yaml").read_text())
    cids = {c["id"] for c in conflicts}
    check(len(cids) == len(conflicts), "conflict ids unique")
    acd_dyads = [d for d in dyads if d["acd"]]
    check(all(d["conflict"] in cids for d in acd_dyads), "ACD dyads reference known conflicts")
    check(
        all(d["active_years"] == sorted(d["active_years"]) for d in dyads),
        "dyad active_years sorted",
    )

    cy = rows_of("country-year.csv")
    keys = {(r["gwno"], r["year"]) for r in cy}
    check(len(keys) == len(cy), "country-year key unique")
    main_recent = [r for r in cy if r["main_system"] == "1" and int(r["year"]) >= 1989]
    check(
        all(r["sb_deaths"] != "" for r in main_recent),
        "country-year has death counts for all main-system years since 1989",
    )
    check(
        all(int(r[c] or 0) >= 0 for r in cy for c in ("sb_deaths", "ns_deaths", "os_deaths")),
        "country-year death counts non-negative",
    )

    dy = rows_of("dyad-year.csv")
    check(len({(r["dyad_id"], r["year"]) for r in dy}) == len(dy), "dyad-year key unique")

    cm = rows_of("country-month.csv")
    check(all(1 <= int(r["month"]) <= 12 for r in cm), "country-month months in range")
    cand_months = set(meta.get("candidate_months", []))
    prov = {f"{int(r['year']):04d}-{int(r['month']):02d}" for r in cm if r["provisional"] == "1"}
    check(prov <= cand_months, "provisional rows only in candidate months", f"stray: {sorted(prov - cand_months)[:4]}")

    # cross-check: GED-derived monthly sums vs the official country-year table
    monthly = defaultdict(int)
    for r in cm:
        if r["provisional"] == "0":
            monthly[(r["gwno"], r["year"])] += int(r["sb_deaths"])
    official = {(r["gwno"], r["year"]): int(r["sb_deaths"]) for r in main_recent}
    diffs = [
        (k, monthly.get(k, 0), v)
        for k, v in official.items()
        if monthly.get(k, 0) != v
    ]
    frac = len(diffs) / max(len(official), 1)
    check(frac < 0.02, f"GED monthly sums match official country-year sb deaths ({len(diffs)} diffs, {frac:.1%})",
          f"worst: {sorted(diffs, key=lambda d: abs(d[1]-d[2]), reverse=True)[:3]}")

    questions = store.load_all()
    errs = [e for q in questions for e in store.validate_question(q)]
    for e in errs:
        print(f"  journal: {e}")
    check(not errs, f"journal well-formed ({len(questions)} questions)")
    qids = [q["id"] for q in questions]
    check(len(set(qids)) == len(qids), "question ids unique")

    print()
    if failures:
        print(f"GATE FAILED: {len(failures)} check(s)")
        sys.exit(1)
    print("gate passed")


if __name__ == "__main__":
    main()
