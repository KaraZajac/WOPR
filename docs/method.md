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
  last year, banded by the run of consecutive hit-years (episode age). The
  bands are worth ~35 points: fresh dyad flares continue ≈53%, decade-old
  wars ≈88% (walk-forward, dyad grain).
- `recent` — last met 2–3 years ago
- `dormant` — 4–10 years ago
- `cold` — 11+ years ago, or never within the substrate

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
2026" — are priced by the rolling engine (`wopr/engine/rolling.py`) instead
of the calendar-year approximation: P(≥T deaths within the W months from
m₀), estimated over class member window-starts on the monthly substrate
(1989–). The bucket machinery ports intact: a unit's status entering month m
is its trailing-12-month record, age bands count consecutive trailing-hit
months (÷12 → the annual bands), and the recency cutoffs sit 12 months under
the annual ones because trailing windows lag activity by up to a year — with
that shift, January-start buckets provably equal the annual engine's (tested).
Candidate months feed the target's bucket naturally (noted as provisional).

Caveats: window-starts overlap, so class counts are not independent — rates
and calibration read fine, but shrinkage/floors modestly overstate certainty.
Buckets still condition on threshold-recency, not current intensity: a
country at full war tempo gets its whole-history class rate for short
windows (Ethiopia, 6-month, reads ~0.63 despite current tempo making it
near-certain) — tempo conditioning is the next covariate. Country and dyad
grains only; pairs stay annual.

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

`wopr backtest` replays the engine over every observable unit-year using only
prior data (~47k pseudo-forecasts; results in `data/backtest.yaml`). As of
UCDP 26.1 with episode-age buckets (engine 0.2.0): country-grain priors are
well calibrated end to end (sb≥25 skill +70%; acd-active +65%); dyad-grain
skill +60% with the former pooled-active defect largely repaired (the 70–80%
bin was 10 points hot under 4-bucket conditioning, now 4; 80–90% from 5.5 to
2.7). **Residual bias:** all active bands still run ~3 points optimistic at
dyad grain, and fresh onsets (`active-1`) are the least predictable class
(country sb: predicted .65, observed .56) — when your question sits in
`active-1`, treat the prior as soft and lean on your inside view.

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

## Scoring rules

Brier `(p−o)²` and log score `ln p(outcome)`; calibration in decile bins; the
headline comparison is **paired Brier, you vs the stored prior, on the same
questions**. Anti-gaming: only forecasts (and priors) timestamped on or
before a question's `decided_on` date score — once the threshold has crossed,
the book is closed.
