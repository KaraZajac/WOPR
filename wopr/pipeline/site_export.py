"""Export render-ready JSON for the Astro site into data/site/.

Everything the site plots is computed here, in Python, against the committed
tables — the site's JS layer only reads and draws. Outputs:

  summary.json    headline numbers, Global War Index series, the WWIII panel,
                  global deaths-by-category and monthly tempo, top risks
  countries.json  per country: engine prior now (+ladder), walk-forward prior
                  series (the "percentage over time"), deaths by category,
                  ACD activity years, monthly tempo, conflicts
  map.json        ISO-3166-numeric -> {gwno, p} join for the world choropleth
  questions.json  the journal, render-ready
  backtest.json   engine reliability (from data/backtest.yaml)

Global War Index: the percentile rank (0–100) of a year's global organized-
violence deaths (sb+ns+os best estimates) within 1989–present — transparent,
reproducible, no weights to argue about. The current partial year is shown
annualized from candidate months and marked provisional, never ranked.

WWIII panel: engine-style conditional base rates at the global grain —
P(≥1 interstate conflict/war year follows the current state) from 1946–,
plus great-power (P5) pair history. Operational definitions in the payload.
"""

import csv
import datetime
import json
from collections import defaultdict

import yaml

import wopr
from wopr.engine import baserate
from wopr.engine.backtest import walk
from wopr.journal import store
from wopr.paths import DATA, REGISTRY, ROOT, TABLES

SITE = DATA / "site"
P5 = {2: "United States", 200: "United Kingdom", 220: "France", 365: "Russia (USSR)", 710: "China"}

# states.yaml name -> world-atlas (Natural Earth 110m) name, where they differ
NE_NAMES = {
    "United States of America": "United States of America",
    "Myanmar (Burma)": "Myanmar",
    "DR Congo (Zaire)": "Dem. Rep. Congo",
    "Congo": "Congo",
    "Ivory Coast": "Côte d'Ivoire",
    "Cote D'Ivoire": "Côte d'Ivoire",
    "Bosnia-Herzegovina": "Bosnia and Herz.",
    "Central African Republic": "Central African Rep.",
    "Dominican Republic": "Dominican Rep.",
    "Equatorial Guinea": "Eq. Guinea",
    "South Sudan": "S. Sudan",
    "Solomon Islands": "Solomon Is.",
    "Czech Republic": "Czechia",
    "Czechia": "Czechia",
    "Macedonia, FYR": "North Macedonia",
    "North Macedonia": "North Macedonia",
    "Russia (Soviet Union)": "Russia",
    "Yemen (North Yemen)": "Yemen",
    "Vietnam (North Vietnam)": "Vietnam",
    "Cambodia (Kampuchea)": "Cambodia",
    "Laos": "Laos",
    "Serbia (Yugoslavia)": "Serbia",
    "Serbia": "Serbia",
    "Zimbabwe (Rhodesia)": "Zimbabwe",
    "Turkey (Türkiye)": "Turkey",
    "Türkiye": "Turkey",
    "East Timor": "Timor-Leste",
    "Timor-Leste": "Timor-Leste",
    "Eswatini (Swaziland)": "eSwatini",
    "Kingdom of eSwatini (Swaziland)": "eSwatini",
    "North Macedonia": "Macedonia",
    "Brunei Darussalam": "Brunei",
    "United Arab Emirates": "United Arab Emirates",
    "Bahamas": "Bahamas",
    "Gambia": "Gambia",
    "Guinea-Bissau": "Guinea-Bissau",
    "Sri Lanka (Ceylon)": "Sri Lanka",
    "Iran (Persia)": "Iran",
    "Taiwan": "Taiwan",
    "North Korea": "North Korea",
    "South Korea": "South Korea",
    "Belarus (Byelorussia)": "Belarus",
    "Kyrgyz Republic": "Kyrgyzstan",
    "Kyrgyzstan": "Kyrgyzstan",
    "Burkina Faso (Upper Volta)": "Burkina Faso",
    "Madagascar (Malagasy)": "Madagascar",
    "Suriname (Surinam)": "Suriname",
    "Tanzania": "Tanzania",
    "Western Sahara": "W. Sahara",
    "Falkland Islands": "Falkland Is.",
}


def rows_of(name):
    with open(TABLES / name, newline="") as f:
        return list(csv.DictReader(f))


def dump(name, obj):
    SITE.mkdir(exist_ok=True)
    path = SITE / name
    with open(path, "w") as f:
        json.dump(obj, f, separators=(",", ":"), sort_keys=True, ensure_ascii=False)
    print(f"  -> {path.relative_to(ROOT)} ({path.stat().st_size:,} bytes)")


