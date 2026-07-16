# Roadmap

## V1 — make the outside view stronger

- ~~Politically-relevant-dyad exposure~~ **done** (the pair grain):
  G-W minimum distance ≤400km ∪ same-region ∪ P5, 1946–present, 98.2% hit
  coverage, walk-forward backtested. Follow-ups: per-pair GED death sums
  (thresholds beyond activity), candidate-month pair nowcasting, and a pair
  risk layer on the site.
- ~~Trends & timeline pages~~ **done**: /trends (the long peace, per-capita
  battle deaths, deaths by region, coup decline, regime shift, conflict
  survival + how-wars-end) and /timeline (layered conflict timeline with era
  bands). Population added (OWID) for per-capita normalization.
  ~~pre-1989 battle deaths (PRIO)~~ **done** (v3.1 1946–2008, converted from
  legacy .xls via libreoffice, stitched onto GED at 1989 — pre-1989 total
  ~3× the whole post–Cold-War era). ~~Correlates of War~~ **done** (dyadic
  MIDs 1946–2014 + trends chart, formal alliances 1946–2012, CINC v7 through
  2022 on country risk panels; COW→G-W crosswalk unit-tested; COW's missing
  TLS intermediate pinned in wopr/pipeline/cow-ca.pem). ~~MID/alliance protocol candidates~~
  **tested and REJECTED** (`wopr protocol --study pair`: 0/4 beat baseline on
  tune; ever-MID −0.7% on validate). The decomposition matters: cold pairs
  with MID history onset at **30×** the never-MID rate, but Brier cannot see
  rare-event refinement at pair base rates — signal ships as display (pair
  rate() notes). A pair-grain adoption metric (log-loss) may be
  pre-registered for a future vantage era. Next trend ideas: small-multiple country trajectories,
  protest trends, Maddison historical GDP via OWID.
- **Covariate-widened reference classes**: regime type (V-Dem/Polity),
  GDP/capita, ethnic fractionalization — class = "countries like this one",
  not just "countries near this one". Sensitivity across class definitions in
  every prior.
- ~~Rolling sub-annual rates~~ **done** (engine 0.3.0): month-aligned
  windows priced exactly on the monthly substrate; ask/rate route to it
  automatically. Follow-ups: tempo-conditioned buckets (current intensity,
  not just threshold-recency — the Ethiopia-short-window blind spot), a
  rolling walk-forward backtest, pair grain at month grain.
- ~~Bucket nowcasting~~ **done** (0.2.0, promote-only from candidate months);
  ~~tempo conditioning~~ **done at month grain** (0.3.0: arena-verified,
  Brier .0611→.0461); ~~neighbor-at-war~~ **done at month grain** (0.3.0:
  non-active buckets split by ≤400km-neighbor contagion — cold+nbr onsets at
  7× cold; Brier-invisible at month grain, expected to matter at year grain).
  **Horizon-aware class rates: built, ablated, measured worse (+.003) —
  reverted to frozen one-step; machinery retained** (docs/method.md).
  ~~Annual-grain intensity + neighbor~~ **done** (0.4.0: |minor/|war bands +
  country +nbr; additive backtest gains on death-threshold suites, mixed
  cells documented). ~~V-Dem covariate classes~~ **built, backtested,
  rejected** (worse on every country suite — cell fragmentation; capability
  and the regime table retained; docs/method.md). ~~Tune/validate protocol~~
  **built** (`wopr protocol`) — the discipline machine that lets a covariate
  earn in on held-out vantages. ~~Youth conditioning~~ **tested and
  REJECTED** through it (0/4 tune cuts beat baseline; noise-level validate
  edge — recency already captures youth's descriptive lift). ~~Ethnic exclusion + joint covariates~~ **tested and
  REJECTED** (`--study joint`, the FINAL read of the 2007 split: 0/3 beat
  tune baseline; exclusion −1.0% on validate; even young∧excluded — the
  strongest descriptive cell — lost on tune). **The 2007 vantage split is
  retired; future covariate studies must pre-register on a fresh era
  (2026+).** Still open: continuous tempo (needs the fresh era), self-level
  horizon decay curves, ACLED weeklies as a tempo input.
- **Proper hierarchical model** replacing the moment-matched EB (partial
  pooling over region × bucket, fitted once at build time).
- **Conflict-scope priors** (aggregate dyad substrate per conflict id).
- ~~UCDP long tail~~ **done** (0.5.0): termination measure + hazard suite +
  auto-resolution; episode table (validated 99.6% vs Kreutz coding); PA
  registry (context; stale cadence); MIC identified as mediation data and
  parked. ~~Powell–Thyne coups~~ **done** (0.5.0: country-grain `coup`
  measure, +18% skill vs climatology — the method generalizes past UCDP;
  fetched via the Wayback CDX index). Next: termination-outcome questions
  (how, not just whether), conflict-scope termination, coup-success split.
- ~~Benchmark against VIEWS~~ **done** (`wopr benchmark`, data/benchmark.yaml):
  retrospective month-grain arena, VIEWS ahead on aggregate, persistence
  nearly ties it, WOPR's tempo gap priced at ~0.017 Brier. Follow-ups:
  **tempo-conditioned buckets** (now the top engine item — the arena showed
  it costs more than anything else), annual-grain arena once journal
  questions resolve, VIEWS numbers as live challengers when a month-shaped
  question type lands.

## V1 — make the journal richer

- Import Metaculus/GJOpen questions + resolutions for volume while the UCDP
  questions season.
- Time-averaged scoring alongside final-forecast scoring.
- Brier skill decomposition (calibration / resolution / uncertainty).
- `wopr ask` templates: "onset", "escalation to war (≥1000)", "spread to
  neighbor", "termination" question kinds with matched engine specs.

## V2 — the watchfloor

- ~~Early-warning board~~ **done** (the watchfloor): country tempo this year
  (annualized candidate months) vs the trailing-5-year baseline and the base
  rate, ranked by magnitude-weighted surprise, with heating/cooling/onset
  flags and an independent ACLED 8-week direction check (derived flag only,
  no raw ACLED series — Content Usage Terms). `wopr watchfloor`, `/watchfloor`.
  Next: dyad-grain watchfloor, coup/termination tempo, thresholded alerts.
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
