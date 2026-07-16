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
import json
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


def read_csv(path: Path, encoding: str = "utf-8-sig") -> list[dict]:
    with open(path, newline="", encoding=encoding) as f:
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


# COW country codes that differ from G-W in the 1946+ window. Germany and
# Yemen apply to the post-1990 unified states only (the divided-era codes
# match); the Pacific microstates differ outright — note COW 970 is Nauru
# while G-W 970 is Kiribati, so this must be a single dict lookup, never
# chained. Serbia (COW keeps 345 after 2006, G-W moves to 340) is handled by
# the year-aware to_gw alias afterwards.
COW_TO_GW = {255: (260, 1990), 679: (678, 1990), 946: (970, 0), 947: (973, 0), 955: (972, 0), 970: (971, 0)}


def cow_to_gw(ccode: int, year: int) -> int:
    """Translate a COW country code to the G-W state for that year."""
    target = COW_TO_GW.get(ccode)
    if target and year >= target[1]:
        return to_gw(target[0], year)
    return to_gw(ccode, year)


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
    year_re = re.compile(r"\d{4}")
    for fn, micro in (("gw-states.tsv", False), ("gw-microstates.tsv", True)):
        text = (SOURCES / fn).read_text(encoding="latin-1")
        ends = []
        rows = []
        for line in text.splitlines():
            parts = [p.strip() for p in line.strip().split("\t")]
            if len(parts) != 5 or not parts[0].isdigit():  # header row / blanks
                continue
            gwno, abbrev, gw_name = int(parts[0]), parts[1], parts[2]
            start = int(year_re.search(parts[3]).group())
            end = int(year_re.search(parts[4]).group())
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
                "gwno": {"a": gwno_list(r["gwno_a"]), "b": gwno_list(r["gwno_b"])},
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
            "gwno": {"a": [], "b": []},
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
    acd = {(int(r["dyad_id"]), int(r["year"])): r for r in dyadic_rows}
    keys = sorted(set(acd) | set(ged_dyad_year))

    def side(r, col):  # secondary parties vary by year, so they live here
        return ";".join(str(x) for x in gwno_list(r[col]))

    rows = []
    for did, y in keys:
        d = dyad_by_id.get(did, {})
        g = ged_dyad_year.get((did, y), {})
        a = acd.get((did, y))
        rows.append(
            [
                did,
                d.get("conflict", ""),
                y,
                int(a["intensity_level"]) if a else 0,
                d.get("type", ""),
                "; ".join(d.get("region", [])),
                side(a, "gwno_a") if a else "",
                side(a, "gwno_b") if a else "",
                side(a, "gwno_a_2nd") if a else "",
                side(a, "gwno_b_2nd") if a else "",
                g.get("events", "") if g else "",
                g.get("deaths", "") if g else "",
            ]
        )
    header = [
        "dyad_id", "conflict_id", "year", "acd_intensity", "type", "region",
        "gwno_a", "gwno_b", "gwno_a2", "gwno_b2", "ged_events", "ged_deaths",
    ]
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


# ---------------------------------------------------------------- covariates

# World Bank country name -> states.yaml name, where they differ
WB_NAMES = {
    "United States": "United States of America",
    "Congo, Dem. Rep.": "DR Congo (Zaire)",
    "Congo, Rep.": "Congo",
    "Cote d'Ivoire": "Ivory Coast",
    "Myanmar": "Myanmar (Burma)",
    "Russian Federation": "Russia (Soviet Union)",
    "Yemen, Rep.": "Yemen (North Yemen)",
    "Vietnam": "Vietnam (North Vietnam)",
    "Cambodia": "Cambodia (Kampuchea)",
    "Zimbabwe": "Zimbabwe (Rhodesia)",
    "Eswatini": "Kingdom of eSwatini (Swaziland)",
    "Czechia": "Czech Republic",
    "Bosnia and Herzegovina": "Bosnia-Herzegovina",
    "Iran, Islamic Rep.": "Iran (Persia)",
    "Turkiye": "Turkey (Türkiye)",
    "Egypt, Arab Rep.": "Egypt",
    "Syrian Arab Republic": "Syria",
    "Kyrgyz Republic": "Kyrgyz Republic",
    "Lao PDR": "Laos",
    "Slovak Republic": "Slovakia",
    "Korea, Rep.": "South Korea",
    "Korea, Dem. People's Rep.": "North Korea",
    "Venezuela, RB": "Venezuela",
    "Gambia, The": "Gambia",
    "Sri Lanka": "Sri Lanka (Ceylon)",
    "Belarus": "Belarus (Byelorussia)",
    "Burkina Faso": "Burkina Faso (Upper Volta)",
    "Madagascar": "Madagascar (Malagasy)",
    "North Macedonia": "Macedonia, FYR",
    "Timor-Leste": "East Timor",
}

