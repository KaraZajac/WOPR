import { defineConfig } from "astro/config";

// Static-output site over data/site/*.json exported by `wopr export`.
// The project name (and so the final host) may still change; PAGES_SITE /
// PAGES_BASE override for whatever it deploys as — internal links all go
// through url() in src/lib/format.js.
export default defineConfig({
  site: process.env.PAGES_SITE || "https://wopr.karazajac.io",
  base: process.env.PAGES_BASE || undefined,
});
