# Deploying the site — wopr.karazajac.io (self-hosted)

The site is pure static output: `site/dist/` after a build is the entire
deployable artifact — no server-side runtime, no Python on the web host.

## Build

```sh
git clone https://github.com/KaraZajac/WOPR
cd WOPR/site
npm ci
npm run build          # -> site/dist/
```

`astro.config.mjs` defaults the canonical URL to `https://wopr.karazajac.io`;
set `PAGES_SITE` (and `PAGES_BASE` for a subpath) at build time only if
serving somewhere else.

## Serve

Any static file server works. nginx example:

```nginx
server {
    server_name wopr.karazajac.io;
    root /var/www/wopr;            # rsync of site/dist/
    index index.html;
    location / { try_files $uri $uri/ =404; }
    gzip on;
    gzip_types text/html text/css application/javascript application/json image/svg+xml;
}
```

Deploy step after a build: `rsync -a --delete site/dist/ server:/var/www/wopr/`.

## Staying current

The repo refreshes itself monthly (`.github/workflows/refresh.yml`, the
20th: pull → build → resolve → verify → export → commit). To pick that up,
a cron on the server rebuilds shortly after — e.g. the 21st:

```sh
#!/bin/sh
# /etc/cron.monthly-ish: 0 6 21 * *  wopr-rebuild
cd /opt/WOPR && git pull --ff-only \
  && cd site && npm ci && npm run build \
  && rsync -a --delete dist/ /var/www/wopr/
```

Push-based alternative: a GitHub webhook or Actions job that rsyncs
`site/dist/` to the server on push to main — same artifact either way.

## Checks after first deploy

- `/` board renders with the current GWI and map.
- `/methods` arena table shows the pools ranked first.
- A country page (e.g. `/country/530/`) renders charts + risk factors.
- Theme toggle persists (Latte/Mocha).

## Now that the repo is public

- The Zenodo GitHub integration works: enable the repo at zenodo.org →
  GitHub, then publishing a GitHub Release (attach `dist/wopr-dataset-*.tar.gz`
  from `wopr release`) mints a DOI automatically — no manual upload.
- Anyone can reproduce the site from the committed `data/site/*.json`,
  and the full pipeline from `wopr pull && wopr build` (sources are
  re-fetched; nothing proprietary is in the repo — see DATA-RIGHTS.md).
