# Data rights and attribution

This repository is original code plus **derived research tables** computed
from third-party conflict datasets. Rights are layered: the code is
[MIT](LICENSE); the derived data in `data/` is **CC BY 4.0**, matching the
upstream UCDP terms, and inherits the attribution requirements below. Raw
sources live only in the gitignored `sources/` directory (regenerable via
`tocsin pull`) and are not redistributed here.

| layer | contents | provenance | terms (verified 2026-07-16) |
|---|---|---|---|
| UCDP-derived tables | `data/tables/`, `data/registry/` (conflicts, dyads, non-state, one-sided), death counts in `data/` | Uppsala Conflict Data Program (UCDP) & PRIO: Armed Conflict Dataset, Dyadic ACD, GED, candidate GED, non-state, one-sided, organized-violence country-year — version pinned in `data/meta.yaml` | **CC BY 4.0** — UCDP FAQ: "Except where otherwise noted, content on this site is licensed under a Creative Commons Attribution 4.0 International license." Redistribution and commercial use permitted **with attribution** (cite as below) |
| Gleditsch–Ward state list | `data/registry/states.yaml` (system membership spells) | Gleditsch & Ward list of independent states v7 (`ksgmdw.txt`), ksgleditsch.com | **no formal license posted** — openly distributed academic data; cite Gleditsch & Ward (1999) by scholarly convention |
| G-W minimum distances | `data/tables/pair-year.csv` (`km` column and the proximity rule) | Gleditsch & Ward minimum-distance data v0.97 (`smallmdd.csv`), ksgleditsch.com | same as above; cite Gleditsch & Ward (2001), *JPR* 38(6): 739–758 |
| ACLED aggregates | `sources/acled/` only (gitignored; **never redistributed** in this repo, and not used in committed tables or on the site) | Armed Conflict Location & Event Data (ACLED), accessed via a registered myACLED account (Open tier) | Proprietary, governed by three instruments accepted at registration: **EULA + Content Usage Terms + Attribution Policy**. License grant is royalty-free, non-exclusive, non-transferable, non-sublicensable, **non-commercial**; commercial entities require a corporate license; published materials must be **transformative** ("not sufficient for Licensed Content to simply be supplemented, appended, excerpted, reorganized, or made available through Licensee's own dashboard"); AI/ML/LLM use restricted; attribution mandatory |
| World geometry | `site/src/assets/countries-110m.json` | world-atlas (Natural Earth 110m, via topojson/world-atlas) | **Public domain** (Natural Earth: "in the public domain… No permission is needed"); world-atlas package ISC. Credited voluntarily |
| VIEWS forecasts | `sources/views/` (gitignored) and aggregate scores in `data/benchmark.yaml` | Uppsala VIEWS open API (api.viewsforecasting.org), fatalities002 runs | openly published forecasts; cite Hegre et al. (2019) *JPR* 56(2) and the VIEWS platform; only derived benchmark scores are committed |
| Regime classifications | `data/tables/regime.csv` | V-Dem "Regimes of the World" (Lührmann, Tannenberg & Lindberg 2018), via Our World in Data's maintained extract | OWID: **CC BY**; cite V-Dem (Coppedge et al.) and OWID as processor |
| Coup d'état records | `data/tables/coup.csv` (`sources/pt-coups.tsv` gitignored) | Powell & Thyne coup dataset, uky.edu (fetched via the Internet Archive Wayback Machine) | freely published academic data; cite Powell & Thyne (2011) *JPR* 48(2): 249–259 |
| Population | `data/tables/population.csv` | Our World in Data population series (UN WPP / HYDE composite) | OWID: **CC BY**; used for per-capita normalization on the trends page |
| Structural covariates | `data/tables/covariates.csv` (WDI columns) | World Bank Open Data / WDI (income, age structure, urbanization, infant mortality — World Bank/UN-compiled; **inflation** is IMF IFS, redistributed by the Bank under its open terms) | **CC BY 4.0** (World Bank Terms of Use for Datasets); attribute "The World Bank: WDI". Third-party series (IMF inflation) carry the provider's terms; kept as covariate context |
| Ethnic exclusion | `data/tables/covariates.csv` (`excluded_share`) | Ethnic Power Relations (EPR-2021) core dataset, ETH Zürich / ICR | freely published academic data; cite Vogt et al. (2015) *JCR* 59(7) and Cederman, Wimmer & Min (2010) |
| Militarized disputes, capabilities, alliances | `data/tables/mids.csv`, `data/tables/alliances.csv`, `covariates.csv` (`cinc`) | Correlates of War project: Dyadic MID 4.03, National Material Capabilities v7, Formal Alliances v4.1 (COW codes crosswalked to G-W year-aware) | **no formal license** — freely downloadable academic data; COW asks that users cite the article of record for each dataset (below) |
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
- Lacina, Bethany & Nils Petter Gleditsch (2005) Monitoring Trends in Global
  Combat: A New Dataset of Battle Deaths. *European Journal of Population*
  21(2–3): 145–166. (PRIO Battle Deaths Dataset v3.1, extending state-based
  battle deaths to 1946; `data/tables/battle-deaths-history.csv`, freely
  published academic data)
- Eck, Kristine & Lisa Hultman (2007) One-Sided Violence Against Civilians in
  War. *Journal of Peace Research* 44(2): 233–246.
- Kreutz, Joakim (2010) How and When Armed Conflicts End: Introducing the
  UCDP Conflict Termination Dataset. *Journal of Peace Research* 47(2):
  243–250.
- Pettersson, Therése; Stina Högbladh & Magnus Öberg (2019) Organized
  violence, 1989–2018 and peace agreements. *Journal of Peace Research*
  56(4): 589–603. (UCDP Peace Agreement Dataset)

**Gleditsch–Ward:** Gleditsch, Kristian S. & Michael D. Ward (1999) Interstate
System Membership: A Revised List of the Independent States since 1816.
*International Interactions* 25(4): 393–413.

**Correlates of War (articles of record):**

- Palmer, Glenn, et al. (2022) The MID5 Dataset, 2011–2014: Procedures, coding
  rules, and description. *Conflict Management and Peace Science* 39(4):
  470–482. (MID)
- Maoz, Zeev, Paul L. Johnson, Jasper Kaplan, Fiona Ogunkoya & Aaron Shreve
  (2019) The Dyadic Militarized Interstate Disputes (MIDs) Dataset Version
  3.0. *Journal of Conflict Resolution* 63(3): 811–835. (dyadic MID)
- Singer, J. David, Stuart Bremer & John Stuckey (1972) Capability
  Distribution, Uncertainty, and Major Power War, 1820–1965. In Bruce Russett
  (ed.) *Peace, War, and Numbers*. Beverly Hills: Sage, 19–48. (NMC/CINC)
- Gibler, Douglas M. (2009) *International Military Alliances, 1648–2008*.
  Washington DC: CQ Press. (Formal Alliances)

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
