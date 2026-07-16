# Deploying the site — wopr.karazajac.io

The site is fully static (Astro, `site/dist/`) and deploys to Cloudflare
Pages exactly like judgment.karazajac.io. One-time setup, ~10 minutes:

## Cloudflare Pages setup

1. Cloudflare dashboard → **Workers & Pages → Create → Pages →
   Connect to Git** → select `KaraZajac/WOPR` (grant access to the private
   repo when prompted).
2. Build settings:
   - **Framework preset:** Astro
   - **Build command:** `npm ci && npm run build`
   - **Build output directory:** `dist`
   - **Root directory:** `site`
3. Environment variables (Production):
   - `PAGES_SITE` = `https://wopr.karazajac.io`
   (astro.config.mjs already defaults to this, so the var is belt-and-
   suspenders; set `PAGES_BASE` only if ever serving under a subpath.)
4. Deploy, then **Custom domains → add `wopr.karazajac.io`** — Cloudflare
   creates the CNAME automatically since karazajac.io is already on
   Cloudflare.

## How updates flow

- Every push to `main` redeploys automatically (Pages watches the repo).
- The monthly refresh workflow (`.github/workflows/refresh.yml`, the 20th)
  commits updated data → that push triggers the redeploy. No manual step.
- The committed `data/site/*.json` are the site's only inputs, so Pages
  never needs Python or the pipeline — just the Astro build.

## Checks after first deploy

- `/` board renders with the current GWI and map.
- `/methods` arena table shows the pools ranked first.
- A country page (e.g. `/country/530/`) renders charts + risk factors.
- Theme toggle persists (Latte/Mocha).
