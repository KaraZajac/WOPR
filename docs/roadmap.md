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
- **Bucket nowcasting**: use candidate months (and ACLED weeklies) to update
  a unit's recency bucket for the current partial year, instead of taking
  status at the annual data edge.
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
  the UCDP candidate feed + ACLED weekly Admin-1 aggregates, already pulled
  by `wopr acled`) diverges hardest from their bucket-conditional base rate —
  "heating up faster than history says it should".
- ACLED event-level API as a second resolution authority (protest/riot
  classes UCDP doesn't cover). **Blocked on access level**: the account's
  automatic *Open* myACLED tier covers aggregates only; event-level needs an
  upgrade/trial from ACLED's Access Team ("Request further access" in the
  portal, or licensing@). The client (`acled.api_read`) is already wired.
- ~~Static site~~ **done** (site/): board with the Global War Index, world
  risk map, WWIII panel, country pages with walk-forward priors, journal,
  reliability curves — Catppuccin Latte/Mocha. Next for the site: deploy
  (pick a host once the name settles), a dyads index page, and the
  early-warning board when the tempo-divergence metric lands.
- ~~Monthly cron~~ **done** (.github/workflows/refresh.yml): pull → build →
  resolve → verify → score/backtest/site-export → commit, on the 20th.