def month_key(y, m):
    return f"{int(y):04d}-{int(m):02d}"


# ---------------------------------------------------------------- countries


def build_countries(meta, states, conflicts, substrate):
    cy = rows_of("country-year.csv")
    cm = rows_of("country-month.csv")
    last_year = substrate["last_year"]

    deaths = defaultdict(list)
    activity = defaultdict(list)
    for r in cy:
        g = int(r["gwno"])
        y = int(r["year"])
        if r["sb_deaths"] != "":
            deaths[g].append([y, int(r["sb_deaths"]), int(r["ns_deaths"]), int(r["os_deaths"])])
        if r["acd_intensity"] != "0":
            activity[g].append([y, int(r["acd_intensity"])])

    horizon = 36  # months of tempo shown on country pages
    months_all = sorted({month_key(r["year"], r["month"]) for r in cm})
    recent = set(months_all[-horizon:])
    tempo = defaultdict(dict)
    for r in cm:
        mk = month_key(r["year"], r["month"])
        if mk not in recent:
            continue
        g = int(r["gwno"])
        t = tempo[g].setdefault(mk, {"deaths": 0, "provisional": 0})
        t["deaths"] += int(r["sb_deaths"]) + int(r["ns_deaths"]) + int(r["os_deaths"])
        t["provisional"] = max(t["provisional"], int(r["provisional"]))

    series = defaultdict(list)  # walk-forward engine priors, per country
    for rec in walk("country", "deaths", ("sb",), 25, substrate):
        series[rec["unit"]].append([rec["year"], round(rec["p"], 4)])

    by_country = defaultdict(list)
    for c in conflicts:
        for g in c["countries"]:
            by_country[g].append(
                {
                    "id": c["id"],
                    "name": c["name"],
                    "type": c["type"],
                    "first": c["active_years"][0],
                    "last": c["active_years"][-1],
                    "years_active": len(c["active_years"]),
                }
            )

    out = {}
    for st in states:
        g = st["gwno"]
        current = any(sp["to"] is None for sp in st["system"])
        if st["microstate"] or not current or g not in substrate["country"]:
            continue  # dead states keep their history in the aggregates, not a risk page
        r = baserate.rate(baserate.Spec("country", g, "deaths", ("sb",), 25, as_of=last_year + 1), substrate)
        out[str(g)] = {
            "gwno": g,
            "name": st["name"],
            "abbrev": st["abbrev"],
            "region": st["region"],
            "p": r["p"],
            "bucket": r["bucket"],
            "level": r["headline_level"],
            "ladder": {
                lvl: {k: e.get(k) for k in ("units", "years", "hits", "rate", "posterior")}
                for lvl, e in r["levels"].items()
            },
            "p_series": series.get(g, []),
            "deaths": deaths.get(g, []),
            "activity": activity.get(g, []),
            "tempo": [[mk, v["deaths"], v["provisional"]] for mk, v in sorted(tempo.get(g, {}).items())],
            "conflicts": sorted(by_country.get(g, []), key=lambda c: -c["last"]),
        }
    return out


# ---------------------------------------------------------------- map join


def build_map(states, countries):
    atlas = json.loads((ROOT / "site" / "src" / "assets" / "countries-110m.json").read_text())
    by_name = {
        g["properties"]["name"]: g["id"]
        for g in atlas["objects"]["countries"]["geometries"]
        if g.get("id")  # disputed territories carry no ISO numeric id
    }
    join, unmatched = {}, []
    for st in states:
        if str(st["gwno"]) not in countries:
            continue
        ne = NE_NAMES.get(st["name"], st["name"])
        iso = by_name.get(ne)
        if iso is None:
            unmatched.append(st["name"])
            continue
        c = countries[str(st["gwno"])]
        join[iso] = {"gwno": st["gwno"], "p": c["p"], "name": st["name"], "bucket": c["bucket"]}
    if unmatched:
        print(f"  map: no geometry for {len(unmatched)}: {', '.join(sorted(unmatched)[:8])}")
    return join


# ---------------------------------------------------------------- global series


