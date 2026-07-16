"""Reference-class base rates over the built tables (the outside view).

A rate query asks: for unit u (a country or a state-based dyad), what fraction
of comparable unit-years met the measure — e.g. ≥25 state-based battle deaths
in a calendar year? The engine answers with an explicit ladder rather than a
single number:

  self    u's own history
  region  units sharing u's region
  global  all units of the grain

and every level is *conditioned on recency and episode age* — class-years are
matched to u's current bucket (``active-1/2-3/4-9/10+``: hit last year, banded
by consecutive hit-years; ``recent``: 2–3 years ago; ``dormant``: 4–10;
``cold``: >10 or never). The headline probability is u's own bucket history
shrunk toward the class rate by an approximate empirical-Bayes prior strength
M estimated from between-unit dispersion (see docs/method.md), clamped away
from 0/1 by a Jeffreys floor. When candidate months show the current partial
year already meeting the measure, next-year questions get the bucket promoted
and aged (promote-only nowcast; see nowcast_bucket).

Honesty notes baked into the output: the dyad universe contains only dyads
UCDP ever observed in conflict, so dyad-grain rates are recurrence rates, not
rates for arbitrary country pairs; substrates are left-censored (ACD 1946,
deaths 1989); windows are approximated by calendar-year rates.
"""

import csv
from dataclasses import dataclass, field
from pathlib import Path

from wopr.paths import TABLES

# `active` is split by episode age (consecutive hit-years so far): fresh
# flares and decade-old wars continue at very different rates, and pooling
# them was the engine's one measured calibration defect (dyad top bins ~5–6
# points overconfident). Buckets are ordered youngest-episode first.
# Active buckets also carry an intensity band — was the latest hit-year above
# the UCDP war line? — and non-active country buckets carry "+nbr" when a
# ≤400km neighbor is in active conflict (both arena/backtest-motivated).
AGE_BANDS = ((1, 1, "active-1"), (2, 3, "active-2-3"), (4, 9, "active-4-9"), (10, 10_000, "active-10+"))
INTENSITY_BANDS = ("minor", "war")
WAR_DEATHS = 1000  # the UCDP war line, for deaths measures
BUCKETS = tuple(
    f"{age}|{band}" for _, _, age in AGE_BANDS for band in INTENSITY_BANDS
) + ("recent", "recent+nbr", "dormant", "dormant+nbr", "cold", "cold+nbr")
MIN_CLASS_YEARS = 30  # fall from region to global below this
M_DEFAULT = 50.0
M_MIN, M_MAX = 5.0, 1000.0
DEATHS_START = 1989  # UCDP death counts begin with GED
ACD_START = 1946


def coarse(bucket: str) -> str:
    """active-2-3|war -> active, cold+nbr~mid -> cold (for badges/map keys)."""
    base = bucket.split("|")[0].split("+")[0].split("~")[0]
    return "active" if base.startswith("active") else base


@dataclass
class Spec:
    grain: str  # country | dyad
    unit: int
    measure: str = "deaths"  # deaths | acd-active
    types: tuple = ("sb",)  # deaths measure: subset of sb/ns/os (country grain)
    threshold: int = 25
    as_of: int = 0  # forecast year; bucket uses history strictly before it
    period: tuple = ()  # substrate years, defaulted by measure

    def normalized(self, last_year: int, coup_span: tuple | None = None) -> "Spec":
        start = DEATHS_START if self.measure == "deaths" else ACD_START
        # terminates needs year+1 observable, so the scoreable period ends early
        hi = last_year - 1 if self.measure == "terminates" else last_year
        period = self.period or (start, hi)
        if self.measure == "coup" and not self.period and coup_span:
            period = coup_span  # Powell–Thyne coverage, not the UCDP span
        as_of = self.as_of or last_year + 1
        return Spec(self.grain, self.unit, self.measure, tuple(self.types), self.threshold, as_of, period)

    def to_dict(self) -> dict:
        return {
            "grain": self.grain,
            "unit": self.unit,
            "measure": self.measure,
            "types": list(self.types),
            "threshold": self.threshold,
            "as_of": self.as_of,
            "period": list(self.period),
        }