COVARIATE_COLS = ["gdp_pc", "inflation", "pop_0014", "pop_1564", "urban_pct", "infant_mort", "pop_growth", "excluded_share", "cinc"]
EPR_EXCLUDED = {"POWERLESS", "DISCRIMINATED", "SELF-EXCLUSION"}  # out of central power


def cow_cinc() -> dict:
    """(gwno, year) -> CINC composite capability index (COW NMC v7, through
    2022). The share of world material capability — six components: military
    expenditure/personnel, iron & steel, energy, total/urban population."""
    path = SOURCES / "cow" / "nmc.csv"
    if not path.exists():
        return {}
    out = {}
    for r in read_csv(path, encoding="latin-1"):
        year = int(r["year"])
        if year < YEAR_MIN or not r["cinc"] or r["cinc"] == "-9":
            continue
        out[(cow_to_gw(int(r["ccode"]), year), year)] = float(r["cinc"])
    return out


def build_mids(states) -> list[list]:
    """data/tables/mids.csv: militarized interstate disputes per undirected
    country pair-year (COW dyadic MID 4.03, 1946–2014). The sub-war friction
    record — disputes, threats, shows and uses of force — that the UCDP
    ≥25-death threshold never sees. hostility is the dyad-year max on COW's
    1–5 scale (4 = use of force, 5 = war); fatal marks any recorded deaths."""
    path = SOURCES / "cow" / "dyadic-mid.csv"
    if not path.exists():
        return [["gwno_a", "gwno_b", "year", "disputes", "hostility", "fatal"]]
    known = {s["gwno"] for s in states}
    agg: dict[tuple, dict] = {}
    dropped = set()
    for r in read_csv(path, encoding="latin-1"):
        year = int(r["year"])
        if year < YEAR_MIN:
            continue
        a, b = cow_to_gw(int(r["statea"]), year), cow_to_gw(int(r["stateb"]), year)
        if a not in known or b not in known:
            dropped.add((a, b, year))
            continue
        key = (min(a, b), max(a, b), year)
        cur = agg.setdefault(key, {"disputes": set(), "hostility": 0, "fatal": 0})
        cur["disputes"].add(r["disno"])
        if r["hihost"].isdigit():
            cur["hostility"] = max(cur["hostility"], int(r["hihost"]))
        if r["fatlev"].isdigit() and int(r["fatlev"]) > 0:
            cur["fatal"] = 1
    if dropped:
        print(f"  mids: dropped {len(dropped)} pair-years with non-registry states")
    rows = [[a, b, y, len(v["disputes"]), v["hostility"], v["fatal"]] for (a, b, y), v in sorted(agg.items())]
    return [["gwno_a", "gwno_b", "year", "disputes", "hostility", "fatal"]] + rows


