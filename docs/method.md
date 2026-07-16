# Method: how the base-rate engine works, and where it can lie to you

The engine answers one kind of query: **P(unit-year meets a measure)** — e.g.
"≥25 state-based battle deaths in Ethiopia in a calendar year". It never
answers with a single number silently; it answers with a *ladder* so the
reference-class choice is always visible.

## Substrates

| grain | measure | coverage | source table |
|---|---|---|---|
| country | `deaths` ≥ T (sb/ns/os subsets) | 1989–last release year | `data/tables/country-year.csv` (official UCDP country-year) |
| country | `acd-active` (UCDP inclusion: ≥25 sb deaths) | 1946– | same, `acd_intensity` column |
| dyad (state-based) | `deaths` ≥ T | 1989– | `data/tables/dyad-year.csv` (GED sums) |
| dyad (state-based) | `acd-active` | 1946– | same, `acd_intensity` column |

Exposure: countries count only main-system Gleditsch–Ward years (microstates
excluded); dyads count from their first observed year.

## Recency conditioning

Conflict is sticky — the unconditional global rate of a ≥25-death country-year
is ~0.17 versus ~0.85 for countries that had one last year — and *how long* it
has been sticky matters too. Every ladder level is conditioned on the target's
**bucket**, evaluated as of the forecast year:

- `active-1` / `active-2-3` / `active-4-9` / `active-10+` — met the measure
  last year, banded by the run of consecutive hit-years (episode age; worth
  ~35 points at dyad grain) — **× an intensity band** (`|minor` / `|war`:
  was the latest hit-year above the UCDP war line, 1,000 deaths or
  intensity 2).
- `recent` — last met 2–3 years ago
- `dormant` — 4–10 years ago
- `cold` — 11+ years ago, or never within the substrate
- non-active **country** buckets carry `+nbr` when a ≤400km neighbor (pair-
  universe distances) had active sb conflict last year — spatial contagion,
  measured at 7× for cold countries at month grain.

The intensity and neighbor splits were ablated against the walk-forward
backtest: **additive gains on the death-threshold suites** (sb≥25
.04145→.04109; all-types≥100 .03695→.03660) and dyads (.04085→.04055),
a small measured cost on country/acd-active (+.0005, likely the location-
attribution noise in country-level intensity) and a noise-level one at pair
grain (sparser cells). Both are kept **uniformly** — per-suite gating chosen
after seeing the numbers would be overfitting the backtest — and the mixed
cells stay on this record.

Class-years are counted only when they entered the same bucket the target is
in now. The first substrate year is skipped (no observable history); "never"
and episode ages are left-censored at the substrate start (a run touching
1989 reads younger than it is); a country quiet since 1989 may not truly be
`cold` in the long-run sense.

