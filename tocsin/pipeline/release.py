"""Assemble the redistributable dataset bundle: `tocsin release`.

Produces dist/tocsin-dataset-<version>/ (+ .tar.gz) containing the derived
tables and registries, an auto-generated codebook (descriptions below, spans
and row counts read from the live files), and the rights/citation documents.
The bundle is licensed CC BY 4.0 — the most permissive license the most
restrictive committed input (UCDP) allows; see DATA-RIGHTS.md. ACLED never
enters the committed data, so nothing here inherits its terms.

Version = the UCDP annual release the build is pinned to (data/meta.yaml),
so a bundle is reproducible from `tocsin pull && tocsin build` at that release.
"""

import csv
import tarfile

import yaml

from tocsin.paths import DATA, REGISTRY, ROOT, TABLES

DIST = ROOT / "dist"

# table -> (one-line description, {column: description})
CODEBOOK = {
    "country-year.csv": (
        "Country-year conflict activity and organized-violence deaths, 1946–present (UCDP).",
        {
            "gwno": "Gleditsch–Ward country code (the dataset spine; Serbia is 340 from 2007)",
            "country": "UCDP country name",
            "region": "UCDP region (Africa/Americas/Asia/Europe/Middle East)",
            "year": "calendar year",
            "main_system": "1 if a G-W main-system member that year (microstates 0)",
            "acd_intensity": "UCDP/PRIO ACD intensity on territory: 0 none, 1 minor, 2 war",
            "sb_deaths": "state-based battle deaths (GED best estimate; empty before 1989)",
            "ns_deaths": "non-state conflict deaths (GED; empty before 1989)",
            "os_deaths": "one-sided violence deaths (GED; empty before 1989)",
        },
    ),
    "dyad-year.csv": (
        "State-based dyad-years: UCDP ACD dyads plus sub-threshold GED-only dyads.",
        {
            "dyad_id": "UCDP dyad id",
            "conflict_id": "UCDP conflict id (empty for GED-only dyads)",
            "year": "calendar year",
            "acd_intensity": "0 none / 1 minor / 2 war for the dyad-year",
            "type": "conflict type (interstate/intrastate/…)",
            "region": "semicolon-joined UCDP regions",
            "gwno_a": "side A primary state (G-W)",
            "gwno_b": "side B primary state or 0 for non-state side",
            "gwno_a2": "comma list of side A secondary states active that year",
            "gwno_b2": "comma list of side B secondary states active that year",
            "ged_events": "GED events attributed to the dyad (1989+)",
            "ged_deaths": "GED best-estimate deaths (1989+)",
        },
    ),
    "country-month.csv": (
        "Country-month organized-violence events and deaths, 1989–present (GED + candidate).",
        {
            "gwno": "G-W country code",
            "year": "year",
            "month": "month 1–12",
            "sb_events": "state-based events",
            "sb_deaths": "state-based deaths (best)",
            "ns_events": "non-state events",
            "ns_deaths": "non-state deaths",
            "os_events": "one-sided events",
            "os_deaths": "one-sided deaths",
            "provisional": "1 if from candidate GED (preliminary, may be revised)",
        },
    ),
    "dyad-month.csv": (
        "Dyad-month events/deaths for all three violence types, 1989–present.",
        {
            "dyad_id": "UCDP dyad id (per violence type)",
            "type": "sb / ns / os",
            "year": "year",
            "month": "month 1–12",
            "events": "GED events",
            "deaths": "GED best-estimate deaths",
            "provisional": "1 if from candidate GED",
        },
    ),
    "pair-year.csv": (
        "The pair universe: every politically-relevant country pair-year (proximity ≤400km ∪ same region ∪ P5), 1946–present.",
        {
            "pair_id": "stable pair id",
            "gwno_a": "lower G-W code of the pair",
            "gwno_b": "higher G-W code",
            "year": "calendar year (both states in system)",
            "km": "G-W minimum distance in km (empty where unavailable)",
            "via": "why the pair is in the universe: prox/region/p5 flags",
            "active": "1 if a UCDP state-based dyad between them was active",
            "war": "1 if that activity reached war intensity (≥1,000)",
        },
    ),
    "episode.csv": (
        "Conflict episodes (continuous activity spells) per dyad with termination coding.",
        {
            "dyad_id": "UCDP dyad id",
            "epid": "episode id (dyad + ordinal)",
            "start_year": "first active year",
            "end_year": "last active year (empty if ongoing)",
            "terminated": "1 if the episode ended within the data",
            "outcome": "termination outcome (Kreutz/UCDP classes; empty where uncoded)",
        },
    ),
    "coup.csv": (
        "Coup attempts and successes per country-year, 1950–present (Powell–Thyne).",
        {
            "gwno": "G-W country code",
            "year": "year",
            "attempts": "coup attempts",
            "successes": "successful coups",
        },
    ),
    "regime.csv": (
        "Regimes-of-the-World classification per country-year (V-Dem via OWID).",
        {
            "gwno": "G-W country code",
            "year": "year",
            "regime": "0 closed autocracy · 1 electoral autocracy · 2 electoral democracy · 3 liberal democracy",
        },
    ),
    "population.csv": (
        "Population per country-year (OWID; UN WPP/HYDE), carried forward to the data edge.",
        {
            "gwno": "G-W country code",
            "year": "year",
            "population": "total population (carried forward beyond the last OWID year)",
        },
    ),
    "covariates.csv": (
        "Structural covariates per country-year (World Bank WDI + EPR + COW CINC). Context tables — none are engine inputs (each failed the tune/validate protocol; see the methods).",
        {
            "gwno": "G-W country code",
            "year": "year",
            "gdp_pc": "GDP per capita, constant US$ (WDI NY.GDP.PCAP.KD)",
            "inflation": "consumer-price inflation, annual % (WDI FP.CPI.TOTL.ZG; IMF-sourced)",
            "pop_0014": "population share aged 0–14, % (WDI)",
            "pop_1564": "population share aged 15–64, % (WDI)",
            "urban_pct": "urban population share, % (WDI)",
            "infant_mort": "infant mortality per 1,000 live births (WDI)",
            "pop_growth": "population growth, annual % (WDI)",
            "excluded_share": "population share in politically-excluded ethnic groups (EPR-2021)",
            "cinc": "COW composite index of national capability (share of world; NMC v7)",
        },
    ),
    "battle-deaths-history.csv": (
        "Pre-GED state-based battle deaths per country-year, 1946–2008 (PRIO Battle Deaths v3.1, best estimate, split evenly across locations).",
        {
            "gwno": "G-W country code (conflict location)",
            "year": "year",
            "battle_deaths": "best-estimate battle deaths",
        },
    ),
    "mids.csv": (
        "Militarized interstate disputes per undirected country pair-year, 1946–2014 (COW dyadic MID 4.03, crosswalked to G-W codes).",
        {
            "gwno_a": "lower G-W code",
            "gwno_b": "higher G-W code",
            "year": "year",
            "disputes": "distinct disputes involving the pair that year",
            "hostility": "dyad-year max hostility, 1–5 (4 = use of force, 5 = war)",
            "fatal": "1 if any dispute recorded fatalities",
        },
    ),
    "alliances.csv": (
        "Formal alliance pair-years, 1946–2012 (COW v4.1; row presence = any alliance).",
        {
            "gwno_a": "lower G-W code",
            "gwno_b": "higher G-W code",
            "year": "year",
            "defense": "1 if a defense pact (the strongest commitment class)",
        },
    ),
}