def build_alliances(states) -> list[list]:
    """data/tables/alliances.csv: formal alliance membership per undirected
    country pair-year (COW v4.1, 1946–2012). defense=1 marks a defense pact
    (the strongest commitment class); row presence marks any alliance."""
    path = SOURCES / "cow" / "alliances-directed.csv"
    if not path.exists():
        return [["gwno_a", "gwno_b", "year", "defense"]]
    known = {s["gwno"] for s in states}
    agg: dict[tuple, int] = {}
    for r in read_csv(path, encoding="latin-1"):
        year = int(r["year"])
        if year < YEAR_MIN:
            continue
        a, b = cow_to_gw(int(r["ccode1"]), year), cow_to_gw(int(r["ccode2"]), year)
        if a not in known or b not in known or a == b:
            continue
        key = (min(a, b), max(a, b), year)
        agg[key] = max(agg.get(key, 0), 1 if r["defense"] == "1" else 0)
    rows = [[a, b, y, d] for (a, b, y), d in sorted(agg.items())]
    return [["gwno_a", "gwno_b", "year", "defense"]] + rows


def epr_excluded_share() -> dict:
    """(gwno, year) -> share of population in politically-excluded ethnic
    groups (EPR status POWERLESS/DISCRIMINATED/SELF-EXCLUSION)."""
    path = SOURCES / "epr-core.csv"
    if not path.exists():
        return {}
    out: dict[tuple, float] = defaultdict(float)
    for r in read_csv(path):
        if not r["size"] or r["status"] not in EPR_EXCLUDED:
            continue
        gwno, lo, hi = int(r["gwid"]), int(r["from"]), int(r["to"])
        for y in range(lo, hi + 1):
            out[(gwno, y)] += float(r["size"])
    return out


def build_covariates(states, last_year: int) -> list[list]:
    """data/tables/covariates.csv: World Bank WDI structural covariates per
    gwno-year, name-matched via the WB country list. gwno-year keyed so it
    joins the conflict spine directly."""
    wb_dir = SOURCES / "worldbank"
    if not (wb_dir / "countries.json").exists():
        return [["gwno", "year"] + COVARIATE_COLS]
    countries = json.loads((wb_dir / "countries.json").read_text())[1]
    by_name = {s["name"]: s["gwno"] for s in states}
    iso_gwno, unmatched = {}, set()
    for c in countries:
        if c["region"]["id"] == "NA":
            continue
        gwno = by_name.get(WB_NAMES.get(c["name"], c["name"]))
        if gwno is not None:
            iso_gwno[c["id"]] = gwno
        else:
            unmatched.add(c["name"])
    if unmatched:
        print(f"  covariates: {len(unmatched)} unmatched WB countries: {sorted(unmatched)[:6]}")

    cells: dict[tuple, dict] = defaultdict(dict)
    for logical in COVARIATE_COLS:
        path = wb_dir / f"{logical}.json"
        if not path.exists():
            continue
        for r in json.loads(path.read_text()):
            gwno = iso_gwno.get(r["iso3"])
            if gwno is None or r["year"] > last_year:
                continue
            cells[(to_gw(gwno, r["year"]), r["year"])][logical] = r["value"]
    for (gwno, year), share in epr_excluded_share().items():
        if year <= last_year:
            cells[(gwno, year)]["excluded_share"] = round(share, 3)
    for (gwno, year), cinc in cow_cinc().items():
        if year <= last_year:
            cells[(gwno, year)]["cinc"] = round(cinc, 5)

    rows = []
    for (gwno, year), vals in sorted(cells.items()):
        # cinc is a world share (small states ~1e-5), so it keeps more precision
        rows.append([gwno, year] + [round(vals[c], 6 if c == "cinc" else 3) if c in vals else "" for c in COVARIATE_COLS])
    return [["gwno", "year"] + COVARIATE_COLS] + rows


# ---------------------------------------------------------------- long tail

TERMINATION_OUTCOMES = {
    "1": "peace-agreement",
    "2": "ceasefire",
    "3": "government-victory",
    "4": "rebel-victory",
    "5": "low-activity",
    "6": "actor-ceases",
}