@dataclass
class Unit:
    id: int
    name: str
    region: list
    first_year: int  # exposure start (system entry / first observed activity)
    last_year: int
    years: dict = field(default_factory=dict)  # year -> {"acd": int, "sb": int|None, ...}


def load_neighbors(tables: Path = TABLES, km: int = 400) -> dict:
    """gwno -> year -> set of gwnos within `km` (from the pair table, so
    succession and system exits are already year-resolved)."""
    from collections import defaultdict

    out: dict[int, dict[int, set]] = defaultdict(lambda: defaultdict(set))
    with open(tables / "pair-year.csv", newline="") as f:
        for r in csv.DictReader(f):
            if r["km"] == "" or int(r["km"]) > km:
                continue
            a, b, y = int(r["gwno_a"]), int(r["gwno_b"]), int(r["year"])
            out[a][y].add(b)
            out[b][y].add(a)
    return {g: dict(years) for g, years in out.items()}


REGIME_BANDS = {0: "aut", 1: "mid", 2: "mid", 3: "dem"}  # Regimes of the World, collapsed a priori


def load_covariate(col: str, tables: Path = TABLES) -> dict:
    """(gwno, year) -> value for one covariates.csv column. Kept separate from
    the engine's live path — only the tune/validate protocol reads these."""
    path = tables / "covariates.csv"
    if not path.exists():
        return {}
    out = {}
    with open(path, newline="") as f:
        for r in csv.DictReader(f):
            if r[col]:
                out[(int(r["gwno"]), int(r["year"]))] = float(r[col])
    return out


def load_youth(tables: Path = TABLES) -> dict:
    """Share of population under 14 (World Bank) — the strongest single onset
    covariate in the descriptive test (protocol verdict: rejected)."""
    return load_covariate("pop_0014", tables)


def load_mids(tables: Path = TABLES) -> dict:
    """(gwno_a, gwno_b) a<b -> list of (year, hostility, fatal) militarized
    dispute years (COW dyadic MID, 1946–2014). Context for the pair universe;
    enters buckets only through the protocol's flag hook."""
    path = tables / "mids.csv"
    if not path.exists():
        return {}
    out: dict[tuple, list] = {}
    with open(path, newline="") as f:
        for r in csv.DictReader(f):
            key = (int(r["gwno_a"]), int(r["gwno_b"]))
            out.setdefault(key, []).append((int(r["year"]), int(r["hostility"]), int(r["fatal"])))
    return out


def load_alliances(tables: Path = TABLES) -> dict:
    """(gwno_a, gwno_b) a<b -> set of years with a defense pact in force
    (COW Formal Alliances, 1946–2012)."""
    path = tables / "alliances.csv"
    if not path.exists():
        return {}
    out: dict[tuple, set] = {}
    with open(path, newline="") as f:
        for r in csv.DictReader(f):
            if r["defense"] == "1":
                out.setdefault((int(r["gwno_a"]), int(r["gwno_b"])), set()).add(int(r["year"]))
    return out


def load_regime(tables: Path = TABLES) -> dict:
    """(gwno, year) -> 'aut'|'mid'|'dem' from the committed V-Dem/OWID table.
    The middle band (electoral autocracies + electoral democracies) is the
    anocracy belt the onset literature flags as riskiest."""
    path = tables / "regime.csv"
    if not path.exists():
        return {}
    out = {}
    with open(path, newline="") as f:
        for r in csv.DictReader(f):
            out[(int(r["gwno"]), int(r["year"]))] = REGIME_BANDS[int(r["regime"])]
    return out


def _nbr_active(countries: dict, neighbors: dict) -> set:
    """(gwno, year) pairs where ≥1 ≤400km neighbor had active sb conflict
    (≥25 deaths or ACD-active) that year. Spec-independent by design."""
    active = set()
    for gwno, u in countries.items():
        for y, row in u.years.items():
            if row.get("acd", 0) > 0 or (row.get("sb") or 0) >= 25:
                active.add((gwno, y))
    flagged = set()
    for gwno, y in active:
        for g in neighbors.get(gwno, {}).get(y, ()):
            flagged.add((g, y))
    return flagged


