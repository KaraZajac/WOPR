# TOCSIN site

Astro static site over `../data/site/*.json` (written by `tocsin export`) and
`../data/meta.yaml`. No client-side framework: charts and the world map are
SVG rendered at build time; the only browser JS is the shared tooltip layer
and the Catppuccin Latte/Mocha theme toggle.

```
npm install
npm run dev        # or: make site-dev from the repo root (re-exports first)
npm run build      # static output in dist/
```

Pages: `/` (Global War Index, world risk map, WWIII panel), `/countries` +
`/country/<gwno>` (ladder, walk-forward prior, deaths, tempo, activity strip),
`/questions` (the journal), `/methods` (engine method + backtest reliability).

Chart conventions follow the dataviz method: categorical slots validated for
CVD in stack order (sb=blue, ns=peach, os=mauve), sequential map ramp is
OKLab-interpolated red (monotone lightness both themes), legends + table
views everywhere, thin marks with surface gaps. When adding a chart, reuse
the components in `src/components/` rather than inventing new marks.
