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

Conflict is sticky: the unconditional global rate of a ≥25-death country-year
is ~0.17, but ~0.85 for countries that had one *last year*. Every ladder level
is therefore conditioned on the target's **bucket** — years since the measure
was last met, evaluated as of the forecast year:

- `active` — met last year
- `recent` — 2–3 years ago
- `dormant` — 4–10 years ago
- `cold` — 11+ years ago, or never within the substrate

Class-years are counted only when they entered the same bucket the target is
in now. The first substrate year is skipped (no observable history), and
"never" is left-censored: a country quiet since 1989 may not truly be `cold`
in the long-run sense.

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