def load_partial(tables: Path, last_year: int) -> dict | None:
    """Candidate-month totals for the first year past the annual substrate —
    the nowcasting input. Returns {"year", "months", "country": {gwno:
    {sb,ns,os}}, "dyad": {id: deaths}} or None when no partial year exists."""
    years = set()
    country: dict[int, dict] = {}
    dyad: dict[int, int] = {}
    months = set()
    with open(tables / "country-month.csv", newline="") as f:
        for r in csv.DictReader(f):
            y = int(r["year"])
            if y <= last_year:
                continue
            years.add(y)
    if not years:
        return None
    target = min(years)  # only the first partial year can nowcast buckets
    with open(tables / "country-month.csv", newline="") as f:
        for r in csv.DictReader(f):
            if int(r["year"]) != target:
                continue
            months.add(int(r["month"]))
            c = country.setdefault(int(r["gwno"]), {"sb": 0, "ns": 0, "os": 0})
            for t in ("sb", "ns", "os"):
                c[t] += int(r[f"{t}_deaths"])
    with open(tables / "dyad-month.csv", newline="") as f:
        for r in csv.DictReader(f):
            if int(r["year"]) != target or r["type"] != "sb":
                continue
            dyad[int(r["dyad_id"])] = dyad.get(int(r["dyad_id"]), 0) + int(r["deaths"])
    return {"year": target, "months": len(months), "country": country, "dyad": dyad}


def load_substrate(tables: Path = TABLES) -> dict:
    """Read the committed year tables into Unit maps keyed by grain."""
    countries: dict[int, Unit] = {}
    with open(tables / "country-year.csv", newline="") as f:
        for r in csv.DictReader(f):
            if r["main_system"] != "1":
                continue
            gwno, year = int(r["gwno"]), int(r["year"])
            u = countries.setdefault(gwno, Unit(gwno, r["country"], [r["region"]], year, year))
            u.first_year = min(u.first_year, year)
            u.last_year = max(u.last_year, year)
            u.years[year] = {
                "acd": int(r["acd_intensity"]),
                "sb": int(r["sb_deaths"]) if r["sb_deaths"] != "" else None,
                "ns": int(r["ns_deaths"]) if r["ns_deaths"] != "" else None,
                "os": int(r["os_deaths"]) if r["os_deaths"] != "" else None,
            }
    dyads: dict[int, Unit] = {}
    with open(tables / "dyad-year.csv", newline="") as f:
        for r in csv.DictReader(f):
            did, year = int(r["dyad_id"]), int(r["year"])
            region = [s.strip() for s in r["region"].split(";") if s.strip()]
            u = dyads.setdefault(did, Unit(did, "", region, year, year))
            u.first_year = min(u.first_year, year)
            u.last_year = max(u.last_year, year)
            u.years[year] = {
                "acd": int(r["acd_intensity"]),
                "sb": int(r["ged_deaths"]) if r["ged_deaths"] != "" else None,
            }
    pairs: dict[int, Unit] = {}
    pair_ids: dict[tuple, int] = {}
    region_of = {g: u.region[0] for g, u in countries.items()}
    with open(tables / "pair-year.csv", newline="") as f:
        for r in csv.DictReader(f):
            pid, year = int(r["pair_id"]), int(r["year"])
            u = pairs.get(pid)
            if u is None:
                a, b = int(r["gwno_a"]), int(r["gwno_b"])
                pair_ids[(a, b)] = pid
                regions = sorted({region_of.get(a, ""), region_of.get(b, "")} - {""})
                u = pairs[pid] = Unit(pid, "", regions, year, year)
            u.first_year = min(u.first_year, year)
            u.last_year = max(u.last_year, year)
            # exposure = row presence; a pair-year outside the universe has no row
            u.years[year] = {"acd": 2 if r["war"] == "1" else 1 if r["active"] == "1" else 0}
    last = max(u.last_year for u in countries.values())
    coup_span = None
    coup_path = tables / "coup.csv"
    if coup_path.exists():
        years = set()
        with open(coup_path, newline="") as f:
            for r in csv.DictReader(f):
                gwno, y = int(r["gwno"]), int(r["year"])
                years.add(y)
                u = countries.get(gwno)
                if u is not None and y in u.years:
                    u.years[y]["coup"] = int(r["attempts"])
                    u.years[y]["coup_s"] = int(r["successes"])
        if years:
            coup_span = (min(years), max(years))
    neighbors = load_neighbors(tables)
    return {
        "country": countries,
        "dyad": dyads,
        "pair": pairs,
        "last_year": last,
        "coup_span": coup_span,
        "partial": load_partial(tables, last),
        "neighbors": neighbors,
        "nbr_active": _nbr_active(countries, neighbors),
        "regime": load_regime(tables),
        "youth": load_youth(tables),
        "excluded": load_covariate("excluded_share", tables),
        "pair_ids": pair_ids,
        "mids": load_mids(tables),
        "alliances": load_alliances(tables),
    }


