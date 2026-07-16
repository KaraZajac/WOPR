// Read-only access to the export at ../data/site (JSON, written by
// `wopr export`) plus data/meta.yaml. Cached per build process.

import fs from "node:fs";
import path from "node:path";
import YAML from "yaml";

function findData(start) {
  let dir = path.resolve(start);
  for (let i = 0; i < 6; i++) {
    if (fs.existsSync(path.join(dir, "data", "meta.yaml"))) {
      return path.join(dir, "data");
    }
    dir = path.dirname(dir);
  }
  throw new Error(`data/ directory not found walking up from ${start}`);
}
const DATA = findData(process.cwd());
const cache = new Map();

function load(rel) {
  if (!cache.has(rel)) {
    const text = fs.readFileSync(path.join(DATA, rel), "utf8");
    cache.set(rel, rel.endsWith(".yaml") ? YAML.parse(text) : JSON.parse(text));
  }
  return cache.get(rel);
}

export const meta = () => load("meta.yaml");
export const summary = () => load("site/summary.json");
export const countries = () => load("site/countries.json");
export const mapJoin = () => load("site/map.json");
export const questions = () => load("site/questions.json");
export const backtest = () => load("site/backtest.json");
export function arena() {
  const p = path.join(DATA, "site", "benchmark.json");
  return fs.existsSync(p) ? load("site/benchmark.json") : null;
}

/** Countries sorted by current risk, descending. */
export function countryList() {
  return Object.values(countries()).sort((a, b) => b.p - a.p || a.name.localeCompare(b.name));
}
