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

    # coup history + prior per country (from the Powell–Thyne substrate)
    coups = defaultdict(list)
    with open(TABLES / "coup.csv", newline="") as f:
        for r in csv.DictReader(f):
            if int(r["attempts"]) > 0:
                coups[int(r["gwno"])].append([int(r["year"]), int(r["attempts"]), int(r["successes"])])

    # structural covariates per country — full recent series + latest value
    cov_cols = ["gdp_pc", "inflation", "pop_0014", "urban_pct", "infant_mort", "excluded_share"]
    cov_series = defaultdict(lambda: defaultdict(list))
    covariates = defaultdict(dict)
    with open(TABLES / "covariates.csv", newline="") as f:
        for r in csv.DictReader(f):
            g, y = int(r["gwno"]), int(r["year"])
            for c in cov_cols:
                if r[c] != "":
                    v = float(r[c])
                    covariates[g][c] = v  # latest year wins
                    if y >= last_year - 35:
                        cov_series[g][c].append([y, v])

    # global percentile of each country's latest value, per covariate
    cov_pctl = {}
    for c in cov_cols:
        vals = sorted(v[c] for v in covariates.values() if c in v)
        for g, cur in covariates.items():
            if c in cur:
                below = sum(1 for x in vals if x < cur[c])
                cov_pctl.setdefault(g, {})[c] = round(below / (len(vals) - 1), 2) if len(vals) > 1 else 0.5

    # honest risk-factor framing from the descriptive/protocol findings:
    # (label, higher-is-riskier?, is it a validated engine covariate?)
    RISK = {
        "pop_0014": ("young population", True, "strong onset signal descriptively (~4× lift), but adds nothing once conflict history is conditioned on — see methods"),
        "excluded_share": ("ethnically excluded population", True, "compounds with youth in the record; not yet an engine covariate"),
        "gdp_pc": ("low income", False, "poverty is a classic conflict correlate"),
        "infant_mort": ("high infant mortality", True, "a development/state-capacity proxy"),
        "inflation": ("high inflation", True, "NOT predictive of onset in our test — shown for context only"),
        "urban_pct": ("urbanization", True, "context only"),
    }

    def risk_factors(g):
        out = []
        for c, (label, hi_risky, note) in RISK.items():
            if c not in covariates[g] or g not in cov_pctl or c not in cov_pctl[g]:
                continue
            p = cov_pctl[g][c]
            elevated = p >= 0.66 if hi_risky else p <= 0.34
            out.append({"factor": label, "value": covariates[g][c], "pctl": p, "elevated": elevated, "note": note})
        return sorted(out, key=lambda r: -r["pctl"] if r else 0)

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
        entry = {
            "gwno": g,
            "name": st["name"],
            "abbrev": st["abbrev"],
            "region": st["region"],
            "p": r["p"],
            "bucket": r["bucket_coarse"],
            "bucket_detail": r["bucket"],
            "nowcast": r.get("nowcast", {}).get("year"),
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
            "coups": sorted(coups.get(g, [])),
            "covariates": dict(covariates.get(g, {})),
            "cov_series": {c: v for c, v in cov_series.get(g, {}).items()},
            "risk_factors": risk_factors(g) if g in covariates else [],
        }
        if coups.get(g) is not None and g in substrate["country"]:
            try:
                cr = baserate.rate(baserate.Spec("country", g, "coup", (), 1, as_of=last_year + 1), substrate)
                entry["coup_p"] = cr["p"]
                entry["coup_bucket"] = cr["bucket"]
            except (KeyError, ValueError):
                pass
        out[str(g)] = entry
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


# ---------------------------------------------------------------- dyads & watchfloor


def build_dyads(dyads, substrate, last_year):
    """Interstate + intrastate dyads active in the last decade, with the
    continuation and (for still-active dyads) termination priors — the
    browsable face of the dyad grain and the termination measure."""
    out = []
    for d in dyads:
        if not d["active_years"] or d["active_years"][-1] < last_year - 10:
            continue
        if d["id"] not in substrate["dyad"]:
            continue
        cont = baserate.rate(baserate.Spec("dyad", d["id"], "acd-active", (), 25, last_year + 1), substrate)
        row = {
            "id": d["id"],
            "name": d["name"],
            "type": d["type"],
            "region": d["region"],
            "first": d["active_years"][0],
            "last": d["active_years"][-1],
            "years_active": len(d["active_years"]),
            "p_continue": cont["p"],
            "bucket": cont["bucket_coarse"],
        }
        if d["active_years"][-1] == last_year:
            term = baserate.rate(baserate.Spec("dyad", d["id"], "terminates", (), 25, last_year + 1), substrate)
            row["p_terminate"] = term["p"]
        out.append(row)
    out.sort(key=lambda d: (-d["last"], -d["p_continue"]))
    return out