def hit(u: Unit, year: int, spec: Spec) -> bool | None:
    """Did unit-year meet the measure? None = not exposed / not measurable."""
    lo, hi = spec.period
    if year < lo or year > hi:
        return None
    if spec.grain == "pair":
        # exposure is the relevance universe itself: no row, no denominator
        row = u.years.get(year)
        return None if row is None else row.get("acd", 0) > 0
    if spec.measure == "terminates":
        # at risk only while active; the hit is "this was the final year"
        if year < u.first_year or (u.years.get(year) or {}).get("acd", 0) == 0:
            return None
        return (u.years.get(year + 1) or {}).get("acd", 0) == 0
    if spec.measure == "coup":
        row = u.years.get(year)
        if row is None or "coup" not in row:
            return None  # outside Powell–Thyne coverage
        return row["coup"] >= 1
    if spec.measure == "acd-active":
        if year < u.first_year:
            return None
        return (u.years.get(year) or {}).get("acd", 0) > 0
    if year < max(u.first_year, DEATHS_START):
        return None
    # a missing row (dyad grain) or a missing count is zero recorded deaths
    row = u.years.get(year) or {}
    total = sum(row.get(t) or 0 for t in spec.types)
    return total >= spec.threshold


def bucket_twin(spec: Spec) -> Spec:
    """The spec whose history defines the bucket. For `terminates` the state
    that matters is the episode itself — recency/age/intensity of ACTIVITY —
    so the bucket scan runs on the acd-active twin, extended one year past
    the terminates period: activity in the final data year is known even
    though that year's terminality isn't."""
    if spec.measure != "terminates":
        return spec
    period = (spec.period[0], spec.period[1] + 1)
    return Spec(spec.grain, spec.unit, "acd-active", (), spec.threshold, spec.as_of, period)


def war_year(u: Unit, year: int, spec: Spec) -> bool:
    """Did `year` sit above the intensity line? For deaths/activity that is
    the UCDP war threshold; for coups the analogue is "included a SUCCESSFUL
    coup" (|war = the latest coup year succeeded, |minor = attempts only)."""
    row = u.years.get(year) or {}
    if spec.measure == "acd-active":
        return row.get("acd", 0) >= 2
    if spec.measure == "coup":
        return row.get("coup_s", 0) >= 1
    return sum(row.get(t) or 0 for t in spec.types) >= WAR_DEATHS


