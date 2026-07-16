# WOPR

> *"A strange game. The only winning move is to check whether your inside
> view actually beats the base rate."*

**A conflict-forecasting system: reference-class base rates computed from the
UCDP record, operational questions that resolve themselves from the next data
refresh, and calibration scoring of your forecasts against the prior you
started from.**

Most forecasting tools are a journal (log probabilities, get Brier scores) or
a model (spit out risk numbers). WOPR is the seam between them:

1. **The outside view.** Ask for a base rate and get an explicit
   reference-class *ladder* — the unit's own history, its region, the world —
   every level conditioned on recency (conflict is sticky: ~0.17 unconditional
   becomes ~0.85 for countries violent last year), with empirical-Bayes
   shrinkage and the class sizes in your face. If the class is thin, you see
   that. No astrology.
2. **The inside view.** Turn the rate into a question with hard UCDP-pinned
   criteria, store the prior, then log your adjusted forecast and your
   reasoning.
3. **The bridge.** Questions auto-resolve from the UCDP annual + candidate
   event feeds; scoring pairs *your* Brier against the *prior's* Brier on the
   same questions. After enough resolutions you learn the one thing almost no
   forecaster ever measures: whether your clever adjustments add information
   or noise.

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
├── engine/            reference-class ladder, recency buckets, EB shrinkage
└── journal/           question store, auto-resolution, Brier/log/calibration
data/
├── meta.yaml          release + coverage bounds (annual vs candidate)
├── registry/          states, conflicts, dyads, non-state, one-sided (YAML)
└── tables/            country-year, dyad-year, country-month, dyad-month (CSV)
questions/             the journal: one YAML per question, git-timestamped
docs/                  method (read the caveats), data model, roadmap
tests/                 stdlib unittest; `make verify` gates data + journal
```

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

$ wopr ask --dyad "Eritrea - Ethiopia" --year 2027       # prior computed + stored
$ wopr call 2027-001 0.03 --note "border rhetoric worse than the base rate implies"
$ wopr resolve                   # grades due questions from the data (provisional
                                 #   on candidate months, confirmed each release)
$ wopr score
you             : Brier 0.041  log -0.113  (n=23)
you vs prior    : ΔBrier -0.019 on 23 paired questions (15 you / 7 prior) — you BEAT the base rate
```

`wopr status`, `wopr list`, `wopr show ID` browse the journal; `--manual`
questions resolve by hand; `wopr resolve --id X --void "reason"` retires a
broken question. Scored forecasts are the last ones made **before** a
question's deciding date — once the threshold crosses, the book is closed
(that applies to stale priors too).

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

*WOPR: the War Operation Plan Response computer from* WarGames *(1983), which
learned about unwinnable games by playing itself. The name will probably
change; the scoring loop is the point.*
