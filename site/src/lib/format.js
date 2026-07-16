// Display helpers.

export const pct = (x, digits = 0) =>
  x == null ? "—" : (x * 100).toFixed(digits) + "%";

export const pct1 = (x) => pct(x, 1);

export const num = (n) => (n == null ? "—" : n.toLocaleString("en-US"));

export function fmtDate(iso) {
  if (!iso) return null;
  const [y, m, d] = String(iso).split("-").map(Number);
  if (!y || !m || !d) return String(iso);
  return new Date(Date.UTC(y, m - 1, d)).toLocaleDateString("en-US", {
    year: "numeric", month: "short", day: "numeric", timeZone: "UTC",
  });
}

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
export function fmtMonth(ym) {
  const [y, m] = String(ym).split("-").map(Number);
  return `${MONTHS[m - 1]} ${y}`;
}

export function ordinal(n) {
  const s = ["th", "st", "nd", "rd"], v = n % 100;
  return n + (s[(v - 20) % 10] || s[v] || s[0]);
}

/** Base-aware internal URL. */
export const url = (p) => import.meta.env.BASE_URL.replace(/\/$/, "") + p;
