"""wopr — the command line for the whole loop.

    wopr pull                          fetch UCDP sources
    wopr build                         sources -> data/ tables + registries
    wopr verify                        validation gate (data + journal + math)
    wopr rate --country Ethiopia       ad-hoc base rate (the outside view)
    wopr ask --country Ethiopia --year 2026 --threshold 25
                                       create a question; prior computed + stored
    wopr call 2026-001 0.45 --note "…" log your forecast (the inside view)
    wopr resolve                       grade due questions from the data
    wopr score                         Brier / log / calibration / you-vs-prior
    wopr list | show ID | status       browse the journal
"""

import argparse
import datetime
import sys

import yaml

import wopr
from wopr.engine import baserate
from wopr.journal import resolve as resolver
from wopr.journal import score as scoring
from wopr.journal import store
from wopr.paths import DATA, REGISTRY

TYPE_WORDS = {"sb": "state-based", "ns": "non-state", "os": "one-sided"}


def _registry(name: str) -> list[dict]:
    path = REGISTRY / f"{name}.yaml"
    if not path.exists():
        raise SystemExit(f"{path} missing — run `wopr build` first")
    return yaml.safe_load(path.read_text())


def find_unit(kind: str, token: str) -> tuple[int, str, list[str]]:
    """Resolve a name or id to (id, display name, default types)."""
    books = {
        "country": [("states", ["sb"])],
        "dyad": [("dyads", ["sb"]), ("nonstate", ["ns"])],
        "conflict": [("conflicts", ["sb"])],
        "actor": [("onesided", ["os"])],
    }[kind]
    key = "gwno" if kind == "country" else "id"
    for book, types in books:
        entries = _registry(book)
        if token.isdigit():
            hit = next((e for e in entries if e[key] == int(token)), None)
            if hit:
                return hit[key], hit["name"], types
            continue
        t = token.lower()
        exact = [e for e in entries if e["name"].lower() == t or e.get("abbrev", "").lower() == t]
        sub = exact or [e for e in entries if t in e["name"].lower()]
        if len(sub) == 1:
            return sub[0][key], sub[0]["name"], types
        if len(sub) > 1:
            names = ", ".join(f"{e['name']} ({e[key]})" for e in sub[:8])
            raise SystemExit(f"ambiguous {kind} {token!r}: {names}")
    raise SystemExit(f"no {kind} matching {token!r}")


def parse_window(args) -> tuple[str, str, str]:
    if args.year:
        return f"{args.year}-01-01", f"{args.year}-12-31", str(args.year)
    if args.window:
        start, _, end = args.window.partition(":")
        datetime.date.fromisoformat(start), datetime.date.fromisoformat(end)
        return start, end, f"{start}..{end}"
    raise SystemExit("give a window: --year 2026 or --window 2026-07-01:2027-06-30")


def scope_from_args(args) -> tuple[dict, list[str]]:
    picks = [(k, getattr(args, k)) for k in ("country", "dyad", "conflict", "actor") if getattr(args, k)]
    if len(picks) != 1:
        raise SystemExit("give exactly one of --country / --dyad / --conflict / --actor")
    kind, token = picks[0]
    uid, name, types = find_unit(kind, token)
    return {"kind": kind, "id": uid, "name": name}, types


def engine_prior(criteria: dict) -> dict | None:
    scope, types = criteria["scope"], criteria["types"]
    if criteria["measure"] != "deaths" or scope["kind"] not in ("country", "dyad"):
        return None
    if scope["kind"] == "dyad" and types != ["sb"]:
        return None
    sub = baserate.load_substrate()
    if scope["id"] not in sub[scope["kind"]]:
        return None  # e.g. non-state dyad: no year substrate at this grain yet
    as_of = int(str(criteria["window"]["start"])[:4])
    spec = baserate.Spec(scope["kind"], scope["id"], "deaths", tuple(types), criteria["threshold"], as_of)
    result = baserate.rate(spec, sub)
    result["unit_name"] = scope["name"]
    return {
        "p": result["p"],
        "computed": store.now(),
        "engine": wopr.__version__,
        "detail": result,
    }


def synthesize_question(criteria: dict) -> str:
    c = criteria
    what = "battle-related deaths" if c["types"] != ["os"] else "civilian fatalities"
    if c["measure"] == "events":
        what = "violent events"
    kinds = "/".join(TYPE_WORDS[t] for t in c["types"])
    scope = c["scope"]
    where = {
        "country": f"in {scope['name']}",
        "dyad": f"in the dyad {scope['name']}",
        "conflict": f"in the conflict {scope['name']}",
        "actor": f"by {scope['name']}",
    }[scope["kind"]]
    w = c["window"]
    return (
        f"Will UCDP record ≥{c['threshold']} {what} (best estimate, {kinds}) "
        f"{where} between {w['start']} and {w['end']} inclusive?"
    )