def bucket_of(
    u: Unit,
    year: int,
    spec: Spec,
    nbr: set | None = None,
    regime: dict | None = None,
    flag: set | None = None,
) -> str | None:
    """Recency/episode-age bucket entering `year`, from history strictly
    before it. Active units are banded by consecutive hit-years (episode
    age) and by last year's intensity (|minor / |war). Non-active units get
    "+nbr" when `nbr` (the substrate's neighbor-at-war set, country grain)
    flags a ≤400km neighbor in conflict last year, and "~aut/~mid/~dem" from
    last year's regime band when `regime` covers the unit (V-Dem RoW,
    collapsed; missing coverage simply omits the suffix). `flag` is the
    generic walk-forward-safe covariate hook — a set of (unit_id, year)
    membership keys that splits non-active buckets %f/%o; default-off, passed
    only by the tune/validate protocol until a covariate is adopted (youth:
    tested, rejected; see docs/method.md). For `terminates` the bucket is the
    episode's own activity state (the acd-active twin). Runs touching the
    substrate start are left-censored (age reads low)."""
    spec = bucket_twin(spec)
    lo, _ = spec.period
    start = max(lo, u.first_year if spec.measure == "acd-active" else max(u.first_year, DEATHS_START))
    if year <= start:  # no observable history yet
        return None
    last_hit = None
    for y in range(year - 1, start - 1, -1):
        if hit(u, y, spec):
            last_hit = y
            break
    if last_hit is None:
        base = "cold"
    else:
        gap = year - last_hit
        if gap == 1:
            age = 1
            y = year - 2
            while y >= start and hit(u, y, spec):
                age += 1
                y -= 1
            for a_lo, a_hi, name in AGE_BANDS:
                if a_lo <= age <= a_hi:
                    band = "war" if war_year(u, year - 1, spec) else "minor"
                    return f"{name}|{band}"
        base = "recent" if gap <= 3 else "dormant" if gap <= 10 else "cold"
    if nbr is not None and (u.id, year - 1) in nbr:
        base = f"{base}+nbr"
    if regime is not None:
        band = regime.get((u.id, year - 1))
        if band:
            base = f"{base}~{band}"
    if flag is not None and not base.startswith("active"):
        # covariate flags refine ONSET (non-active) buckets only
        base = f"{base}%f" if (u.id, year - 1) in flag else f"{base}%o"
    return base


def unit_bucket_years(
    u: Unit, spec: Spec, bucket: str, nbr: set | None = None, regime: dict | None = None, flag: set | None = None
) -> tuple[int, int]:
    """(hits k, exposure years n) for u restricted to years entered in `bucket`."""
    lo, hi = spec.period
    k = n = 0
    for y in range(lo + 1, hi + 1):
        h = hit(u, y, spec)
        if h is None or bucket_of(u, y, spec, nbr, regime, flag) != bucket:
            continue
        n += 1
        k += int(h)
    return k, n


def unconditional(u: Unit, spec: Spec) -> tuple[int, int]:
    lo, hi = spec.period
    k = n = 0
    for y in range(lo, hi + 1):
        h = hit(u, y, spec)
        if h is None:
            continue
        n += 1
        k += int(h)
    return k, n


def class_units(spec: Spec, substrate: dict, level: str) -> list[Unit]:
    units = substrate[spec.grain]
    me = units[spec.unit]
    if level == "self":
        return [me]
    if level == "global":
        return list(units.values())
    mine = set(me.region)
    return [u for u in units.values() if mine & set(u.region)] if mine else list(units.values())


def eb_strength(members: list[tuple[int, int]]) -> float:
    """Approximate empirical-Bayes prior strength from between-unit dispersion."""
    members = [(k, n) for k, n in members if n > 0]
    if len(members) < 3:
        return M_DEFAULT
    K = sum(k for k, _ in members)
    N = sum(n for _, n in members)
    p = K / N
    if p <= 0.0 or p >= 1.0:
        return M_MAX
    s2 = sum(n * (k / n - p) ** 2 for k, n in members) / N
    binom = p * (1 - p) * len(members) / N  # expected dispersion if homogeneous
    tau2 = s2 - binom
    if tau2 <= 0:
        return M_MAX
    return min(max(p * (1 - p) / tau2 - 1, M_MIN), M_MAX)


