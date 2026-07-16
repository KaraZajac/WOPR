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

    episode_path = TABLES / "episode.csv"
    if episode_path.exists():
        eps = rows_of("episode.csv")
        check(len({e["epid"] for e in eps}) == len(eps), "episode ids unique")
        # cross-check: UCDP-coded episode end years vs our activity-derived
        # final years (dyad active in y, inactive in y+1). Coding rules differ
        # slightly (episode gaps), so this is a warning-level agreement rate.
        dy_active = defaultdict(set)
        for r in rows_of("dyad-year.csv"):
            if r["acd_intensity"] != "0":
                dy_active[int(r["dyad_id"])].add(int(r["year"]))
        agree = disagree = 0
        for e in eps:
            if e["terminated"] != "1" or not e["end_year"]:
                continue
            end = int(e["end_year"])
            active = dy_active.get(int(e["dyad_id"]), set())
            if end in active and end + 1 not in active:
                agree += 1
            else:
                disagree += 1
        total = agree + disagree
        rate_ok = agree / total if total else 1.0
        check(rate_ok > 0.9, f"episode ends agree with activity-derived finals ({agree}/{total}, {rate_ok:.1%})")

    coup_path = TABLES / "coup.csv"
    if coup_path.exists():
        coups = rows_of("coup.csv")
        check(len({(c["gwno"], c["year"]) for c in coups}) == len(coups), "coup key unique")
        check(
            all(int(c["successes"]) <= int(c["attempts"]) for c in coups),
            "coup successes never exceed attempts",
        )
        span = sorted(int(c["year"]) for c in coups)
        check(span[0] <= 1955 and span[-1] >= 2020, f"coup coverage spans {span[0]}–{span[-1]}")

    pop_path = TABLES / "population.csv"
    if pop_path.exists():
        pops = rows_of("population.csv")
        check(all(int(p["population"]) > 0 for p in pops), "population values positive")
        recent = {int(p["gwno"]) for p in pops if int(p["year"]) == 2023}
        cy_recent = {int(r["gwno"]) for r in rows_of("country-year.csv") if r["year"] == "2023" and r["main_system"] == "1"}
        cov = len(recent & cy_recent) / max(len(cy_recent), 1)
        check(cov > 0.9, f"population covers 2023 main-system states ({cov:.0%})")

    bdh_path = TABLES / "battle-deaths-history.csv"
    if bdh_path.exists():
        bdh = rows_of("battle-deaths-history.csv")
        yrs = [int(r["year"]) for r in bdh]
        check(min(yrs) <= 1950, f"battle-deaths history reaches the pre-GED era (from {min(yrs)})")
        check(all(int(r["battle_deaths"]) >= 0 for r in bdh), "historical battle deaths non-negative")

    cov_path = TABLES / "covariates.csv"
    if cov_path.exists():
        cov = rows_of("covariates.csv")
        check(len({(c["gwno"], c["year"]) for c in cov}) == len(cov), "covariate key unique")
        young = [float(c["pop_0014"]) for c in cov if c["pop_0014"]]
        check(all(0 <= v <= 60 for v in young), "youth share in plausible range")
        excl = [float(c["excluded_share"]) for c in cov if c["excluded_share"]]
        check(all(0 <= v <= 1.01 for v in excl), "excluded share is a fraction")
        if cov and "cinc" in cov[0]:
            cinc = [(c["year"], float(c["cinc"])) for c in cov if c.get("cinc")]
            check(all(0 <= v <= 1 for _, v in cinc), "CINC values are world shares")
            latest = max(y for y, _ in cinc)
            total = sum(v for y, v in cinc if y == latest)
            check(0.9 <= total <= 1.1, f"CINC sums to ~1 across states ({latest}: {total:.3f})")

    mids_path = TABLES / "mids.csv"
    if mids_path.exists():
        mids = rows_of("mids.csv")
        check(len({(m["gwno_a"], m["gwno_b"], m["year"]) for m in mids}) == len(mids), "MID pair-year key unique")
        check(all(1 <= int(m["hostility"]) <= 5 for m in mids), "MID hostility on the 1–5 scale")
        check(all(int(m["gwno_a"]) < int(m["gwno_b"]) for m in mids), "MID pairs undirected (a < b)")
        gwnos = {int(s["gwno"]) for s in states}
        check(
            all(int(m["gwno_a"]) in gwnos and int(m["gwno_b"]) in gwnos for m in mids),
            "MID states all in the registry (COW→G-W crosswalk clean)",
        )

    al_path = TABLES / "alliances.csv"
    if al_path.exists():
        al = rows_of("alliances.csv")
        check(all(r["defense"] in ("0", "1") for r in al), "alliance defense flag boolean")
        check(len({(r["gwno_a"], r["gwno_b"], r["year"]) for r in al}) == len(al), "alliance pair-year key unique")

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