# ---------------------------------------------------------------- commands


def cmd_rate(args) -> None:
    scope, default_types = scope_from_args(args)
    if scope["kind"] not in ("country", "dyad"):
        raise SystemExit("rate supports --country and --dyad scopes (v0)")
    types = args.types.split(",") if args.types else default_types
    sub = baserate.load_substrate()
    spec = baserate.Spec(
        scope["kind"], scope["id"], args.measure, tuple(types), args.threshold, args.as_of or 0
    )
    result = baserate.rate(spec, sub)
    result["unit_name"] = scope["name"]
    print(baserate.render(result))


def cmd_ask(args) -> None:
    scope, default_types = scope_from_args(args)
    types = args.types.split(",") if args.types else default_types
    start, end, label = parse_window(args)
    criteria = {
        "scope": scope,
        "types": types,
        "measure": args.measure,
        "threshold": args.threshold,
        "window": {"start": start, "end": end},
    }
    title = args.title or f"{scope['name']}: {'/'.join(types)} {args.measure} ≥{args.threshold} in {label}"
    q = store.new_question(
        title,
        args.question or synthesize_question(criteria),
        criteria,
        method="manual" if args.manual else "auto",
        tags=args.tag,
    )
    prior = None if args.no_prior else engine_prior(criteria)
    if prior:
        q["prior"] = prior
    elif args.prior is not None:
        q["prior"] = {"p": args.prior, "computed": store.now(), "engine": "manual", "note": args.prior_note}
    else:
        print("note: no engine prior for this criteria shape — set one with --prior")
    store.save(q)
    print(f"created {q['id']}  {q['_path'].name}")
    print(f"  {q['question']}")
    if start < str(datetime.date.today()):
        print("  note: window already underway — forecasts score only until the threshold crosses")
    if prior:
        print()
        print(baserate.render(prior["detail"]))
    print()
    print(f"log your forecast:  wopr call {q['id']} <p> --note '…'")


def cmd_call(args) -> None:
    q = store.load(args.id)
    fc = store.add_forecast(q, args.p, args.note or "")
    store.save(q)
    prior_p = (q.get("prior") or {}).get("p")
    drift = f"  (prior {prior_p}, you {args.p:+.3f} vs it)" if prior_p is not None else ""
    print(f"{q['id']} ← p={fc['p']} at {fc['t']}{drift}")


def cmd_resolve(args) -> None:
    if args.id and (args.outcome or args.void):
        q = store.load(args.id)
        if q["status"] != "open":
            raise SystemExit(f"{q['id']} is already {q['status']}")
        if args.void:
            q["status"] = "void"
            q["resolution"] = {"outcome": "void", "note": args.void, "resolved": store.now(), "method": "manual"}
        else:
            q["status"] = "resolved"
            q["resolution"] = {
                "outcome": args.outcome,
                "decided_on": args.decided_on or str(datetime.date.today()),
                "resolved": store.now(),
                "method": "manual",
                "provisional": False,
                "note": args.note or "",
            }
        store.save(q)
        print(f"{q['id']} → {q['resolution']['outcome']}")
        return
    questions = [store.load(args.id)] if args.id else store.load_all()
    results = resolver.run(questions, dry_run=args.dry_run)
    if not results:
        print("no auto-resolvable questions")
        return
    meta = resolver.load_meta()
    for q, res, action in results:
        if action == "pending":
            print(f"{q['id']}  pending — window ends {q['criteria']['window']['end']}, data through {meta['through']}")
            continue
        flag = " (provisional)" if res and res.get("provisional") else ""
        print(f"{q['id']}  {action}: {res['outcome']}{flag}  [{res['basis']['total']} {q['criteria']['measure']}]")
        if not args.dry_run and action != "still-provisional":
            store.save(q)


def cmd_score(args) -> None:
    rows = scoring.question_rows(store.load_all())
    agg = scoring.aggregate(rows)
    print(scoring.render(rows, agg))
    if args.write:
        out = {"aggregate": agg, "calibration": scoring.calibration(rows), "questions": rows}
        with open(DATA / "scorecard.yaml", "w") as f:
            yaml.safe_dump(out, f, sort_keys=False, allow_unicode=True)
        print(f"\nwrote {DATA / 'scorecard.yaml'}")


def cmd_list(_args) -> None:
    questions = store.load_all()
    if not questions:
        print("journal is empty — create a question with `wopr ask`")
        return
    for q in questions:
        w = q["criteria"]["window"]
        prior = (q.get("prior") or {}).get("p", "—")
        last = q["forecasts"][-1]["p"] if q["forecasts"] else "—"
        res = q.get("resolution") or {}
        state = {"open": "open", "void": "VOID"}.get(q["status"], res.get("outcome", "?").upper())
        state += "*" if res.get("provisional") else ""
        print(f"{q['id']}  {state:<6} {w['start']}..{w['end']}  prior={prior:<7} you={last:<7} {q['title'][:52]}")


