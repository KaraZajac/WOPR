# Data rights and attribution

This repository is original code plus **derived research tables** computed
from third-party conflict datasets. Rights are layered: the code is
[MIT](LICENSE); the derived data in `data/` is **CC BY 4.0**, matching the
upstream UCDP terms, and inherits the attribution requirements below. Raw
sources live only in the gitignored `sources/` directory (regenerable via
`wopr pull`) and are not redistributed here.

| layer | contents | provenance | terms |
|---|---|---|---|
| UCDP-derived tables | `data/tables/`, `data/registry/` (conflicts, dyads, non-state, one-sided), death counts in `data/` | Uppsala Conflict Data Program (UCDP) & PRIO: Armed Conflict Dataset, Dyadic ACD, GED, candidate GED, non-state, one-sided, organized-violence country-year — version pinned in `data/meta.yaml` | **CC BY 4.0**; cite UCDP as below |
| Gleditsch–Ward state list | `data/registry/states.yaml` (system membership spells) | Gleditsch & Ward list of independent states, ksgleditsch.com | free for academic use **with citation** |
| ACLED aggregates | `sources/acled/` only (gitignored; **never redistributed** in this repo, and not used in committed tables) | Armed Conflict Location & Event Data (ACLED), accessed via a registered myACLED account | ACLED Terms & Conditions/EULA: attribution required, no redistribution or resale; see acleddata.com |
| World geometry | `site/src/assets/countries-110m.json` | world-atlas (Natural Earth 110m, via topojson/world-atlas) | **Public domain** (Natural Earth); world-atlas ISC |
| Original contributions | the pipeline/engine/journal code, question files in `questions/`, computed priors and scorecards, documentation | this project | code MIT; data outputs CC BY 4.0 |

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

Research and educational use. Candidate GED events are preliminary UCDP data
that have not completed full quality control; resolutions based on them are
marked provisional in this repository until confirmed by an annual release.
This project is unaffiliated with UCDP, PRIO, or Uppsala University. Forecasts
in `questions/` are personal probability judgments, not predictions of policy
or advice of any kind.
