"""The forecast journal: one YAML file per question under questions/.

A question is operational by construction — its criteria pin a UCDP measure,
scope, threshold, and window, so most questions resolve mechanically from the
next data refresh. The file accumulates the computed base-rate prior, your
forecast history, and eventually the resolution; git history timestamps all
of it.
"""

import datetime
import re

import yaml

from wopr.paths import QUESTIONS

SCOPE_KINDS = ("country", "dyad", "conflict", "actor", "pair")
MEASURES = ("deaths", "events")
TYPES = ("sb", "ns", "os")
P_MIN, P_MAX = 0.001, 0.999


def now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:48] or "question"


def qpath(qid: str, slug: str):
    return QUESTIONS / f"{qid}-{slug}.yaml"


def load_all() -> list[dict]:
    if not QUESTIONS.exists():
        return []
    out = []
    for p in sorted(QUESTIONS.glob("*.yaml")):
        q = yaml.safe_load(p.read_text())
        q["_path"] = p
        out.append(q)
    return out


def load(qid: str) -> dict:
    matches = list(QUESTIONS.glob(f"{qid}-*.yaml")) if QUESTIONS.exists() else []
    if not matches:
        raise SystemExit(f"no question {qid} in {QUESTIONS}")
    q = yaml.safe_load(matches[0].read_text())
    q["_path"] = matches[0]
    return q


def save(q: dict) -> None:
    errors = validate_question(q)
    if errors:
        raise SystemExit("refusing to save invalid question:\n  " + "\n  ".join(errors))
    QUESTIONS.mkdir(exist_ok=True)
    path = q.pop("_path", None) or qpath(q["id"], q["slug"])
    body = {k: v for k, v in q.items() if not k.startswith("_")}
    with open(path, "w") as f:
        yaml.safe_dump(body, f, sort_keys=False, allow_unicode=True, width=100)
    q["_path"] = path


def next_id() -> str:
    year = datetime.date.today().year
    seqs = [
        int(m.group(1))
        for p in (QUESTIONS.glob(f"{year}-*.yaml") if QUESTIONS.exists() else [])
        if (m := re.match(rf"{year}-(\d{{3}})-", p.name))
    ]
    return f"{year}-{max(seqs, default=0) + 1:03d}"


def new_question(title: str, question: str, criteria: dict, method: str = "auto", tags: list | None = None) -> dict:
    return {
        "id": next_id(),
        "slug": slugify(title),
        "title": title,
        "question": question,
        "created": now(),
        "status": "open",
        "tags": tags or [],
        "criteria": criteria,
        "resolution_policy": {"method": method},
        "forecasts": [],
    }


def add_forecast(q: dict, p: float, note: str = "", source: str = "") -> dict:
    """Log a challenger forecast — another model's number, or an analyst
    override. The engine's own prediction lives in `prior`; these compete
    against it when the question resolves."""
    if q["status"] != "open":
        raise SystemExit(f"{q['id']} is {q['status']}; no further forecasts")
    if not (P_MIN <= p <= P_MAX):
        raise SystemExit(f"p must be within [{P_MIN}, {P_MAX}] — no certainties in this house")
    entry = {"t": now(), "p": p}
    if source:
        entry["source"] = source
    if note:
        entry["note"] = note
    q["forecasts"].append(entry)
    return entry


def _is_date(s) -> bool:
    try:
        datetime.date.fromisoformat(str(s))
        return True
    except ValueError:
        return False


def validate_question(q: dict) -> list[str]:
    e = []
    qid = q.get("id", "?")

    def bad(msg):
        e.append(f"{qid}: {msg}")

    if not re.match(r"^\d{4}-\d{3}$", str(q.get("id", ""))):
        bad("id must look like 2026-001")
    for key in ("slug", "title", "question", "created"):
        if not q.get(key):
            bad(f"missing {key}")
    if q.get("status") not in ("open", "resolved", "void"):
        bad(f"bad status {q.get('status')!r}")
    c = q.get("criteria") or {}
    scope = c.get("scope") or {}
    if scope.get("kind") not in SCOPE_KINDS:
        bad(f"scope.kind must be one of {SCOPE_KINDS}")
    if not isinstance(scope.get("id"), int):
        bad("scope.id must be an int (UCDP/G-W id)")
    if scope.get("kind") == "pair" and not (
        isinstance(scope.get("a"), int) and isinstance(scope.get("b"), int)
    ):
        bad("pair scope needs gwno ints a and b")
    if c.get("measure") not in MEASURES:
        bad(f"measure must be one of {MEASURES}")
    if not isinstance(c.get("threshold"), int) or c.get("threshold", 0) < 1:
        bad("threshold must be a positive int")
    if not set(c.get("types") or []) <= set(TYPES) or not c.get("types"):
        bad(f"types must be a nonempty subset of {TYPES}")
    w = c.get("window") or {}
    if not (_is_date(w.get("start")) and _is_date(w.get("end"))):
        bad("window.start/end must be ISO dates")
    elif str(w["end"]) < str(w["start"]):
        bad("window ends before it starts")
    if (q.get("resolution_policy") or {}).get("method") not in ("auto", "manual"):
        bad("resolution_policy.method must be auto|manual")
    prior = q.get("prior")
    if prior is not None and not (0.0 < prior.get("p", -1) < 1.0):
        bad("prior.p out of (0,1)")
    last = ""
    for fc in q.get("forecasts", []):
        if not (P_MIN <= fc.get("p", -1) <= P_MAX):
            bad(f"forecast p {fc.get('p')} out of range")
        if fc.get("t", "") < last:
            bad("forecast timestamps out of order")
        last = fc.get("t", "")
    if q.get("status") == "resolved":
        r = q.get("resolution") or {}
        if r.get("outcome") not in ("yes", "no"):
            bad("resolved question needs resolution.outcome yes|no")
        if not _is_date(r.get("decided_on")):
            bad("resolution.decided_on must be a date")
    if q.get("status") == "void" and not (q.get("resolution") or {}).get("note"):
        bad("void question needs resolution.note explaining why")
    return e