def cmd_show(args) -> None:
    q = store.load(args.id)
    body = {k: v for k, v in q.items() if not k.startswith("_") and k != "prior"}
    print(yaml.safe_dump(body, sort_keys=False, allow_unicode=True, width=100).rstrip())
    if q.get("prior"):
        print()
        detail = q["prior"].get("detail")
        print(baserate.render(detail) if detail else f"prior: {q['prior']['p']} ({q['prior'].get('engine')})")


def cmd_status(_args) -> None:
    questions = store.load_all()
    meta = DATA / "meta.yaml"
    if meta.exists():
        m = yaml.safe_load(meta.read_text())
        print(
            f"data: UCDP {m['ucdp_release']} annual through {m['annual_coverage_end']}, "
            f"candidate through {m['data_through']}"
        )
    open_qs = [q for q in questions if q["status"] == "open"]
    provisional = [q for q in questions if (q.get("resolution") or {}).get("provisional")]
    unforecast = [q for q in open_qs if not q["forecasts"]]
    print(f"questions: {len(questions)} total, {len(open_qs)} open, {len(provisional)} provisional")
    for q in open_qs:
        w = q["criteria"]["window"]
        nag = "  ← no forecast logged yet" if q in unforecast else ""
        print(f"  {q['id']}  ends {w['end']}  {q['title'][:56]}{nag}")
    for q in provisional:
        print(f"  {q['id']}  provisional {q['resolution']['outcome']} — confirms on next annual release")


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="wopr", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--version", action="version", version=f"wopr {wopr.__version__}")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("pull", help="download UCDP sources").add_argument("--force", action="store_true")
    sub.add_parser("build", help="build data/ from sources/")
    sub.add_parser("verify", help="run the validation gate")

    def scope_flags(p):
        p.add_argument("--country")
        p.add_argument("--dyad")
        p.add_argument("--conflict")
        p.add_argument("--actor")
        p.add_argument("--types", help="comma subset of sb,ns,os")
        p.add_argument("--threshold", type=int, default=25)

    p = sub.add_parser("rate", help="ad-hoc base rate")
    scope_flags(p)
    p.add_argument("--measure", choices=("deaths", "acd-active"), default="deaths")
    p.add_argument("--as-of", type=int, default=0)

    p = sub.add_parser("ask", help="create a question")
    scope_flags(p)
    p.add_argument("--measure", choices=("deaths", "events"), default="deaths")
    p.add_argument("--year", type=int)
    p.add_argument("--window", help="START:END (ISO dates)")
    p.add_argument("--title")
    p.add_argument("--question")
    p.add_argument("--manual", action="store_true", help="resolve by hand, not from data")
    p.add_argument("--tag", action="append", default=[])
    p.add_argument("--no-prior", action="store_true")
    p.add_argument("--prior", type=float, help="manual prior when the engine can't compute one")
    p.add_argument("--prior-note", default="")

    p = sub.add_parser("call", help="log a forecast")
    p.add_argument("id")
    p.add_argument("p", type=float)
    p.add_argument("--note")

    p = sub.add_parser("resolve", help="grade due questions from the data")
    p.add_argument("--id")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--outcome", choices=("yes", "no"), help="manual resolution (with --id)")
    p.add_argument("--decided-on")
    p.add_argument("--note")
    p.add_argument("--void", help="void a question, with the reason (with --id)")

    p = sub.add_parser("score", help="Brier/log/calibration, you vs the prior")
    p.add_argument("--write", action="store_true", help="also write data/scorecard.yaml")

    sub.add_parser("list", help="all questions, one line each")
    p = sub.add_parser("show", help="one question in full")
    p.add_argument("id")
    sub.add_parser("status", help="open questions and data coverage")

    args = ap.parse_args(argv)
    if args.cmd == "pull":
        from wopr.pipeline import download

        sys.argv = ["download"] + (["--force"] if args.force else [])
        download.main()
    elif args.cmd == "build":
        from wopr.pipeline import build

        build.main()
    elif args.cmd == "verify":
        from wopr.pipeline import validate

        validate.main()
    else:
        {
            "rate": cmd_rate,
            "ask": cmd_ask,
            "call": cmd_call,
            "resolve": cmd_resolve,
            "score": cmd_score,
            "list": cmd_list,
            "show": cmd_show,
            "status": cmd_status,
        }[args.cmd](args)


if __name__ == "__main__":
    main()