def build_episodes() -> list[list]:
    """data/tables/episode.csv from the UCDP termination dyad file: one row
    per dyad-episode with validated bounds and how it ended (Kreutz coding).
    The engine derives termination hazards from activity alone; this table is
    the outcome detail and the cross-check."""
    path = SOURCES / "ucdp-termination-dyad.csv"
    if not path.exists():
        return [["dyad_id", "epid", "start_year", "end_year", "terminated", "outcome"]]
    episodes = {}
    for r in read_csv(path):
        epid = r["d_epid"]
        if not epid:
            continue
        cur = episodes.setdefault(epid, r)
        if int(r["year"]) >= int(cur["year"]):
            episodes[epid] = r  # the episode's last coded year carries the end state
    rows = []
    for epid, r in episodes.items():
        rows.append(
            [
                int(r["dyad_id"]),
                epid,
                int(r["d_ep_startyear"]),
                int(r["d_ep_endyear"]) if r["d_ep_endyear"] else "",
                1 if r["d_epterm"] == "1" else 0,
                TERMINATION_OUTCOMES.get(r["d_outcome"], ""),
            ]
        )
    rows.sort(key=lambda x: (x[0], x[2]))
    return [["dyad_id", "epid", "start_year", "end_year", "terminated", "outcome"]] + rows


def build_peace_agreements(states) -> list[dict]:
    """data/registry/peace-agreements.yaml from the UCDP PA workbook. The PA
    dataset updates irregularly (v22.2 ends 2021), so this is browsable
    context and eventual confirmation — not a near-term resolution feed."""
    from wopr.pipeline.xlsx import xlsx_rows

    path = SOURCES / "ucdp-peace-agreements.xlsx"
    if not path.exists():
        return []
    rows = xlsx_rows(path)
    header = rows[0]
    idx = {name: i for i, name in enumerate(header)}
    out = []
    for r in rows[1:]:
        def col(name):
            i = idx.get(name)
            return r[i] if i is not None and i < len(r) else ""

        if not col("paid"):
            continue
        out.append(
            {
                "id": int(float(col("paid"))),
                "name": col("pa_name"),
                "date": col("pa_date"),
                "year": int(float(col("year"))) if col("year") else None,
                "conflicts": gwno_list(col("conflict_id")),  # agreements can span conflicts
                "dyads": gwno_list(col("dyad_id")),
                "incompatibility": col("incompatibility"),
            }
        )
    out.sort(key=lambda a: (a["year"] or 0, a["id"]))
    return out


# ---------------------------------------------------------------- coups


def build_coups(states, last_year: int) -> list[list]:
    """data/tables/coup.csv from the Powell–Thyne country-year panel:
    gwno, year, attempts, successes. P&T publish their own G-W codes
    (ccode_gw) where they diverge from COW; coup slots code 1 = failed
    attempt, 2 = successful coup."""
    path = SOURCES / "pt-coups.tsv"
    if not path.exists():
        return [["gwno", "year", "attempts", "successes"]]
    known = {s["gwno"] for s in states}
    rows = []
    unmatched = set()
    with open(path, newline="", encoding="utf-8-sig") as f:
        for r in csv.DictReader(f, delimiter="\t"):
            year = int(r["year"])
            gw = r.get("ccode_gw", "").strip()
            gwno = to_gw(int(gw) if gw else int(r["ccode"]), year)
            if gwno not in known:
                unmatched.add(f"{r['country']}({gwno})")
                continue
            slots = [r.get(f"coup{i}", "").strip() for i in (1, 2, 3, 4)]
            slots = [int(s) for s in slots if s and s != "0"]
            rows.append([gwno, year, len(slots), sum(1 for s in slots if s == 2)])
    if unmatched:
        print(f"  coups: {len(unmatched)} unmatched P&T countries: {sorted(unmatched)[:6]}")
    rows.sort()
    return [["gwno", "year", "attempts", "successes"]] + rows


# ---------------------------------------------------------------- regime

