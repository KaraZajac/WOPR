# WOPR

> *"A strange game. The only winning move is to check whether anything
> actually beats the base rate."*

**A conflict-forecasting system: reference-class base rates computed from the
UCDP record, operational questions that resolve themselves from the next data
refresh, and calibration scoring of your forecasts against the prior you
started from.**

WOPR is the forecaster; the analyst audits it and makes it race. Three parts:

1. **The model.** Ask for a probability and get an explicit reference-class
   *ladder* — the unit's own history, its region, the world — conditioned on
   recency and episode age (conflict is sticky: ~0.17 unconditional becomes
   ~0.85 for countries violent last year), with empirical-Bayes shrinkage and
   the class sizes in your face. If the class is thin, you see that. Every
   prediction shows its work; the walk-forward backtest measures its
   calibration on ~280k historical unit-years. No astrology.
2. **The testable record.** Predictions become questions with hard
   UCDP-pinned criteria that resolve mechanically from the next data refresh
   — the model's track record accumulates in git, timestamped, with no human
   in the resolution loop.
3. **The arena.** Challenger forecasts — other models (VIEWS), naive
   baselines, or an analyst override — get logged against the same questions
   and scored head-to-head on identical resolved outcomes: paired Brier,
   challenger vs engine. That's the question the whole system exists to
   answer: does anything out there carry information the base rate doesn't?

## What's here

| | |
|---|---:|
| UCDP GED events (1989–2025, release 26.1) | **417,968** |
| + candidate events (2026, monthly, provisional) | **8,195** |
| State-based conflicts / dyads (1946–2025) | **303 / 697** |
| Non-state dyads · one-sided actors | **1,001 · 378** |
| G-W states with region + system spells | **225** |
| Country-years in the base-rate substrate | **12,703** |

```
wopr/
├── pipeline/          pull (UCDP + G-W) → build (tables, registries) → validate
│                        + acled (aggregates) + site_export (render-ready JSON)
├── engine/            reference-class ladder, recency buckets, EB shrinkage,
│                        walk-forward backtest
└── journal/           question store, auto-resolution, Brier/log/calibration
data/
├── meta.yaml          release + coverage bounds (annual vs candidate)
├── registry/          states, conflicts, dyads, non-state, one-sided (YAML)
├── tables/            country-year, dyad-year, country-month, dyad-month (CSV)
├── backtest.yaml      the engine's own measured reliability
└── site/              JSON exported for the site (`wopr export`)
questions/             the journal: one YAML per question, git-timestamped
site/                  Astro site: world risk map, Global War Index, WWIII panel,
                         country pages, the journal — Catppuccin Latte/Mocha
docs/                  method (read the caveats), data model, roadmap
tests/                 stdlib unittest; `make verify` gates data + journal
```

## The site

`make site-dev` (or `make site` for the static build; needs `npm install` in
`site/` once). A dashboard with the Global War Index (percentile of global
organized-violence deaths), a world map of engine priors, the operationally
defined WWIII panel (P5-war base rates — the long peace, quantified), per-
country pages with walk-forward prior histories, deaths, monthly tempo and
80-year activity strips, the journal, and the engine's reliability curves.
Catppuccin Latte/Mocha with a toggle; every chart has tooltips and a table
view; all SVG is rendered at build time — zero client JS beyond the tooltip
layer and theme switch.

## The loop

```console
$ wopr pull && wopr build        # ~280 MB of UCDP into sources/, tables into data/
$ wopr rate --country Ethiopia --threshold 25
Ethiopia (country 530) — P(sb deaths ≥ 25 in a calendar year)
as of 2026 · bucket: active (history through 2025) · substrate 1989–2025
level     units    yrs   hits    rate       M  posterior
self          1     33     31  0.9394       —          —
region       52    460    379  0.8239     5.4     0.9231
global      181   1112    940  0.8453     5.0      0.927
headline: p = 0.9231  (region posterior, bucket-conditional)

$ wopr ask --pair "Venezuela,Guyana" --year 2027         # model's prediction stored
$ wopr call 2027-001 0.03 --source views                 # challenger number logged
$ wopr resolve                   # grades due questions from the data (provisional
                                 #   on candidate months, confirmed each release)
$ wopr score
engine (prior)      : Brier 0.041  log -0.113  (n=23)
challenger          : Brier 0.058  log -0.171  (n=23)
challenger vs engine: ΔBrier +0.017 on 23 paired questions — the engine held
```

`wopr status`, `wopr list`, `wopr show ID` browse the journal; `--manual`
questions resolve by hand; `wopr resolve --id X --void "reason"` retires a
broken question. Scored forecasts are the last ones made **before** a
question's deciding date — once the threshold crosses, the book is closed
(that applies to stale engine priors too).

## Honesty guarantees

- Every prior ships with its full ladder: class definitions, counts,
  conditioning bucket, shrinkage strength. Sensitivity is visible, not hidden.
- Questions are operational by construction (UCDP measure + scope + threshold
  + window), so resolution is mechanical, and ambiguity dies at ask-time.
- Candidate-based resolutions are marked provisional and re-graded on the
  next annual release; flips are recorded, and the score moves.
- Dyad rates are recurrence rates over UCDP-observed dyads — the engine says
  so out loud. Read [docs/method.md](docs/method.md) before trusting any
  number.

## Setup

Python ≥ 3.11 and PyYAML; nothing else. `pip install -e .` for the `wopr`
entry point (or run `python3 -m wopr …`). `make install-hooks` turns on the
pre-commit gate (`make verify`: data validation + unit tests).

Data terms and required citations: [DATA-RIGHTS.md](DATA-RIGHTS.md). UCDP
annual releases land mid-year; candidate GED lands monthly with ~6 weeks of
lag — `wopr pull && wopr build && wopr resolve` is the maintenance loop.

Optional: with myACLED credentials in the repo-root `.env`
(`ACLED_USERNAME`/`ACLED_PASSWORD`), `wopr acled` pulls ACLED's aggregate
files (country-month political violence, country-year fatalities, weekly
Admin-1 regionals) into `sources/acled/` — tempo signals for the future
watchfloor, not resolution authorities (different ontology than UCDP; see
docs/data-model.md).

*WOPR: the War Operation Plan Response computer from* WarGames *(1983), which
learned about unwinnable games by playing itself. The name will probably
change; the scoring loop is the point.*
