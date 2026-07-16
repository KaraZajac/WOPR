import { defineConfig } from "astro/config";

// Static-output site over data/site/*.json exported by `tocsin export`.
// Deploys to tocsin.karazajac.io (Cloudflare Pages; docs/deploy.md). PAGES_SITE /
// PAGES_BASE remain as overrides for previews — internal links all go
// through url() in src/lib/format.js.
export default defineConfig({
  site: process.env.PAGES_SITE || "https://tocsin.karazajac.io",
  base: process.env.PAGES_BASE || undefined,
});
