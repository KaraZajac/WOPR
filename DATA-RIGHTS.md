# Data rights and attribution

This repository is original code plus **derived research tables** computed
from third-party conflict datasets. Rights are layered: the code is
[MIT](LICENSE); the derived data in `data/` is **CC BY 4.0**, matching the
upstream UCDP terms, and inherits the attribution requirements below. Raw
sources live only in the gitignored `sources/` directory (regenerable via
`wopr pull`) and are not redistributed here.

| layer | contents | provenance | terms (verified 2026-07-16) |
|---|---|---|---|
| UCDP-derived tables | `data/tables/`, `data/registry/` (conflicts, dyads, non-state, one-sided), death counts in `data/` | Uppsala Conflict Data Program (UCDP) & PRIO: Armed Conflict Dataset, Dyadic ACD, GED, candidate GED, non-state, one-sided, organized-violence country-year — version pinned in `data/meta.yaml` | **CC BY 4.0** — UCDP FAQ: "Except where otherwise noted, content on this site is licensed under a Creative Commons Attribution 4.0 International license." Redistribution and commercial use permitted **with attribution** (cite as below) |
| Gleditsch–Ward state list | `data/registry/states.yaml` (system membership spells) | Gleditsch & Ward list of independent states v7 (`ksgmdw.txt`), ksgleditsch.com | **no formal license posted** — openly distributed academic data; cite Gleditsch & Ward (1999) by scholarly convention |
| ACLED aggregates | `sources/acled/` only (gitignored; **never redistributed** in this repo, and not used in committed tables or on the site) | Armed Conflict Location & Event Data (ACLED), accessed via a registered myACLED account (Open tier) | Proprietary, governed by three instruments accepted at registration: **EULA + Content Usage Terms + Attribution Policy**. License grant is royalty-free, non-exclusive, non-transferable, non-sublicensable, **non-commercial**; commercial entities require a corporate license; published materials must be **transformative** ("not sufficient for Licensed Content to simply be supplemented, appended, excerpted, reorganized, or made available through Licensee's own dashboard"); AI/ML/LLM use restricted; attribution mandatory |
| World geometry | `site/src/assets/countries-110m.json` | world-atlas (Natural Earth 110m, via topojson/world-atlas) | **Public domain** (Natural Earth: "in the public domain… No permission is needed"); world-atlas package ISC. Credited voluntarily |
| Original contributions | the pipeline/engine/journal code, question files in `questions/`, computed priors and scorecards, documentation | this project | code MIT; data outputs CC BY 4.0 (attribution chains back to UCDP) |

**Required citations (UCDP):**

- Davies, Engström, Pettersson & Öberg, the UCDP version 26.1 annual update
  article, *Journal of Peace Research* (2026), and UCDP codebooks for the
  individual datasets.
- Gleditsch, Nils Petter, Peter Wallensteen, Mikael Eriksson, Margareta
  Sollenberg & Håvard Strand (2002) Armed Conflict 1946–2001: A New Dataset.
  *Journal of Peace Research* 39(5): 615–637. (UCDP/PRIO Armed Conflict Dataset)
- Sundberg, Ralph & Erik Melander (2013) Introducing the UCDP Georeferenced
  Event Dataset. *Journal of Peace Research* 50(4): 523–532. (GED)
- Sundberg, Ralph, Kristine Eck & Joakim Kreutz (2012) Introducing the UCDP
  Non-State Conflict Dataset. *Journal of Peace Research* 49(2): 351–362.
- Eck, Kristine & Lisa Hultman (2007) One-Sided Violence Against Civilians in
  War. *Journal of Peace Research* 44(2): 233–246.

**Gleditsch–Ward:** Gleditsch, Kristian S. & Michael D. Ward (1999) Interstate
System Membership: A Revised List of the Independent States since 1816.
*International Interactions* 25(4): 393–413.

**ACLED (if its data informs any published output):** Raleigh, Clionadh,
Andrew Linke, Håvard Hegre & Joakim Karlsen (2010) Introducing ACLED: An
Armed Conflict Location and Event Data Project. *Journal of Peace Research*
47(5): 651–660, plus ACLED's current attribution policy.

**Citing this project:** see [CITATION.cff](CITATION.cff).

**ACLED practical constraints for this project:** the site and committed
tables must never carry raw or lightly-reworked ACLED series — only genuinely
transformative outputs (e.g., divergence-from-baseline signals) with
attribution, per the Content Usage Terms. If this project's use ever counts
as use by a commercial entity, ACLED's EULA requires a corporate license
first — resolve that with ACLED before any such use.

Research and educational use. Candidate GED events are preliminary UCDP data
that have not completed full quality control; resolutions based on them are
marked provisional in this repository until confirmed by an annual release.
This project is unaffiliated with UCDP, PRIO, or Uppsala University. Forecasts
in `questions/` are personal probability judgments, not predictions of policy
or advice of any kind.