The target's bucket is taken **at the edge of observation** (substrate end +
1). A question about a year beyond that — e.g. calendar 2027 asked in
mid-2026 with annual data through 2025 — does not decay the bucket for years
nobody has observed. If candidate months show the partial current year
**already meeting the measure**, the bucket is promoted and its age extended
(**nowcast, promote-only** — a quiet partial year never demotes, because five
candidate months can't prove a quiet year). A question about the partial year
itself never sees that year's own data in its prior.

## Rolling windows (month grain)

Month-aligned windows that aren't calendar years — "next 12 months", "H2
2026" — are priced by the rolling engine (`tocsin/engine/rolling.py`) instead
of the calendar-year approximation: P(≥T deaths within the W months from
m₀), estimated over class member window-starts on the monthly substrate
(1989–). The bucket machinery ports intact: a unit's status entering month m
is its trailing-12-month record, age bands count consecutive trailing-hit
months (÷12 → the annual bands), and the recency cutoffs sit 12 months under
the annual ones because trailing windows lag activity by up to a year — with
that shift, January-start buckets provably equal the annual engine's (tested).
Candidate months feed the target's bucket naturally (noted as provisional).

At month grain, **active buckets carry a tempo band** — the count of
trailing-year months individually over the threshold (`low` 1–3, `mid` 4–8,
`high` 9–12) — so a sustained war and a single-spike year no longer share a
class. (A sum-active year with no single hit-month reads `low`.) The arena
priced this covariate: adding it moved TOCSIN's month-grain Brier from .0611
to .0461, closing 75% of the gap to VIEWS.

**Non-active buckets carry a neighbor flag** (`+nbr`: any ≤400km neighbor,
from the pair universe's distances, with ≥25 sb deaths in its own trailing
year). Measured contagion, walk-forward at a 2024 vantage: cold countries
next to a war hit at **7× the isolated cold rate** (.0018 vs .00026/month;
dormant 3×, recent 1.5×). Aggregate month-grain Brier barely moves (the
rates are tiny against mostly-zero outcomes), but the class distinction is
real and large — it is exactly the difference that matters for onset
questions at year grain.

**Measured negative results, kept on the record:**

1. *Horizon-aware class rates* — pricing a window g months past the data
   edge by class windows offset the same g — built, ablated, **worse**
   (+.003 Brier, worst at long horizons). Mechanism: class-level decay pools
   units that exit conflict with units that persist, underpricing the
   persisters that dominate scoring. The engine applies the one-step rate
   frozen across staleness; the machinery remains in `build_state(gaps=…)`.
2. *V-Dem regime conditioning* — Regimes of the World collapsed a priori to
   aut/mid/dem and suffixed onto non-active country buckets — built,
   ablated, **worse on every country suite** (sb≥25 .04109→.04131;
   all≥100 .03660→.03710; acd +.0003). Mechanism: a 3-way split stacked on
   the neighbor split fragments non-active cells below the region fallback
   threshold; estimator variance exceeds the anocracy signal, which region ×
   neighbor × history already partially carries. The engine passes
   `regime=None`; the capability is tested and the clean regime table
   (`data/tables/regime.csv`, V-Dem RoW via OWID) stays committed for
   display and for a future tune/validate-protocol revisit.

Caveats: window-starts overlap, so class counts are not independent — rates
and calibration read fine, but shrinkage/floors modestly overstate certainty.
Tempo is banded, not continuous — the residual ~.003 Brier to raw persistence
is discretization cost, left as-is deliberately (tuning bands on the same
vantages the arena scores would be overfitting; a tune/validate split is
future work). Country and dyad grains only; pairs stay annual.

## Coups (the method leaves UCDP entirely)

A country-grain measure over the **Powell–Thyne coup dataset** (1950–present,
via the Wayback CDX index — the uky.edu host blocks unattended clients), a
test of whether the reference-class method generalizes past UCDP outcomes.
It does: same buckets (a coup year enters `active-1`; the intensity band is
successful-vs-failed rather than war-vs-minor; recency/neighbor apply), and
walk-forward (6,145 country-years, base rate 1.9%) it scores **+18% skill vs
climatology** — the coup trap is real and the engine finds it (dormant coup
states run ~3×, active states higher). Powell–Thyne uses its own G-W codes
(`ccode_gw`); coups auto-resolve from the committed table (≥1 attempt = yes),
the dataset its sole authority, on the same annual cadence as termination.

## Termination (the machinery inverted)

`terminates` is a dyad-grain measure whose hit is "this was the episode's
final active year" (active in y, inactive in y+1, from our own activity
tables — validated at **99.6% agreement** against the UCDP Conflict
Termination dataset's coded episode ends). The bucket is the episode's own
activity state (the acd-active twin, allowed to see the final data year:
activity there is known even though its terminality isn't). Walk-forward
(2,797 at-risk dyad-years): the hazard falls monotonically with age and
intensity — fresh minor episodes end at ~32%/yr, decade-old wars at ~9%;
episodes entered from cold are ~50% one-and-done. Skill vs climatology is a
modest +7% — termination is genuinely hard — but the buckets separate
cleanly and the calibration tracks through the mass. Termination questions
resolve on a long cycle by construction: year Y needs the release covering
Y+1, annual authority only (candidate months can prove activity, never a
quiet year).

The UCDP long tail also lands: `data/registry/peace-agreements.yaml` (the
PA dataset — browsable context and outcome detail; its release cadence is
irregular and currently ends 2021, so it is **not** a near-term resolution
feed), and the UCDP MIC download, which turns out to be *mediation/talks*
data (third parties, good offices) rather than militarized confrontations —
cached, unbuilt, honestly labeled.

## The pair universe (every country against every country)

Observed dyads answer "will this conflict recur?" — they cannot price a pair
that never fought, because UCDP only contains pairs that did. The **pair
grain** supplies the missing denominator: for every year since 1946, all
country pairs that are *relevant* — Gleditsch–Ward minimum distance ≤400km,
**or** same UCDP region (this is what admits standoff-era conflicts like
Iran–Israel and Israel–Yemen, and divided states, which distance data
handles badly), **or** at least one P5 member (microstates join only through
this rule: Grenada 1983). ~244k pair-years; the outcome is UCDP interstate
activity between primary parties.

Measured coverage: 98.2% of interstate hit pair-years fall inside the
universe. The three known misses are one-year colonial/joiner artifacts
(Netherlands–Indonesia 1962, India–Hyderabad 1948, Iraq–Australia 2003) —
kept outside deliberately, because adding pairs *because* they fought would
select the denominator on the outcome. Distances end in 2002 and are carried
forward through state succession plus hand-coded neighbors for states born
later (Montenegro, Kosovo, South Sudan, Timor-Leste).

Walk-forward, the pair grain prices an arbitrary relevant pair at ~0.0006/yr
(cold pairs ≈ 0, dormant ≈ 3%, fresh interstate episodes continue ≈ 33%,
entrenched ones ≈ 77%; skill +23% vs climatology — modest by construction
for so rare an event). Pair questions resolve from GED interstate events
between the two governments in either direction, coalition sides included.
The pair substrate speaks only UCDP activity (≥25 deaths); other thresholds
have no pair denominator yet.

## The ladder and shrinkage

For target u in bucket B:

1. **self** — u's own k/n across its years that entered bucket B.
2. **region** — all units sharing u's region, same conditioning.
3. **global** — all units of the grain.

At the region and global levels the engine estimates an approximate
empirical-Bayes prior strength M from between-unit dispersion (method of
moments on the units' (kᵢ, nᵢ)): with p̂ the pooled rate and s² the
n-weighted between-unit variance,

    τ² = s² − p̂(1−p̂)·(#units / Σnᵢ)        (excess over binomial noise)
    M  = clamp(p̂(1−p̂)/τ² − 1, 5, 1000)       (τ² ≤ 0 → 1000; <3 units → 50)

and the posterior for u is `(k_self + M·p_level) / (n_self + M)`. Homogeneous
classes pool hard (M→1000: use the class rate); heterogeneous classes let u's
own history dominate.

**Headline rule:** the region posterior when the region bucket has ≥30
class-years, else the global posterior; clamped by a Jeffreys floor
`0.5/(n+1)` so the engine never says 0 or 1. If the bucket is empty even
globally, it falls back to the global unconditional rate and says so.

## Measured reliability (walk-forward backtest)

`tocsin backtest` replays the engine over every observable unit-year using only
prior data (~47k pseudo-forecasts; results in `data/backtest.yaml`). As of
UCDP 26.1 with episode-age buckets (engine 0.2.0): country-grain priors are
well calibrated end to end (sb≥25 skill +70%; acd-active +65%); dyad-grain
skill +60% with the former pooled-active defect largely repaired (the 70–80%
bin was 10 points hot under 4-bucket conditioning, now 4; 80–90% from 5.5 to
2.7). **Residual bias:** all active bands still run ~3 points optimistic at
dyad grain, and fresh onsets (`active-1`) are the least predictable class
(country sb: predicted .65, observed .56) — when your question sits in
`active-1`, treat the prior as soft — it is where challengers have the best shot.

## Structural covariates — what actually predicts onset (a finding)

We ingested World Bank WDI (income, inflation, age structure, urbanization,
infant mortality) and EPR ethnic-exclusion data (`data/tables/covariates.csv`)
and tested, descriptively, which separate conflict onsets from quiet years —
6,280 at-risk (currently-quiet) country-years, base onset rate ~3.3%:

| condition at year Y | P(active at Y+1) |
|---|---|
| baseline | 3.3% |
| **young population** (>39% under 14) | **6.5%** |
| older population | 1.7% |
| high inflation (>7%) | 3.7% |
| low inflation | 3.1% |
| young **and** politically-excluded (EPR) | **8.6%** |
| older, low-exclusion | 2.9% |

**The finding:** youth structure is a strong onset signal (~4× lift) and
ethnic exclusion compounds it; **inflation is weak and does not combine the
way one might expect** — the young/high-inflation cell (5.4%) is actually
*below* young/low-inflation (7.5%). This tested a specific hypothesis
(inflation + a young population → more onsets) and the honest answer was:
youth yes, exclusion yes, inflation no.

## The tune/validate protocol (how a covariate earns in)

The descriptive lift above is *not* permission to add youth to the engine —
fitting a scheme on the same history you score it on is p-hacking, the exact
error that made the reverted regime result look tempting. `tocsin protocol`
enforces the discipline: split the scored years into **tune** (≤2007, where
candidate schemes compete) and **validate** (≥2008, read exactly once); pick
the best youth cut on tune; compare it to the baseline on validate a single
time. A covariate is adopted only if it beats baseline on validate by a
pre-registered margin (≥1% relative) *and* helps a majority of cuts on tune.

**Result for youth: REJECTED.** On the tune set, **0 of 4** youth cuts even
beat the plain engine, and the least-bad one carried only a +0.4% (noise-
level) edge to validate — below the bar. The lesson is the deeper finding:
youth's strong *descriptive* onset lift adds essentially nothing *once the
engine already conditions on conflict recency and history* — the recency
buckets already capture what youth was proxying. This is the third covariate
(after regime, and horizon-decay) that looked promising and did not survive
honest out-of-sample testing, and it is direct support for the field's
"simple base rates are hard to beat" result (Cederman & Weidmann 2017).

The naive threshold (`ΔBrier < −0.0001`) would have *adopted* youth — a
covariate 0/4 cuts could beat on their own tuning data. That gap is the
whole reason the protocol exists. The data stays committed (it's real and
useful context on country pages); the live engine is unchanged.

### The COW pair study: a 30× signal the metric cannot see

`tocsin protocol --study pair` ran the four pre-registered COW candidates on
the pair universe (pair/acd-active, same 2007 split, same bar): **ever-MID,
MID-in-25yr, fatal-MID, defense-pact**. Verdict: **all four REJECTED** —
0/4 beat the baseline on tune; the selected one (ever-MID) was *worse* on
validate (−0.7% relative).

The decomposition is the finding. Descriptively the signal is enormous:
**cold pairs with militarized-dispute history onset at 30× the rate of
never-MID pairs** (0.194% vs 0.006%; 44/22,649 vs 14/215,855 pair-years).
But at a base rate of ~0.0006, even *perfect* conditioning moves aggregate
Brier by well under 0.1% — arithmetic, not noise: the no-history mass is
already scored nearly perfectly, and the flagged class is too small for its
improvement to register. **Brier is nearly blind to rare-event refinement at
the pair grain.** (The same mechanism explains why the pair suite shows only
+19.6% skill, and why the neighbor flag — a 7× class signal — was
Brier-invisible at country grain.)

Per the a-priori-once rule the verdict is final for this feature on this
history: the bar was pre-registered as Brier, and switching metrics after
seeing the result would be p-hacking. The signal ships as *display*: pair
`rate()` output now notes a pair's COW dispute record and the measured 30×
class rate, explicitly labeled as context that failed the protocol. If the
pair grain ever deserves its own adoption metric (log-loss would see this
signal), it must be pre-registered before the *next* vantage era so the
validate years are genuinely fresh.

### The joint study: combinations don't rescue rejected covariates

"What if the covariates were combined?" was answered narrowly and finally
(`tocsin protocol --study joint`). Combinations excluded a priori: anything at
pair grain (Brier-blind regardless) and regime × anything (fragmentation
already measured harmful). The one descriptively-motivated untested
combination was youth × ethnic exclusion (the 2×2 had shown young+excluded
onset at 8.6% vs 2.9%), plus exclusion solo, plus the OR. Result: **0/3 beat
baseline on tune; the selected (exclusion alone) was −1.0% relative on
validate — the worst validate read of any study.** The compound flag
young∧excluded, the strongest descriptive cell in the whole covariate
program, still lost to the plain engine on tune.

Why combining fails: each covariate's descriptive lift is *absorbed* by
recency conditioning (the risk it flags is already priced by "how recently
did this country fight"), and ANDing flags shrinks the flagged class (895
unit-years), so empirical-Bayes shrinkage pulls its split rate back toward
the parent — the signal survives as sociology but not as forecast
improvement.

**The 2007 vantage split is now retired.** Country-grain validate has been
consulted twice (youth, joint), pair-grain once (COW). Per the
pre-registration in `run_joint`, any future covariate study must use a fresh
era (2026+ outcomes) — this history has been spent.

Protocol scoreboard: regime, horizon-decay, youth, COW pair features, joint
covariates — **five for five REJECTED.** The recency-structured base rate
absorbs everything the conflict literature says should help, which is itself
the strongest evidence yet for the Cederman–Weidmann position — and the
project's central empirical claim when written up.

## Known approximations (read before trusting a prior)

- **Windows.** The engine computes annual-hit probabilities. Sub-annual
  windows inherit the calendar-year rate (an overestimate); 12-month windows
  crossing New Year are approximated by the window-start year. Multi-year
  windows are not modeled — split them into per-year questions.
- **Dyad selection bias.** The dyad universe is *dyads UCDP ever observed in
  organized violence*. A dyad rate is a recurrence/continuation rate. For a
  pair with no conflict history the engine has no denominator — that needs
  politically-relevant-dyad exposure (COW), which is on the roadmap.
- **Left-censoring.** Death-based measures start in 1989 (GED); `acd-active`
  in 1946. History before that is invisible, which biases `cold`-bucket
  membership.
- **Non-stationarity.** 1989 ≠ 2026. The ladder shows you the class; it does
  not reweight for time. Recency conditioning absorbs some drift, not all.
- **Attribution grain.** Country rates count violence *on a country's
  territory* (UCDP location), not violence *involving its government*.
  Interstate questions belong at dyad grain.

## The arena (model-vs-model benchmarking)

`tocsin benchmark` races TOCSIN against named challengers retrospectively on a
common target: **P(≥25 state-based deaths in a country-month)** — VIEWS's
native output. Their `main_dich` was verified to mean exactly that by
calibrating old runs against realized outcomes (mean prediction .138 vs
realized ≥25 frequency .136; the ≥1 frequency is .251 — detected, never
assumed). Every model predicts 12 months ahead from identical historical
vantages using only information available then; TOCSIN runs walk-forward-
clamped (`class_end`), one-step by design. Baselines: persistence (trailing-
12-month rate) and climatology (full-history rate).

Current standings (5 vantages, 7,680 country-months, UCDP 26.1; Brier, lower
better): **VIEWS 0.0412, persistence 0.0433, TOCSIN 0.0461, climatology
0.0922**. History: TOCSIN opened at 0.0611 with recency/age-only buckets; the
arena priced that tempo gap at ~0.017, and adding the tempo band closed 75%
of the deficit to VIEWS in one covariate. Readings: (1) VIEWS leads,
earning its covariates on transitions — but only ~5% ahead of naive
persistence, the standing embarrassment of this field, reproduced here
independently. (2) TOCSIN is now within ~12% of the academic SOTA with a
transparent lookup you can audit down to the class counts, and it wins 71%
of individual months head-to-head. (3) The residual to persistence is
banding discretization, deliberately not tuned against the arena. (4) Month
grain is VIEWS's home target; the annual-grain arena — TOCSIN's design center —
opens as journal questions resolve.

### The pools: the arena's most accurate forecast is nobody's model

The arena also scores **equal-weight opinion pools** — zero fitted
parameters, so scoring them on the same vantages is measurement, not tuning.
Result: **pool(views, persistence) = 0.0399**, beating VIEWS alone (0.0412,
−3.3%) and every other entrant; pool(all three) = 0.0409 also beats VIEWS.
This is the classic combination result (Bates–Granger 1969; Clemen 1989;
every M-competition): forecasters with *different* error structures average
into something better than the best of them.

The diagnostic detail: TOCSIN wins 70% of months against VIEWS yet *adding
TOCSIN to the views+persistence pool makes it worse* (0.0409 vs 0.0399) —
because at month grain TOCSIN **is** calibrated persistence; it duplicates the
pool's recency member rather than diversifying it. Diversity, not individual
skill, is what a pool pays for. VIEWS's covariate-ML signal is the orthogonal
ingredient; TOCSIN's distinct value lies on the targets no other model prices
(annual horizons, arbitrary thresholds, termination, coups) and in
auditability — not in month-grain occurrence, where its information is
already in the pool via persistence.

Practical rule this establishes: **when a question has multiple credible
forecasters, the best available number is their equal-weight pool, not the
single best model** — and the site's arena table now reports the pools as
the standing to beat.

## Scoring rules

Brier `(p−o)²` and log score `ln p(outcome)`; calibration in decile bins; the
headline comparison is **paired Brier, challengers vs the engine's stored prior, on the same
questions**. Anti-gaming: only forecasts (and priors) timestamped on or
before a question's `decided_on` date score — once the threshold has crossed,
the book is closed.