def build_global(meta, conflicts, dyads):
    cy = rows_of("country-year.csv")
    cm = rows_of("country-month.csv")

    by_year = defaultdict(lambda: [0, 0, 0])
    for r in cy:
        if r["sb_deaths"] != "":
            y = int(r["year"])
            by_year[y][0] += int(r["sb_deaths"])
            by_year[y][1] += int(r["ns_deaths"])
            by_year[y][2] += int(r["os_deaths"])
    deaths_series = [[y, *by_year[y]] for y in sorted(by_year)]

    active_count = defaultdict(int)
    for c in conflicts:
        for y in c["active_years"]:
            active_count[y] += 1
    interstate_years = defaultdict(int)
    war_years = defaultdict(int)
    for d in dyads:
        if d["type"] != "interstate":
            continue
        for y in d["active_years"]:
            interstate_years[y] += 1
    dy = rows_of("dyad-year.csv")
    dyad_type = {d["id"]: d["type"] for d in dyads}
    for r in dy:
        if r["acd_intensity"] == "2" and dyad_type.get(int(r["dyad_id"])) == "interstate":
            war_years[int(r["year"])] += 1

    conflict_series = [[y, active_count[y], interstate_years.get(y, 0), war_years.get(y, 0)] for y in sorted(active_count)]

    totals = {y: sum(v) for y, v in by_year.items()}
    ranked = sorted(totals.values())

    def percentile(v):
        below = sum(1 for x in ranked if x < v)
        return round(100 * below / (len(ranked) - 1), 1) if len(ranked) > 1 else 50.0

    gwi_series = [[y, totals[y], percentile(totals[y])] for y in sorted(totals)]

    # current partial year from candidate months, annualized for display only
    months = defaultdict(int)
    provisional_months = set()
    for r in cm:
        mk = month_key(r["year"], r["month"])
        months[mk] += int(r["sb_deaths"]) + int(r["ns_deaths"]) + int(r["os_deaths"])
        if r["provisional"] == "1":
            provisional_months.add(mk)
    tempo = [[mk, v, 1 if mk in provisional_months else 0] for mk, v in sorted(months.items())][-48:]
    current_year = max(int(mk[:4]) for mk in provisional_months) if provisional_months else None
    partial = None
    if current_year:
        got = [v for mk, v, _ in tempo if int(mk[:4]) == current_year]
        annualized = round(sum(got) / len(got) * 12) if got else None
        partial = {
            "year": current_year,
            "months": len(got),
            "deaths": sum(got),
            "annualized": annualized,
            "percentile_if_annualized": percentile(annualized) if annualized else None,
        }

    return {
        "deaths_series": deaths_series,
        "conflict_series": conflict_series,
        "gwi": {"series": gwi_series, "latest": gwi_series[-1], "partial": partial},
        "tempo": tempo,
    }


# ---------------------------------------------------------------- WWIII panel


def transition(years_flags, condition):
    """P(flag at y | flag at y-1 == condition) over consecutive observed years."""
    ys = sorted(years_flags)
    k = n = 0
    for a, b in zip(ys, ys[1:]):
        if b - a != 1 or years_flags[a] != condition:
            continue
        n += 1
        k += int(years_flags[b])
    return {"k": k, "n": n, "rate": round(k / n, 4) if n else None}


