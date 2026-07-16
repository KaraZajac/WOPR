"""Build data/ from sources/: registries and base-rate tables.

Reads the UCDP releases and the Gleditsch–Ward state list fetched by
``wopr pull`` and writes:

  data/registry/states.yaml      G–W state system, UCDP regions, system spells
  data/registry/conflicts.yaml   UCDP/PRIO state-based conflicts + active years
  data/registry/dyads.yaml       state-based dyads (ACD + sub-threshold GED-only)
  data/registry/nonstate.yaml    non-state conflict dyads
  data/registry/onesided.yaml    one-sided violence actors
  data/tables/country-year.csv   1946–2025: ACD activity + UCDP deaths by category
  data/tables/dyad-year.csv      1946–2025 state-based dyad-years (+ GED deaths 1989+)
  data/tables/country-month.csv  1989–present monthly, candidate months provisional
  data/tables/dyad-month.csv     1989–present monthly by dyad, all violence types
  data/meta.yaml                 versions, coverage bounds, row counts

Candidate GED files overlap and get corrected across monthly releases: events
are deduplicated by id (latest file version wins) and only dates past the
annual release cutoff are kept. Candidate events whose dyad/actor names carry
UCDP ``XXX`` placeholders cannot be attributed to a dyad and are excluded from
dyad-grain tables (they still count at country grain).
"""

import csv
import datetime
import re
from collections import defaultdict
from pathlib import Path

import yaml

from wopr.paths import CANDIDATE, DATA, REGISTRY, ROOT, SOURCES, TABLES

csv.field_size_limit(10_000_000)

ACD_REGIONS = {"1": "Europe", "2": "Middle East", "3": "Asia", "4": "Africa", "5": "Americas"}
# UCDP keeps 345 ("Serbia (Yugoslavia)") for Serbia after the 2006 breakup;
# the G-W system switches to 340. Map UCDP ids onto G-W at year grain.
UCDP_TO_GW = {345: (340, 2007)}
CONFLICT_TYPES = {"1": "extrasystemic", "2": "interstate", "3": "intrastate", "4": "internationalized-intrastate"}
INCOMPATIBILITY = {"1": "territory", "2": "government", "3": "both"}
VIOLENCE = {"1": "sb", "2": "ns", "3": "os"}  # state-based / non-state / one-sided
YEAR_MIN = 1946