REGISTRIES = {
    "states.yaml": "G-W state system: gwno, names, regions, microstate flag, system-membership spells.",
    "conflicts.yaml": "UCDP/PRIO state-based conflicts: type, incompatibility, regions, countries, active years.",
    "dyads.yaml": "State-based dyads (ACD + sub-threshold): sides, conflict linkage, active years.",
    "nonstate.yaml": "UCDP non-state conflict dyads.",
    "onesided.yaml": "UCDP one-sided violence actors.",
    "peace-agreements.yaml": "UCDP Peace Agreement records (context; irregular cadence).",
}


def table_stats(name: str) -> tuple[int, str]:
    with open(TABLES / name, newline="") as f:
        rows = list(csv.DictReader(f))
    years = [int(r["year"]) for r in rows if r.get("year")]
    span = f"{min(years)}–{max(years)}" if years else "—"
    return len(rows), span


def codebook(version: str) -> str:
    lines = [
        f"# TOCSIN dataset codebook — v{version}",
        "",
        "A merged, redistributable conflict-research dataset on a common spine —",
        "Gleditsch–Ward country code × year — derived from UCDP/PRIO, Gleditsch–Ward,",
        "Powell–Thyne, V-Dem (via OWID), OWID population, World Bank WDI, EPR, and",
        "Correlates of War. License: **CC BY 4.0** with the attribution chain in",
        "DATA-RIGHTS.md (included in this bundle). Build pinned to UCDP release",
        f"{version}; regenerate from source with `tocsin pull && tocsin build`.",
        "",
        "Country codes are Gleditsch–Ward throughout (UCDP and COW codes are",
        "crosswalked year-aware at build time; Serbia is 340 from 2007, unified",
        "Germany 260, unified Yemen 678).",
        "",
        "## Tables (`tables/`)",
    ]
    for name, (desc, cols) in CODEBOOK.items():
        n, span = table_stats(name)
        lines += ["", f"### {name}", "", f"{desc}", "", f"*{n:,} rows · {span}*", ""]
        lines += [f"- `{c}` — {d}" for c, d in cols.items()]
    lines += ["", "## Registries (`registry/`)", ""]
    lines += [f"- `{name}` — {desc}" for name, desc in REGISTRIES.items()]
    lines += [
        "",
        "## Provenance & citation",
        "",
        "Every upstream source, its license, and its required citation is listed in",
        "DATA-RIGHTS.md. Cite this dataset via CITATION.cff, and cite UCDP (and the",
        "other sources you use) as described there.",
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    meta_path = DATA / "meta.yaml"
    if not meta_path.exists():
        raise SystemExit("data/meta.yaml missing — run `tocsin build` (and `make verify`) first")
    version = str(yaml.safe_load(meta_path.read_text())["ucdp_release"])
    missing = [n for n in CODEBOOK if not (TABLES / n).exists()]
    if missing:
        raise SystemExit(f"tables missing from data/tables: {missing} — run the full pipeline first")

    name = f"tocsin-dataset-{version}"
    stage = DIST / name
    if stage.exists():
        for p in sorted(stage.rglob("*"), reverse=True):
            p.unlink() if p.is_file() else p.rmdir()
    (stage / "tables").mkdir(parents=True)
    (stage / "registry").mkdir()

    (stage / "CODEBOOK.md").write_text(codebook(version))
    for doc in ("DATA-RIGHTS.md", "CITATION.cff"):
        (stage / doc).write_bytes((ROOT / doc).read_bytes())
    (stage / "LICENSE-DATA.txt").write_text(
        "The data files in this bundle are licensed CC BY 4.0\n"
        "(https://creativecommons.org/licenses/by/4.0/), with the per-source\n"
        "attribution requirements listed in DATA-RIGHTS.md.\n"
    )
    for n in CODEBOOK:
        (stage / "tables" / n).write_bytes((TABLES / n).read_bytes())
    for n in REGISTRIES:
        src = REGISTRY / n
        if src.exists():
            (stage / "registry" / n).write_bytes(src.read_bytes())
    (stage / "meta.yaml").write_bytes(meta_path.read_bytes())

    tarball = DIST / f"{name}.tar.gz"
    with tarfile.open(tarball, "w:gz") as tf:
        tf.add(stage, arcname=name)
    files = sum(1 for p in stage.rglob("*") if p.is_file())
    print(f"  staged {files} files -> {stage.relative_to(ROOT)}")
    print(f"  -> {tarball.relative_to(ROOT)} ({tarball.stat().st_size:,} bytes)")
    print("  upload the tarball to Zenodo (or attach to a GitHub release) for a DOI")


if __name__ == "__main__":
    main()