def build_watchfloor():
    from wopr.engine import watchfloor as wf

    board = wf.compute(baserate.load_substrate())
    return board


REGIME_LABEL = {0: "closed autocracy", 1: "electoral autocracy", 2: "electoral democracy", 3: "liberal democracy"}


def build_trends(conflicts, dyads):
    """Long-run trend series for the /trends page — all from committed tables."""
    cy = rows_of("country-year.csv")
    dy = rows_of("dyad-year.csv")
    pop = {(int(r["gwno"]), int(r["year"])): int(r["population"]) for r in rows_of("population.csv")}
    dyad_type = {d["id"]: d["type"] for d in dyads}

    # 1. the long peace — active conflicts per year by type, 1946–
    active_by_type = defaultdict(lambda: defaultdict(set))
    for r in dy:
        if r["acd_intensity"] == "0":
            continue
        t = dyad_type.get(int(r["dyad_id"]), r["type"] or "intrastate")
        kind = "interstate" if t == "interstate" else "intrastate"
        active_by_type[int(r["year"])][kind].add(int(r["dyad_id"]))
    long_peace = [
        [y, len(active_by_type[y]["interstate"]), len(active_by_type[y]["intrastate"])]
        for y in range(1946, max(active_by_type) + 1)
    ]

    # 1b. state-based battle deaths stitched 1946– (PRIO pre-1989 + GED 1989+)
    prio = defaultdict(int)
    bdh_path = TABLES / "battle-deaths-history.csv"
    if bdh_path.exists():
        for r in rows_of("battle-deaths-history.csv"):
            prio[int(r["year"])] += int(r["battle_deaths"])
    ged_sb = defaultdict(int)
    for r in cy:
        if r["sb_deaths"] != "":
            ged_sb[int(r["year"])] += int(r["sb_deaths"])
    battle_long = [
        [y, ged_sb[y] if y >= 1989 else prio.get(y, 0)]
        for y in range(1946, max(ged_sb) + 1)
    ]

    # 2. deaths by region over time (1989–), + global per-capita
    region_year = defaultdict(lambda: defaultdict(int))
    global_deaths = defaultdict(int)
    global_pop = defaultdict(int)
    for r in cy:
        if r["sb_deaths"] == "":
            continue
        y = int(r["year"])
        d = int(r["sb_deaths"]) + int(r["ns_deaths"]) + int(r["os_deaths"])
        region_year[y][r["region"]] += d
        global_deaths[y] += d
        global_pop[y] += pop.get((int(r["gwno"]), y), 0)
    regions = ["Africa", "Americas", "Asia", "Europe", "Middle East"]
    deaths_region = [[y] + [region_year[y][reg] for reg in regions] for y in sorted(region_year)]
    per_capita = [
        [y, round(global_deaths[y] / global_pop[y] * 1e6, 2) if global_pop[y] else None]
        for y in sorted(global_deaths)
    ]

    # 3. coups per decade — attempts vs successes
    dec_att = defaultdict(int)
    dec_succ = defaultdict(int)
    for r in rows_of("coup.csv"):
        dec = (int(r["year"]) // 10) * 10
        dec_att[dec] += int(r["attempts"])
        dec_succ[dec] += int(r["successes"])
    coups_decade = [[f"{d}s", dec_att[d], dec_succ[d]] for d in sorted(dec_att)]

    # 4. the world by regime type, 1946– (share of states)
    reg_year = defaultdict(lambda: defaultdict(int))
    for r in rows_of("regime.csv"):
        reg_year[int(r["year"])][int(r["regime"])] += 1
    regime_share = [
        [y] + [reg_year[y][b] for b in (0, 1, 2, 3)]
        for y in range(1946, max(reg_year) + 1)
    ]

    # 5. how conflicts end — outcome mix by era, + survival curve
    eps = rows_of("episode.csv")
    outcome_era = defaultdict(lambda: defaultdict(int))
    durations = []
    for e in eps:
        if e["terminated"] != "1" or not e["outcome"]:
            continue
        end = int(e["end_year"]) if e["end_year"] else None
        if end:
            era = "1946–89" if end < 1990 else "1990–2009" if end < 2010 else "2010–now"
            outcome_era[era][e["outcome"]] += 1
        if e["end_year"] and e["start_year"]:
            durations.append(int(e["end_year"]) - int(e["start_year"]) + 1)
    outcomes = ["low-activity", "government-victory", "peace-agreement", "ceasefire", "actor-ceases", "rebel-victory"]
    endings = {era: [outcome_era[era][o] for o in outcomes] for era in ("1946–89", "1990–2009", "2010–now")}
    n = len(durations)
    survival = [[t, round(sum(1 for d in durations if d > t) / n, 4)] for t in range(0, 26)] if n else []

    return {
        "long_peace": long_peace,
        "battle_deaths_long": battle_long,
        "deaths_by_region": {"regions": regions, "series": deaths_region},
        "per_capita": per_capita,
        "coups_decade": coups_decade,
        "regime_share": {"bands": [REGIME_LABEL[b] for b in (0, 1, 2, 3)], "series": regime_share},
        "endings": {"outcomes": outcomes, "by_era": endings, "median_duration": sorted(durations)[n // 2] if n else None, "n": n},
        "survival": survival,
    }


def build_timeline(conflicts, dyads):
    """A layered timeline of global conflict, 1946–: per-year counts of the
    things that mark eras — onsets, wars, terminations, coups — plus a short
    list of marquee labeled events."""
    dy = rows_of("dyad-year.csv")
    dyad_type = {d["id"]: d["type"] for d in dyads}
    by_year = defaultdict(lambda: {"active": 0, "wars": 0, "onsets": 0, "terminations": 0, "coups": 0})

    active_prev = set()
    years = sorted({int(r["year"]) for r in dy})
    active_in = defaultdict(set)
    war_in = defaultdict(set)
    for r in dy:
        if r["acd_intensity"] != "0":
            active_in[int(r["year"])].add(int(r["dyad_id"]))
        if r["acd_intensity"] == "2":
            war_in[int(r["year"])].add(int(r["dyad_id"]))
    prev = set()
    for y in years:
        cur = active_in[y]
        by_year[y]["active"] = len(cur)
        by_year[y]["wars"] = len(war_in[y])
        by_year[y]["onsets"] = len(cur - prev)
        by_year[y]["terminations"] = len(prev - cur)
        prev = cur
    for e in rows_of("episode.csv"):  # authoritative terminations
        if e["terminated"] == "1" and e["end_year"]:
            by_year[int(e["end_year"])]["terminations"] = by_year[int(e["end_year"])].get("terminations", 0)
    for r in rows_of("coup.csv"):
        by_year[int(r["year"])]["coups"] += int(r["attempts"])

    series = [
        [y, by_year[y]["active"], by_year[y]["wars"], by_year[y]["onsets"], by_year[y]["coups"]]
        for y in range(1946, max(by_year) + 1)
    ]
    eras = [
        {"from": 1946, "to": 1991, "label": "Cold War"},
        {"from": 1991, "to": 2001, "label": "Post–Cold War"},
        {"from": 2001, "to": 2014, "label": "War on Terror"},
        {"from": 2014, "to": 2026, "label": "Great-power return"},
    ]
    return {"series": series, "eras": eras}


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
                    {
                        "p": q["prior"]["p"],
                        "bucket": d.get("bucket_coarse") or d.get("bucket"),
                        "bucket_detail": d.get("bucket"),
                        "level": d.get("headline_level"),
                    }
                    if q.get("prior")
                    else None
                ),
                "forecasts": q.get("forecasts", []),
                "resolution": q.get("resolution"),
            }
        )

    print("computing dyads…")
    dyad_rows = build_dyads(dyads, substrate, meta["counts"] and int(meta["annual_coverage_end"][:4]))
    print("computing watchfloor…")
    watch = build_watchfloor()
    summary["watchfloor_top"] = watch["units"][:8]
    summary["coup_top"] = sorted(
        (
            {"gwno": c["gwno"], "name": c["name"], "p": c.get("coup_p"), "bucket": c.get("coup_bucket")}
            for c in countries.values()
            if c.get("coup_p") is not None
        ),
        key=lambda c: -c["p"],
    )[:12]

    dump("summary.json", summary)
    dump("countries.json", countries)
    dump("map.json", build_map(states, countries))
    dump("questions.json", questions)
    dump("dyads.json", dyad_rows)
    dump("watchfloor.json", watch)
    print("computing trends & timeline…")
    dump("trends.json", build_trends(conflicts, dyads))
    dump("timeline.json", build_timeline(conflicts, dyads))
    backtest_path = DATA / "backtest.yaml"
    if backtest_path.exists():
        dump("backtest.json", yaml.safe_load(backtest_path.read_text()))
    benchmark_path = DATA / "benchmark.yaml"
    if benchmark_path.exists():
        dump("benchmark.json", yaml.safe_load(benchmark_path.read_text()))
    print("export complete")


if __name__ == "__main__":
    main()