def rate(spec: Spec, substrate: dict) -> dict:
    """The full ladder for a spec; ['p'] is the headline prior."""
    spec = spec.normalized(substrate["last_year"], substrate.get("coup_span"))
    if spec.grain == "pair" and spec.measure != "acd-active":
        raise ValueError("pair grain supports the acd-active measure only (deaths per pair: roadmap)")
    if spec.measure == "terminates" and spec.grain != "dyad":
        raise ValueError("terminates is a dyad-grain measure (episodes belong to dyads)")
    if spec.measure == "coup":
        if spec.grain != "country":
            raise ValueError("coup is a country-grain measure")
        if substrate.get("coup_span") is None:
            raise ValueError("no coup table built — run `wopr pull && wopr build`")
    units = substrate[spec.grain]
    if spec.unit not in units:
        raise KeyError(f"unknown {spec.grain} id {spec.unit}")
    me = units[spec.unit]
    nbr = substrate.get("nbr_active") if spec.grain == "country" else None
    # regime conditioning was built and backtested: WORSE on every country
    # suite (cell fragmentation beats the anocracy signal — docs/method.md).
    # The capability stays (bucket_of takes `regime`); the engine passes None.
    regime = None
    # the unit's bucket is its status at the edge of observation — unobserved
    # years between the substrate end and as_of must not decay it toward cold.
    # The edge is the BUCKET data's edge (for terminates, one year past the
    # scoreable period: last year's activity is known, its terminality isn't).
    bucket_year = min(spec.as_of, bucket_twin(spec).period[1] + 1)
    bucket = bucket_of(me, bucket_year, spec, nbr, regime) or "cold"
    nowcast = nowcast_bucket(me, spec, substrate.get("partial"))
    if nowcast:
        bucket = nowcast["bucket"]
    k_self, n_self = unit_bucket_years(me, spec, bucket, nbr, regime)

    out = {
        "spec": spec.to_dict(),
        "unit_name": me.name or str(me.id),
        "bucket": bucket,
        "bucket_coarse": coarse(bucket),
        "bucket_data_end": min(spec.as_of - 1, spec.period[1]),
        "levels": {},
        "unconditional": {},
    }
    if nowcast:
        out["nowcast"] = nowcast
    posteriors = {}
    for level in ("self", "region", "global"):
        members = class_units(spec, substrate, level)
        counts = [unit_bucket_years(u, spec, bucket, nbr, regime) for u in members]
        K = sum(k for k, _ in counts)
        N = sum(n for _, n in counts)
        entry = {"units": len(members), "years": N, "hits": K, "rate": round(K / N, 4) if N else None}
        if level != "self" and N:
            M = eb_strength(counts)
            post = (k_self + M * (K / N)) / (n_self + M)
            entry["M"] = round(M, 1)
            entry["posterior"] = round(post, 4)
            posteriors[level] = (post, N)
        out["levels"][level] = entry
        totals = [unconditional(u, spec) for u in members]
        un_k, un_n = sum(k for k, _ in totals), sum(n for _, n in totals)
        out["unconditional"][level] = {
            "years": un_n,
            "hits": un_k,
            "rate": round(un_k / un_n, 4) if un_n else None,
        }

    if posteriors:
        use = "region" if posteriors.get("region") and posteriors["region"][1] >= MIN_CLASS_YEARS else "global"
        if use not in posteriors:
            use = next(iter(posteriors))
        p, n_level = posteriors[use]
    else:  # bucket empty even globally: fall back to the global unconditional rate
        use = "global-unconditional"
        e = out["unconditional"]["global"]
        p, n_level = (e["rate"] or 0.0), max(e["years"], 1)
    floor = 0.5 / (n_level + 1)
    out["headline_level"] = use
    out["p"] = round(min(max(p, floor), 1 - floor), 4)
    out["notes"] = notes(spec, substrate)
    if nowcast:
        out["notes"].append(
            f"bucket nowcast: {nowcast['year']} already meets the measure "
            f"({nowcast['total']} in {nowcast['months']} candidate months, provisional)"
        )
    return out