def build_wwiii(meta, dyads, substrate):
    last_year = substrate["last_year"]
    dy = rows_of("dyad-year.csv")
    dyad = {d["id"]: d for d in dyads}

    any_interstate = {y: False for y in range(1946, last_year + 1)}
    any_war = dict(any_interstate)
    p5_activity = dict(any_interstate)
    p5_war = dict(any_interstate)
    p5_war_wide = dict(any_interstate)  # counting secondary warring parties (Korea, Vietnam)
    for r in dy:
        d = dyad.get(int(r["dyad_id"]))
        if not d or d["type"] not in ("interstate", "intrastate", "internationalized-intrastate"):
            continue
        if r["acd_intensity"] == "0":
            continue
        y = int(r["year"])
        if y not in any_interstate:
            continue
        war = r["acd_intensity"] == "2"

        def ids(col):
            return {int(x) for x in r[col].split(";") if x}

        prim_a, prim_b = ids("gwno_a"), ids("gwno_b")
        wide_a, wide_b = prim_a | ids("gwno_a2"), prim_b | ids("gwno_b2")
        if d["type"] == "interstate":
            any_interstate[y] = True
            any_war[y] = any_war[y] or war
            if prim_a & set(P5) and prim_b & set(P5):
                p5_activity[y] = True
                p5_war[y] = p5_war[y] or war
        if war and wide_a & set(P5) and wide_b & set(P5):
            p5_war_wide[y] = True  # P5 forces on both sides of a war-intensity dyad

    n_years = last_year - 1946 + 1
    current_interstate = []
    for d in dyads:
        if d["type"] == "interstate" and d["active_years"] and d["active_years"][-1] == last_year:
            r = baserate.rate(
                baserate.Spec("dyad", d["id"], "acd-active", (), 25, as_of=last_year + 1), substrate
            )
            current_interstate.append(
                {"id": d["id"], "name": d["name"], "since": d["active_years"][0], "p_continue": r["p"]}
            )

    def block(flags, label):
        cond = flags[last_year]
        return {
            "definition": label,
            "years_true": sum(flags.values()),
            "years": n_years,
            "unconditional": round(sum(flags.values()) / n_years, 4),
            "state_now": cond,
            "conditional": transition(flags, cond),
        }

    return {
        "as_of": last_year + 1,
        "hero": block(any_war, f"≥1 interstate war (≥1,000 battle deaths in the year) anywhere, {1946}–{last_year}"),
        "any_interstate": block(any_interstate, "≥1 UCDP-active interstate dyad (≥25 deaths)"),
        "p5_activity": block(p5_activity, "≥1 interstate dyad with permanent-UNSC members on both sides (≥25 deaths)"),
        "p5_war": block(p5_war, "≥1 great-power war: P5 as primary parties on both sides, ≥1,000 battle deaths in the year"),
        "p5_war_wide": block(
            p5_war_wide,
            "≥1 war-intensity conflict with P5 forces on both sides counting secondary parties (Korea, Vietnam pattern)",
        ),
        "p5_war_years": sorted(y for y, v in p5_war.items() if v),
        "p5_war_wide_years": sorted(y for y, v in p5_war_wide.items() if v),
        "active_now": sorted(current_interstate, key=lambda d: -d["p_continue"]),
        "notes": [
            "conditional = the historical frequency of the state repeating, given this year's state (one-step transition)",
            "'world war' has no UCDP operationalization; the P5-both-sides war rate is the closest defensible proxy",
            "battle-death thresholds use UCDP intensity coding (war = ≥1,000 in the calendar year)",
        ],
    }


# ---------------------------------------------------------------- main


def main() -> None:
    meta = yaml.safe_load((DATA / "meta.yaml").read_text())
    states = yaml.safe_load((REGISTRY / "states.yaml").read_text())
    conflicts = yaml.safe_load((REGISTRY / "conflicts.yaml").read_text())
    dyads = yaml.safe_load((REGISTRY / "dyads.yaml").read_text())
    substrate = baserate.load_substrate()

    print("computing country pages…")
    countries = build_countries(meta, states, conflicts, substrate)
    print("computing global series…")
    global_block = build_global(meta, conflicts, dyads)
    wwiii = build_wwiii(meta, dyads, substrate)

    top = sorted(countries.values(), key=lambda c: -c["p"])
    movers = sorted(
        (c for c in countries.values() if len(c["p_series"]) >= 6),
        key=lambda c: -(c["p_series"][-1][1] - c["p_series"][-6][1]),
    )
    summary = {
        "version": wopr.__version__,
        "release": meta["ucdp_release"],
        "annual_end": meta["annual_coverage_end"],
        "data_through": meta["data_through"],
        "built": meta["built"],
        "counts": meta["counts"],
        **global_block,
        "wwiii": wwiii,
        "top_risk": [
            {"gwno": c["gwno"], "name": c["name"], "p": c["p"], "bucket": c["bucket"]} for c in top[:12]
        ],
        "movers": [
            {
                "gwno": c["gwno"],
                "name": c["name"],
                "p": c["p_series"][-1][1],
                "delta5y": round(c["p_series"][-1][1] - c["p_series"][-6][1], 4),
            }
            for c in movers[:6] + movers[-6:]
        ],
    }

    questions = []
    for q in store.load_all():
        d = (q.get("prior") or {}).get("detail") or {}
        questions.append(
            {
                "id": q["id"],
                "title": q["title"],
                "question": q["question"],
                "status": q["status"],
                "tags": q.get("tags", []),
                "criteria": q["criteria"],
                "prior": (
                    {"p": q["prior"]["p"], "bucket": d.get("bucket"), "level": d.get("headline_level")}
                    if q.get("prior")
                    else None
                ),
                "forecasts": q.get("forecasts", []),
                "resolution": q.get("resolution"),
            }
        )

    dump("summary.json", summary)
    dump("countries.json", countries)
    dump("map.json", build_map(states, countries))
    dump("questions.json", questions)
    backtest_path = DATA / "backtest.yaml"
    if backtest_path.exists():
        dump("backtest.json", yaml.safe_load(backtest_path.read_text()))
    print("export complete")


if __name__ == "__main__":
    main()