# OWID entity name -> our states.yaml name, ONLY where they truly differ
# (the registry prefers plain modern UCDP names — do not "correct" those)
OWID_NAMES = {
    "United States": "United States of America",
    "Democratic Republic of Congo": "DR Congo (Zaire)",
    "Cote d'Ivoire": "Ivory Coast",
    "Myanmar": "Myanmar (Burma)",
    "Russia": "Russia (Soviet Union)",
    "Yemen": "Yemen (North Yemen)",
    "Vietnam": "Vietnam (North Vietnam)",
    "Cambodia": "Cambodia (Kampuchea)",
    "Zimbabwe": "Zimbabwe (Rhodesia)",
    "Eswatini": "Kingdom of eSwatini (Swaziland)",
    "Czechia": "Czech Republic",
    "Bosnia and Herzegovina": "Bosnia-Herzegovina",
    "South Yemen": "Yemen (South Yemen)",
    "Yemen People's Republic": "Yemen (South Yemen)",
    "Yemen Arab Republic": "Yemen (North Yemen)",
    "East Germany": "German Democratic Republic",
    "West Germany": "Germany",
    "Madagascar": "Madagascar (Malagasy)",
    "Democratic Republic of Vietnam": "Vietnam (North Vietnam)",
    "Republic of Vietnam": "Vietnam, Republic of",
}


def build_battle_deaths_history() -> list[list]:
    """data/tables/battle-deaths-history.csv: state-based battle deaths per
    country-year 1946–2008 from PRIO Battle Deaths (best estimate, by
    location). Stitches onto GED sb deaths (1989+) to give a continuous
    1946–present series — GED is authoritative from 1989, so this table is
    the pre-GED extension only."""
    path = SOURCES / "prio-battle-deaths.csv"
    if not path.exists():
        return [["gwno", "year", "battle_deaths"]]
    totals: dict[tuple, int] = defaultdict(int)
    for r in read_csv(path):
        if not r["bdeadbes"] or not r["bdeadbes"].lstrip("-").isdigit():
            continue
        best = int(r["bdeadbes"])
        if best < 0:
            continue
        year = int(r["year"])
        locs = gwno_list(r["gwnoloc"]) or gwno_list(r["gwnoa"])
        if not locs:
            continue
        share = best // len(locs)  # split a multi-country conflict evenly
        for g in locs:
            totals[(to_gw(g, year), year)] += share
    rows = [[g, y, d] for (g, y), d in sorted(totals.items())]
    return [["gwno", "year", "battle_deaths"]] + rows