def nowcast_bucket(u: Unit, spec: Spec, partial: dict | None) -> dict | None:
    """Promote the target's bucket when the current partial year has already
    met the measure in candidate months. Promote-only: a quiet partial year
    is never treated as a quiet year. Applies only to questions about years
    strictly after the partial year — a question about the partial year
    itself must not see that year's own data in its prior."""
    if spec.grain == "pair" or spec.measure in ("terminates", "coup"):
        return None  # no candidate feed for pairs, termination, or coups
    if not partial or spec.as_of <= partial["year"] or spec.period[1] != partial["year"] - 1:
        return None
    if spec.measure == "acd-active":
        got = (partial[spec.grain].get(u.id, {}) or {}).get("sb", 0) if spec.grain == "country" else partial["dyad"].get(u.id, 0)
        met = got >= 25
    else:
        if spec.grain == "country":
            c = partial["country"].get(u.id, {})
            got = sum(c.get(t, 0) for t in spec.types)
        else:
            got = partial["dyad"].get(u.id, 0)
        met = got >= spec.threshold
    if not met:
        return None
    # age = run of hit-years through the substrate end, plus the partial year
    age = 1
    y = spec.period[1]
    while hit(u, y, spec):
        age += 1
        y -= 1
    band = next(name for a_lo, a_hi, name in AGE_BANDS if a_lo <= age <= a_hi)
    intensity = "war" if got >= WAR_DEATHS else "minor"
    return {"bucket": f"{band}|{intensity}", "year": partial["year"], "months": partial["months"], "total": got}


def notes(spec: Spec, substrate: dict | None = None) -> list[str]:
    ns = ["annual-hit probability; sub-annual or cross-year windows approximated by the calendar-year rate"]
    horizon = spec.as_of - (spec.period[1] + 1)
    if horizon > 0:
        ns.append(
            f"as_of {spec.as_of} is {horizon} year(s) past the substrate ({spec.period[1]}): bucket taken at the "
            f"data edge, one-step rate applied — slightly overstates persistence at longer horizons"
        )
    if spec.grain == "dyad":
        ns.append("dyad universe = dyads UCDP ever observed; this is a recurrence rate, not a rate for arbitrary pairs")
    if spec.measure == "deaths":
        ns.append(f"death counts begin {DEATHS_START} (GED); earlier history invisible to this measure")
    if spec.grain == "pair" and substrate is not None and substrate.get("mids"):
        by_pid = {pid: ab for ab, pid in substrate.get("pair_ids", {}).items()}
        disputes = substrate["mids"].get(by_pid.get(spec.unit, ()), [])
        if disputes:
            years = [y for y, _, _ in disputes]
            hi = max(h for _, h, _ in disputes)
            ns.append(
                f"COW record: militarized disputes in {len(years)} year(s), {min(years)}–{max(years)} "
                f"(max hostility {hi}/5). Cold pairs with MID history onset ~30× the never-MID rate "
                f"(measured 2026-07) — context only; conditioning on it failed the protocol (see methods)"
            )
    return ns


def render(result: dict) -> str:
    spec = result["spec"]
    measure = {
        "deaths": f"{'/'.join(spec['types'])} deaths ≥ {spec['threshold']}",
        "acd-active": "UCDP active (≥25 deaths)",
        "terminates": "episode terminates (active this year, inactive the next)",
        "coup": "coup attempt (Powell–Thyne; |war band = last coup year succeeded)",
    }[spec["measure"]]
    lines = [
        f"{result['unit_name']} ({spec['grain']} {spec['unit']}) — P({measure} in a calendar year)",
        f"as of {spec['as_of']} · bucket: {result['bucket']} (history through {result['bucket_data_end']})"
        f" · substrate {spec['period'][0]}–{spec['period'][1]}",
        "",
        f"{'level':<8} {'units':>6} {'yrs':>6} {'hits':>6} {'rate':>7} {'M':>7} {'posterior':>10}",
    ]
    for level, e in result["levels"].items():
        lines.append(
            f"{level:<8} {e['units']:>6} {e['years']:>6} {e['hits']:>6} "
            f"{e['rate'] if e['rate'] is not None else '—':>7} "
            f"{e.get('M', '—'):>7} {e.get('posterior', '—'):>10}"
        )
    lines.append("")
    lines.append(f"headline: p = {result['p']}  ({result['headline_level']} posterior, bucket-conditional)")
    uncond = ", ".join(
        f"{lvl} {e['rate'] if e['rate'] is not None else '—'}" for lvl, e in result["unconditional"].items()
    )
    lines.append(f"unconditional rates: {uncond}")
    for n in result["notes"]:
        lines.append(f"note: {n}")
    return "\n".join(lines)