def read_csv(path: Path) -> list[dict]:
    with open(path, newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def gwno_list(field: str) -> list[int]:
    out = []
    for tok in field.split(","):
        tok = tok.strip()
        if tok.lstrip("-").isdigit() and int(tok) > 0:
            out.append(int(tok))
    return out


def region_names(field: str) -> list[str]:
    return [ACD_REGIONS[t.strip()] for t in field.split(",") if t.strip() in ACD_REGIONS]


def gw_region(gwno: int) -> str:
    if gwno < 200:
        return "Americas"
    if gwno < 400:
        return "Europe"
    if gwno < 630:
        return "Africa"
    if gwno < 700:
        return "Middle East"
    return "Asia"


def to_gw(gwno: int, year: int) -> int:
    """Translate a UCDP country id to the G-W state for that year."""
    target = UCDP_TO_GW.get(gwno)
    if target and year >= target[1]:
        return target[0]
    return gwno


def candidate_version(name: str) -> tuple[int, ...]:
    """Sort key for candidate files; GEDEvent_v26_0_5 -> (26, 0, 5),
    consolidated GEDEvent_v26_01_26_03 -> (26, 0, 3)."""
    nums = [int(n) for n in re.findall(r"\d+", name)]
    return (nums[0], 0, nums[-1])


def parse_date(field: str) -> datetime.date | None:
    try:
        return datetime.date.fromisoformat(field[:10])
    except ValueError:
        return None


def is_placeholder(row: dict) -> bool:
    """UCDP marks to-be-created actors/dyads with XXX tokens in candidate data."""
    return any("XXX" in row[k] for k in ("dyad_name", "side_a", "side_b", "conflict_name"))


# ---------------------------------------------------------------- states


def load_states(cy_rows: list[dict]) -> list[dict]:
    region = {int(r["country_id"]): r["region"] for r in cy_rows}
    name = {int(r["country_id"]): r["country"] for r in cy_rows}
    states: dict[int, dict] = {}
    for fn, micro in (("gw-iisystem.dat", False), ("gw-microstates.dat", True)):
        text = (SOURCES / fn).read_text(encoding="latin-1")
        ends = []
        rows = []
        for line in text.splitlines():
            parts = [p.strip() for p in line.strip().split("\t")]
            if len(parts) != 5:
                continue
            gwno, abbrev, gw_name = int(parts[0]), parts[1], parts[2]
            start = int(parts[3][-4:])
            end = int(parts[4][-4:])
            rows.append((gwno, abbrev, gw_name, start, end))
            ends.append(end)
        sentinel = max(ends)  # the list's last revision year marks ongoing members
        for gwno, abbrev, gw_name, start, end in rows:
            st = states.setdefault(
                gwno,
                {
                    "gwno": gwno,
                    "abbrev": abbrev,
                    "name": name.get(gwno, gw_name),
                    "region": region.get(gwno, gw_region(gwno)),
                    "microstate": micro,
                    "system": [],
                },
            )
            st["system"].append({"from": start, "to": None if end == sentinel else end})
    for st in states.values():
        st["system"].sort(key=lambda s: s["from"])
    # at year grain a successor state starts the year after its predecessor's
    # last (e.g. Serbia 340 takes over from Yugoslavia 345 in 2007)
    for gw, y0 in UCDP_TO_GW.values():
        for spell in states[gw]["system"]:
            if spell["from"] == y0 - 1:
                spell["from"] = y0
    return [states[k] for k in sorted(states)]


def system_years(state: dict, last_year: int) -> set[int]:
    years: set[int] = set()
    for spell in state["system"]:
        years.update(range(max(spell["from"], YEAR_MIN), (spell["to"] or last_year) + 1))
    return years


# ---------------------------------------------------------------- registries


def build_conflicts(acd_rows: list[dict], ged_names: dict[int, str]) -> list[dict]:
    conflicts: dict[int, dict] = {}
    for r in acd_rows:
        cid = int(r["conflict_id"])
        c = conflicts.setdefault(
            cid,
            {
                "id": cid,
                "name": ged_names.get(cid, ""),
                "type": CONFLICT_TYPES[r["type_of_conflict"]],
                "incompatibility": INCOMPATIBILITY[r["incompatibility"]],
                "region": region_names(r["region"]),
                "countries": [],
                "active_years": [],
            },
        )
        c["active_years"].append(int(r["year"]))
        c["type"] = CONFLICT_TYPES[r["type_of_conflict"]]  # latest year's coding wins
        for g in gwno_list(r["gwno_loc"]):
            if g not in c["countries"]:
                c["countries"].append(g)
        if not c["name"]:
            territory = r["territory_name"].strip()
            c["name"] = f"{r['location']}: {territory or 'Government'}"
    for c in conflicts.values():
        c["active_years"].sort()
        c["countries"].sort()
    return [conflicts[k] for k in sorted(conflicts)]


def build_dyads(dyadic_rows: list[dict], ged_dyad_years: dict, ged_dyad_info: dict) -> list[dict]:
    dyads: dict[int, dict] = {}
    for r in dyadic_rows:
        did = int(r["dyad_id"])
        d = dyads.setdefault(
            did,
            {
                "id": did,
                "conflict": int(r["conflict_id"]),
                "name": f"{r['side_a']} - {r['side_b']}",
                "side_a": r["side_a"],
                "side_a_id": gwno_list(r["side_a_id"]),
                "side_b": r["side_b"],
                "side_b_id": gwno_list(r["side_b_id"]),
                "type": CONFLICT_TYPES[r["type_of_conflict"]],
                "region": region_names(r["region"]),
                "acd": True,
                "active_years": [],
            },
        )
        d["active_years"].append(int(r["year"]))
    for (did, _year), _ in sorted(ged_dyad_years.items()):
        if did in dyads or did not in ged_dyad_info:
            continue
        info = ged_dyad_info[did]
        dyads[did] = {
            "id": did,
            "conflict": info["conflict"],
            "name": info["name"],
            "side_a": info["side_a"],
            "side_a_id": [info["side_a_id"]],
            "side_b": info["side_b"],
            "side_b_id": [info["side_b_id"]],
            "type": "",
            "region": info["region"],
            "acd": False,  # never reached ACD inclusion (sub-threshold)
            "active_years": [],
        }
    for d in dyads.values():
        d["active_years"].sort()
    return [dyads[k] for k in sorted(dyads)]


def build_nonstate(rows: list[dict]) -> list[dict]:
    out: dict[int, dict] = {}
    for r in rows:
        did = int(r["dyad_id"])
        d = out.setdefault(
            did,
            {
                "id": did,
                "conflict": int(r["conflict_id"]),
                "name": f"{r['side_a_name']} - {r['side_b_name']}",
                "side_a": r["side_a_name"],
                "side_a_id": gwno_list(r["side_a_id"]),
                "side_b": r["side_b_name"],
                "side_b_id": gwno_list(r["side_b_id"]),
                "organization_level": int(r["org"]),
                "region": region_names(r["region"]),
                "countries": [],
                "active_years": [],
            },
        )
        d["active_years"].append(int(r["year"]))
        for g in gwno_list(r["gwno_location"]):
            g = to_gw(g, int(r["year"]))
            if g not in d["countries"]:
                d["countries"].append(g)
    for d in out.values():
        d["active_years"].sort()
        d["countries"].sort()
    return [out[k] for k in sorted(out)]


def build_onesided(rows: list[dict]) -> list[dict]:
    out: dict[int, dict] = {}
    for r in rows:
        aid = int(r["actor_id"])
        a = out.setdefault(
            aid,
            {
                "id": aid,
                "name": r["actor_name"],
                "government": r["is_government_actor"].strip().lower() in ("1", "true", "yes"),
                "region": region_names(r["region"]),
                "countries": [],
                "active_years": [],
            },
        )
        a["active_years"].append(int(r["year"]))
        for g in gwno_list(r["gwno_location"]):
            g = to_gw(g, int(r["year"]))
            if g not in a["countries"]:
                a["countries"].append(g)
    for a in out.values():
        a["active_years"].sort()
        a["countries"].sort()
    return [out[k] for k in sorted(out)]


# ---------------------------------------------------------------- GED passes


def scan_ged() -> dict:
    """One streaming pass over annual GED: monthly aggregates + dyad info/names."""
    country_month: dict[tuple, dict] = defaultdict(lambda: defaultdict(int))
    dyad_month: dict[tuple, dict] = defaultdict(lambda: defaultdict(int))
    dyad_year: dict[tuple, dict] = defaultdict(lambda: defaultdict(int))
    dyad_info: dict[int, dict] = {}
    conflict_names: dict[int, str] = {}
    max_date = datetime.date(1900, 1, 1)
    n_events = 0
    bad_dates = 0
    with open(SOURCES / "ucdp-ged.csv", newline="", encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            n_events += 1
            date = parse_date(r["date_start"])
            if date is None:
                bad_dates += 1
                continue
            max_date = max(max_date, date)
            vt = VIOLENCE[r["type_of_violence"]]
            gwno = to_gw(int(r["country_id"]), date.year)
            did = int(r["dyad_new_id"])
            best = int(r["best"] or 0)
            cm = country_month[(gwno, date.year, date.month)]
            cm[f"{vt}_events"] += 1
            cm[f"{vt}_deaths"] += best
            dm = dyad_month[(did, date.year, date.month)]
            dm["events"] += 1
            dm["deaths"] += best
            if r["type_of_violence"] == "1":
                dy = dyad_year[(did, date.year)]
                dy["events"] += 1
                dy["deaths"] += best
            cid = int(r["conflict_new_id"])
            conflict_names.setdefault(cid, r["conflict_name"])
            if did not in dyad_info:
                dyad_info[did] = {
                    "conflict": cid,
                    "name": r["dyad_name"],
                    "side_a": r["side_a"],
                    "side_a_id": int(r["side_a_new_id"]),
                    "side_b": r["side_b"],
                    "side_b_id": int(r["side_b_new_id"]),
                    "region": [r["region"]],
                    "type": VIOLENCE[r["type_of_violence"]],
                }
    return {
        "country_month": country_month,
        "dyad_month": dyad_month,
        "dyad_year": dyad_year,
        "dyad_info": dyad_info,
        "conflict_names": conflict_names,
        "annual_end": max_date,
        "n_events": n_events,
        "bad_dates": bad_dates,
    }


def load_candidates(annual_end: datetime.date) -> dict:
    """Merge candidate files: dedupe by id (latest file wins), keep post-annual dates."""
    files = sorted(CANDIDATE.glob("*.csv"), key=lambda p: candidate_version(p.stem))
    merged: dict[str, dict] = {}
    for path in files:
        for r in read_csv(path):
            merged[r["id"]] = r
    kept, dropped_early, placeholders = [], 0, 0
    max_date = annual_end
    for r in merged.values():
        date = parse_date(r["date_start"])
        if date is None or date <= annual_end:
            dropped_early += 1
            continue
        r["_date"] = date
        max_date = max(max_date, date)
        if is_placeholder(r):
            placeholders += 1
        kept.append(r)
    months = sorted({(r["_date"].year, r["_date"].month) for r in kept})
    return {
        "events": kept,
        "files": [p.name for p in files],
        "months": months,
        "dropped_pre_annual": dropped_early,
        "placeholders": placeholders,
        "max_date": max_date,
    }


# ---------------------------------------------------------------- tables


def write_csv(path: Path, header: list[str], rows: list[list]) -> None:
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)
    print(f"  -> {path.relative_to(ROOT)} ({len(rows):,} rows)")


def build_country_year(states, cy_rows, acd_rows, last_year: int) -> list[list]:
    cy = {(to_gw(int(r["country_id"]), int(r["year"])), int(r["year"])): r for r in cy_rows}
    active: dict[tuple, int] = {}
    for r in acd_rows:
        year = int(r["year"])
        for g in gwno_list(r["gwno_loc"]):
            key = (to_gw(g, year), year)
            active[key] = max(active.get(key, 0), int(r["intensity_level"]))
    rows = []
    for st in states:
        years = system_years(st, last_year)
        for y in sorted(years):
            key = (st["gwno"], y)
            c = cy.get(key)
            rows.append(
                [
                    st["gwno"],
                    st["name"],
                    st["region"],
                    y,
                    0 if st["microstate"] else 1,
                    active.get(key, 0),
                    c["sb_total_deaths_best"] if c else "",
                    c["ns_total_deaths_best"] if c else "",
                    c["os_total_deaths_best"] if c else "",
                ]
            )
    header = ["gwno", "country", "region", "year", "main_system", "acd_intensity", "sb_deaths", "ns_deaths", "os_deaths"]
    return [header] + rows


def build_dyad_year(dyadic_rows, ged_dyad_year, dyads) -> list[list]:
    dyad_by_id = {d["id"]: d for d in dyads}
    acd = {(int(r["dyad_id"]), int(r["year"])): int(r["intensity_level"]) for r in dyadic_rows}
    keys = sorted(set(acd) | set(ged_dyad_year))
    rows = []
    for did, y in keys:
        d = dyad_by_id.get(did, {})
        g = ged_dyad_year.get((did, y), {})
        rows.append(
            [
                did,
                d.get("conflict", ""),
                y,
                acd.get((did, y), 0),
                d.get("type", ""),
                "; ".join(d.get("region", [])),
                g.get("events", "") if g else "",
                g.get("deaths", "") if g else "",
            ]
        )
    header = ["dyad_id", "conflict_id", "year", "acd_intensity", "type", "region", "ged_events", "ged_deaths"]
    return [header] + rows


def build_month_tables(ged, cand) -> tuple[list[list], list[list]]:
    country = {k: dict(v) for k, v in ged["country_month"].items()}
    dyad = {k: dict(v) for k, v in ged["dyad_month"].items()}
    provisional_c, provisional_d = set(), set()
    dyad_types = {did: info["type"] for did, info in ged["dyad_info"].items()}
    for r in cand["events"]:
        date, vt = r["_date"], VIOLENCE[r["type_of_violence"]]
        best = int(r["best"] or 0)
        ck = (to_gw(int(r["country_id"]), date.year), date.year, date.month)
        cm = country.setdefault(ck, {})
        cm[f"{vt}_events"] = cm.get(f"{vt}_events", 0) + 1
        cm[f"{vt}_deaths"] = cm.get(f"{vt}_deaths", 0) + best
        provisional_c.add(ck)
        if not is_placeholder(r):
            did = int(r["dyad_new_id"])
            dk = (did, date.year, date.month)
            dm = dyad.setdefault(dk, {})
            dm["events"] = dm.get("events", 0) + 1
            dm["deaths"] = dm.get("deaths", 0) + best
            provisional_d.add(dk)
            dyad_types.setdefault(did, vt)
    c_header = ["gwno", "year", "month", "sb_events", "sb_deaths", "ns_events", "ns_deaths", "os_events", "os_deaths", "provisional"]
    c_rows = [
        [k[0], k[1], k[2]] + [v.get(col, 0) for col in c_header[3:9]] + [1 if k in provisional_c else 0]
        for k, v in sorted(country.items())
    ]
    d_header = ["dyad_id", "type", "year", "month", "events", "deaths", "provisional"]
    d_rows = [
        [k[0], dyad_types.get(k[0], ""), k[1], k[2], v.get("events", 0), v.get("deaths", 0), 1 if k in provisional_d else 0]
        for k, v in sorted(dyad.items())
    ]
    return [c_header] + c_rows, [d_header] + d_rows


# ---------------------------------------------------------------- main


def dump_yaml(path: Path, obj) -> None:
    with open(path, "w") as f:
        yaml.safe_dump(obj, f, sort_keys=False, allow_unicode=True, width=120)
    print(f"  -> {path.relative_to(ROOT)}")


def main() -> None:
    manifest = yaml.safe_load((SOURCES / "manifest.yaml").read_text())
    for d in (DATA, TABLES, REGISTRY):
        d.mkdir(exist_ok=True)

    print("scanning GED…")
    ged = scan_ged()
    annual_end = ged["annual_end"]
    last_year = annual_end.year
    cand = load_candidates(annual_end)
    print(
        f"  {ged['n_events']:,} annual events through {annual_end}; "
        f"{len(cand['events']):,} candidate events in {len(cand['months'])} months "
        f"({cand['placeholders']} unattributed)"
    )

    cy_rows = read_csv(SOURCES / "ucdp-cy.csv")
    acd_rows = read_csv(SOURCES / "ucdp-prio-acd.csv")
    dyadic_rows = read_csv(SOURCES / "ucdp-dyadic.csv")

    print("building registries…")
    states = load_states(cy_rows)
    conflicts = build_conflicts(acd_rows, ged["conflict_names"])
    dyads = build_dyads(dyadic_rows, ged["dyad_year"], ged["dyad_info"])
    nonstate = build_nonstate(read_csv(SOURCES / "ucdp-nonstate.csv"))
    onesided = build_onesided(read_csv(SOURCES / "ucdp-onesided.csv"))
    dump_yaml(REGISTRY / "states.yaml", states)
    dump_yaml(REGISTRY / "conflicts.yaml", conflicts)
    dump_yaml(REGISTRY / "dyads.yaml", dyads)
    dump_yaml(REGISTRY / "nonstate.yaml", nonstate)
    dump_yaml(REGISTRY / "onesided.yaml", onesided)

    print("building tables…")
    cy_table = build_country_year(states, cy_rows, acd_rows, last_year)
    dy_table = build_dyad_year(dyadic_rows, ged["dyad_year"], dyads)
    cm_table, dm_table = build_month_tables(ged, cand)
    write_csv(TABLES / "country-year.csv", cy_table[0], cy_table[1:])
    write_csv(TABLES / "dyad-year.csv", dy_table[0], dy_table[1:])
    write_csv(TABLES / "country-month.csv", cm_table[0], cm_table[1:])
    write_csv(TABLES / "dyad-month.csv", dm_table[0], dm_table[1:])

    meta = {
        "ucdp_release": manifest["ucdp_release"],
        "downloaded": manifest["downloaded"],
        "built": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "annual_coverage_end": str(annual_end),
        "data_through": str(cand["max_date"]),
        "candidate_files": cand["files"],
        "candidate_months": [f"{y:04d}-{m:02d}" for y, m in cand["months"]],
        "counts": {
            "ged_events": ged["n_events"],
            "ged_bad_dates": ged["bad_dates"],
            "candidate_events": len(cand["events"]),
            "candidate_unattributed": cand["placeholders"],
            "states": len(states),
            "conflicts": len(conflicts),
            "dyads": len(dyads),
            "nonstate_dyads": len(nonstate),
            "onesided_actors": len(onesided),
            "country_years": len(cy_table) - 1,
            "dyad_years": len(dy_table) - 1,
            "country_months": len(cm_table) - 1,
            "dyad_months": len(dm_table) - 1,
        },
    }
    dump_yaml(DATA / "meta.yaml", meta)
    print("build complete")


if __name__ == "__main__":
    main()
