# Roadmap

## V1 — make the outside view stronger

- **Politically-relevant-dyad exposure** (COW contiguity + major powers) so
  dyad questions about *never-conflict* pairs get a real denominator instead
  of "no history".
- **Covariate-widened reference classes**: regime type (V-Dem/Polity),
  GDP/capita, ethnic fractionalization — class = "countries like this one",
  not just "countries near this one". Sensitivity across class definitions in
  every prior.
- **Rolling sub-annual rates** from the month tables (P(threshold in next 12
  months) computed from rolling windows rather than calendar-year
  approximation).
- **Proper hierarchical model** replacing the moment-matched EB (partial
  pooling over region × bucket, fitted once at build time).
- **Conflict-scope priors** (aggregate dyad substrate per conflict id).
- Benchmark the engine against **VIEWS** predictions where questions overlap.

## V1 — make the journal richer

- Import Metaculus/GJOpen questions + resolutions for volume while the UCDP
  questions season.
- Time-averaged scoring alongside final-forecast scoring.
- Brier skill decomposition (calibration / resolution / uncertainty).
- `wopr ask` templates: "onset", "escalation to war (≥1000)", "spread to
  neighbor", "termination" question kinds with matched engine specs.

## V2 — the watchfloor

- **Early-warning board**: dyads/countries whose current-month tempo (from
  the candidate feed) diverges hardest from their bucket-conditional base
  rate — "heating up faster than history says it should".
- ACLED as a second resolution authority (requires registered API key;
  operational thresholds, protest/riot event classes UCDP doesn't cover).
- Static site (Astro, like JUDGMENT): browsable questions, priors, reliability
  diagram, public timestamped forecasts.
- Monthly cron: `wopr pull && wopr build && wopr resolve && wopr score`.