def build_population(states, last_year: int) -> list[list]:
    """data/tables/population.csv: gwno-year population from the OWID extract,
    YEAR_MIN–present, name-matched. The per-capita denominator for trends."""
    by_name = {s["name"]: s["gwno"] for s in states}
    path = SOURCES / "owid-population.csv"
    if not path.exists():
        return [["gwno", "year", "population"]]
    dedup = {}
    with open(path, newline="", encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            try:
                year = int(r["Year"])
            except ValueError:
                continue
            if year < YEAR_MIN or not r["Population"].strip():
                continue
            gwno = by_name.get(OWID_NAMES.get(r["Entity"], r["Entity"]))
            if gwno is None:
                continue
            dedup[(to_gw(gwno, year), year)] = int(float(r["Population"]))
    # OWID population lags ~2 years behind the conflict data; carry the last
    # known value forward so recent per-capita rates have a denominator
    latest = {}
    for (g, y), p in dedup.items():
        if y > latest.get(g, (0, 0))[0]:
            latest[g] = (y, p)
    for g, (y0, p) in latest.items():
        for y in range(y0 + 1, last_year + 1):
            dedup[(g, y)] = p
    return [["gwno", "year", "population"]] + [[g, y, p] for (g, y), p in sorted(dedup.items())]


def build_regime(states, last_year: int) -> list[list]:
    """data/tables/regime.csv: Regimes of the World (0–3) per gwno-year,
    1945–present, name-matched from the OWID/V-Dem extract."""
    by_name = {s["name"]: s["gwno"] for s in states}
    rows = []
    unmatched = set()
    with open(SOURCES / "owid-regime.csv", newline="", encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            year = int(r["Year"])
            if year < YEAR_MIN - 1 or not r["Political regime"].strip().isdigit():
                continue
            name = OWID_NAMES.get(r["Entity"], r["Entity"])
            gwno = by_name.get(name)
            if gwno is None:
                unmatched.add(r["Entity"])
                continue
            rows.append([to_gw(gwno, year), year, int(r["Political regime"])])
    if unmatched:
        print(f"  regime: no gwno for {len(unmatched)} OWID entities: {sorted(unmatched)[:8]}")
    rows.sort()
    dedup = {(g, y): v for g, y, v in rows}  # succession alias can collide; last wins
    return [["gwno", "year", "regime"]] + [[g, y, v] for (g, y), v in sorted(dedup.items())]


# ---------------------------------------------------------------- pair universe

P5 = (2, 200, 220, 365, 710)
PAIR_KM = 400  # proximity threshold; coverage of interstate hits printed at build
# land neighbors of states born after the distance data ends (2002)
NEW_STATE_NEIGHBORS = {
    341: [340, 344, 346, 339],            # Montenegro
    347: [339, 340, 341, 343],            # Kosovo
    626: [482, 490, 500, 501, 530, 625],  # South Sudan
    860: [850],                           # East Timor
}


def build_pair_year(states, dyadic_rows, last_year: int) -> list[list]:
    """The relevant pair universe: for every year, all country pairs that are
    proximate (Gleditsch–Ward minimum distance ≤ PAIR_KM), in the same UCDP
    region (standoff-era conflicts — Iran–Israel, Israel–Yemen — and divided
    states are region-mates, not distance-mates), or involve a P5 state
    (microstates join through the P5 rule only: Grenada 1983). This is the
    exposure denominator observed dyads can't provide — pairs that never
    fought are in here too. Distances end in 2002 and are carried forward
    through the state-succession alias plus NEW_STATE_NEIGHBORS patches."""
    by_abbrev = {s["abbrev"]: s["gwno"] for s in states}
    membership = {s["gwno"]: system_years(s, last_year) for s in states if not s["microstate"]}
    micro_membership = {s["gwno"]: system_years(s, last_year) for s in states if s["microstate"]}
    region_of = {s["gwno"]: s["region"] for s in states}

    def in_system(g, y):
        return y in membership.get(g, ())

    prox: dict[int, dict[tuple, int]] = defaultdict(dict)  # year -> {(a,b): km}
    unmatched = set()
    with open(SOURCES / "gw-mindist.csv", newline="") as f:
        for r in csv.DictReader(f):
            y = int(r["year"])
            if y < YEAR_MIN:
                continue
            a, b = by_abbrev.get(r["ida"]), by_abbrev.get(r["idb"])
            if a is None or b is None:
                unmatched.add(r["ida"] if a is None else r["idb"])
                continue
            km = int(r["mindist"])
            if km <= PAIR_KM and a != b:
                prox[y][(min(a, b), max(a, b))] = km
    if unmatched:
        print(f"  pair universe: no gwno for mindist ids {sorted(unmatched)[:8]}")
    data_end = max(prox)

    # carry the last observed year forward through succession and new states
    for y in range(data_end + 1, last_year + 1):
        carried = {}
        for (a, b), km in prox[data_end].items():
            a2, b2 = to_gw(a, y), to_gw(b, y)
            if a2 != b2:
                carried[(min(a2, b2), max(a2, b2))] = km
        for g, neighbors in NEW_STATE_NEIGHBORS.items():
            if in_system(g, y):
                for n in neighbors:
                    n = to_gw(n, y)
                    if n != g:
                        carried[(min(g, n), max(g, n))] = 0
        prox[y] = carried

    hits: dict[tuple, dict] = {}
    for r in dyadic_rows:
        if CONFLICT_TYPES[r["type_of_conflict"]] != "interstate":
            continue
        y = int(r["year"])
        war = r["intensity_level"] == "2"
        side_a = [to_gw(g, y) for g in gwno_list(r["gwno_a"])]
        side_b = [to_gw(g, y) for g in gwno_list(r["gwno_b"])]
        for a in side_a:
            for b in side_b:
                if a == b:
                    continue
                key = (min(a, b), max(a, b), y)
                h = hits.setdefault(key, {"war": False})
                h["war"] = h["war"] or war

    rows = []
    covered = missed = 0
    for y in range(YEAR_MIN, last_year + 1):
        members = [g for g in membership if in_system(g, y)]
        relevant: dict[tuple, tuple] = {}
        for i, a in enumerate(members):  # same-region pairs
            for b in members[i + 1 :]:
                if region_of[a] == region_of[b]:
                    relevant[(min(a, b), max(a, b))] = ("", "region")
        for (a, b), km in prox.get(y, {}).items():
            if in_system(a, y) and in_system(b, y):
                relevant[(a, b)] = (km, "prox")
        for g in P5:
            g = to_gw(g, y)
            if not in_system(g, y):
                continue
            for other in members + [m for m in micro_membership if y in micro_membership[m]]:
                if other == g:
                    continue
                key = (min(g, other), max(g, other))
                km = relevant.get(key, ("",))[0]
                relevant[key] = (km, relevant[key][1] if key in relevant else "major")
        for (a, b), (km, via) in sorted(relevant.items()):
            h = hits.get((a, b, y))
            rows.append([a * 1000 + b, a, b, y, km, via, 1 if h else 0, 1 if h and h["war"] else 0])
        for (a, b, hy) in list(hits):
            if hy == y and (a, b) not in relevant:
                missed += 1
        covered += sum(1 for (a, b, hy) in hits if hy == y and (a, b) in relevant)
    total_hits = covered + missed
    print(
        f"  pair universe: {len(rows):,} pair-years; interstate hit coverage "
        f"{covered}/{total_hits} ({covered / max(total_hits, 1):.1%}) via ≤{PAIR_KM}km ∪ same-region ∪ P5"
        + (f"; {missed} hit pair-years outside (see method.md)" if missed else "")
    )
    header = ["pair_id", "gwno_a", "gwno_b", "year", "km", "via", "active", "war"]
    return [header] + rows


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
    pair_table = build_pair_year(states, dyadic_rows, last_year)
    regime_table = build_regime(states, last_year)
    episode_table = build_episodes()
    coup_table = build_coups(states, last_year)
    population_table = build_population(states, last_year)
    covariate_table = build_covariates(states, last_year)
    bdh_table = build_battle_deaths_history()
    mids_table = build_mids(states)
    alliance_table = build_alliances(states)
    peace = build_peace_agreements(states)
    if peace:
        dump_yaml(REGISTRY / "peace-agreements.yaml", peace)
    write_csv(TABLES / "country-year.csv", cy_table[0], cy_table[1:])
    write_csv(TABLES / "dyad-year.csv", dy_table[0], dy_table[1:])
    write_csv(TABLES / "country-month.csv", cm_table[0], cm_table[1:])
    write_csv(TABLES / "dyad-month.csv", dm_table[0], dm_table[1:])
    write_csv(TABLES / "pair-year.csv", pair_table[0], pair_table[1:])
    write_csv(TABLES / "regime.csv", regime_table[0], regime_table[1:])
    write_csv(TABLES / "episode.csv", episode_table[0], episode_table[1:])
    write_csv(TABLES / "coup.csv", coup_table[0], coup_table[1:])
    write_csv(TABLES / "population.csv", population_table[0], population_table[1:])
    write_csv(TABLES / "covariates.csv", covariate_table[0], covariate_table[1:])
    if len(bdh_table) > 1:
        write_csv(TABLES / "battle-deaths-history.csv", bdh_table[0], bdh_table[1:])
    if len(mids_table) > 1:
        write_csv(TABLES / "mids.csv", mids_table[0], mids_table[1:])
    if len(alliance_table) > 1:
        write_csv(TABLES / "alliances.csv", alliance_table[0], alliance_table[1:])

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
            "pair_years": len(pair_table) - 1,
        },
    }
    dump_yaml(DATA / "meta.yaml", meta)
    print("build complete")


if __name__ == "__main__":
    main()
