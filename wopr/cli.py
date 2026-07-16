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
import re
import sys

import yaml

import wopr
from wopr.engine import baserate, rolling
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


def resolve_pair(token: str) -> dict:
    """'Venezuela,Guyana' -> pair scope with a<b gwnos and a display name."""
    parts = [p.strip() for p in re.split(r"[,/|]| - ", token) if p.strip()]
    if len(parts) != 2:
        raise SystemExit("--pair wants two countries, e.g. --pair 'Venezuela,Guyana'")
    (ga, na, _), (gb, nb, _) = (find_unit("country", p) for p in parts)
    if ga == gb:
        raise SystemExit("a pair needs two different countries")
    a, b = min(ga, gb), max(ga, gb)
    name = f"{na if ga == a else nb} – {nb if gb == b else na}"
    return {"kind": "pair", "id": a * 1000 + b, "a": a, "b": b, "name": name}


def scope_from_args(args) -> tuple[dict, list[str]]:
    if getattr(args, "pair", None):
        return resolve_pair(args.pair), ["sb"]
    picks = [(k, getattr(args, k)) for k in ("country", "dyad", "conflict", "actor") if getattr(args, k)]
    if len(picks) != 1:
        raise SystemExit("give exactly one of --country / --dyad / --conflict / --actor / --pair")
    kind, token = picks[0]
    uid, name, types = find_unit(kind, token)
    return {"kind": kind, "id": uid, "name": name}, types


def window_months(window: dict) -> tuple[int, int] | None:
    """(start month index, length in months) when the window is month-aligned
    (first day → last day of a month), else None."""
    start = datetime.date.fromisoformat(str(window["start"]))
    end = datetime.date.fromisoformat(str(window["end"]))
    if start.day != 1 or (end + datetime.timedelta(days=1)).day != 1:
        return None
    w = (end.year - start.year) * 12 + end.month - start.month + 1
    return rolling.mi(start.year, start.month), w


def engine_prior(criteria: dict) -> dict | None:
    scope, types = criteria["scope"], criteria["types"]
    if criteria["measure"] != "deaths" or scope["kind"] not in ("country", "dyad", "pair"):
        return None
    if scope["kind"] == "dyad" and types != ["sb"]:
        return None
    if scope["kind"] == "pair" and criteria["threshold"] != 25:
        return None  # pair substrate is UCDP activity, defined at the 25-death line
    sub = baserate.load_substrate()
    if scope["id"] not in sub[scope["kind"]]:
        return None  # e.g. non-state dyad, or a pair outside the relevance universe

    w = criteria["window"]
    calendar_year = str(w["start"])[5:] == "01-01" and str(w["end"]) == f"{str(w['start'])[:4]}-12-31"
    wm = window_months(w)
    if scope["kind"] != "pair" and not calendar_year and wm and 1 <= wm[1] <= 24:
        # month-aligned non-calendar window: the rolling engine prices it exactly
        monthly = rolling.load_monthly(sub)
        spec = rolling.RollingSpec(scope["kind"], scope["id"], tuple(types), criteria["threshold"], wm[1], wm[0])
        result = rolling.rate(spec, sub, monthly)
    else:
        as_of = int(str(w["start"])[:4])
        if scope["kind"] == "pair":
            spec = baserate.Spec("pair", scope["id"], "acd-active", (), 25, as_of)
        else:
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
        "pair": f"between the governments of {scope['name']} (either direction)",
    }[scope["kind"]]
    w = c["window"]
    return (
        f"Will UCDP record ≥{c['threshold']} {what} (best estimate, {kinds}) "
        f"{where} between {w['start']} and {w['end']} inclusive?"
    )


# ---------------------------------------------------------------- commands


def render_detail(detail: dict) -> str:
    if detail.get("spec", {}).get("window_months"):
        return rolling.render(detail)
    return baserate.render(detail)


def cmd_rate(args) -> None:
    scope, default_types = scope_from_args(args)
    if scope["kind"] not in ("country", "dyad", "pair"):
        raise SystemExit("rate supports --country, --dyad, and --pair scopes")
    types = args.types.split(",") if args.types else default_types
    sub = baserate.load_substrate()
    if args.months:
        if scope["kind"] == "pair":
            raise SystemExit("rolling windows support --country and --dyad (pairs are annual)")
        monthly = rolling.load_monthly(sub)
        if args.start:
            y, m = (int(x) for x in args.start.split("-"))
            start = rolling.mi(y, m)
        else:
            start = monthly["data_end"] + 1  # first month past observed data
        spec = rolling.RollingSpec(scope["kind"], scope["id"], tuple(types), args.threshold, args.months, start)
        result = rolling.rate(spec, sub, monthly)
        result["unit_name"] = scope["name"]
        print(rolling.render(result))
        return
    if scope["kind"] == "pair":
        if scope["id"] not in sub["pair"]:
            raise SystemExit(
                f"{scope['name']} is outside the relevance universe (not proximate, not same-region, "
                "no P5 member) — there is no defensible denominator, so the engine declines"
            )
        spec = baserate.Spec("pair", scope["id"], "acd-active", (), 25, args.as_of or 0)
    else:
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
        print(render_detail(prior["detail"]))
    print()
    print(f"log your forecast:  wopr call {q['id']} <p> --note '…'")


def cmd_call(args) -> None:
    q = store.load(args.id)
    fc = store.add_forecast(q, args.p, args.note or "", source=args.source or "")
    store.save(q)
    prior_p = (q.get("prior") or {}).get("p")
    who = args.source or "challenger"
    drift = f"  (engine {prior_p}, {who} {args.p})" if prior_p is not None else ""
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
        print(render_detail(detail) if detail else f"prior: {q['prior']['p']} ({q['prior'].get('engine')})")


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
    print(f"questions: {len(questions)} total, {len(open_qs)} open, {len(provisional)} provisional")
    for q in open_qs:
        w = q["criteria"]["window"]
        challengers = sorted({f.get("source", "challenger") for f in q["forecasts"]})
        extra = f"  [{', '.join(challengers)}]" if challengers else ""
        print(f"  {q['id']}  ends {w['end']}  {q['title'][:56]}{extra}")
    for q in provisional:
        print(f"  {q['id']}  provisional {q['resolution']['outcome']} — confirms on next annual release")


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="wopr", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--version", action="version", version=f"wopr {wopr.__version__}")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("pull", help="download UCDP sources").add_argument("--force", action="store_true")
    sub.add_parser("build", help="build data/ from sources/")
    sub.add_parser("verify", help="run the validation gate")
    p = sub.add_parser("acled", help="pull ACLED aggregate files (needs .env credentials)")
    p.add_argument("--force", action="store_true")
    p.add_argument("--api-check", action="store_true", help="probe event-level API entitlement")

    def scope_flags(p):
        p.add_argument("--country")
        p.add_argument("--dyad")
        p.add_argument("--conflict")
        p.add_argument("--actor")
        p.add_argument("--pair", help="two countries, e.g. 'Venezuela,Guyana' (interstate pair)")
        p.add_argument("--types", help="comma subset of sb,ns,os")
        p.add_argument("--threshold", type=int, default=25)

    p = sub.add_parser("rate", help="ad-hoc base rate")
    scope_flags(p)
    p.add_argument("--measure", choices=("deaths", "acd-active"), default="deaths")
    p.add_argument("--as-of", type=int, default=0)
    p.add_argument("--months", type=int, help="rolling window length (monthly substrate)")
    p.add_argument("--start", help="rolling window start, YYYY-MM (default: first unobserved month)")

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

    p = sub.add_parser("call", help="log a challenger forecast (another model, or an analyst override)")
    p.add_argument("id")
    p.add_argument("p", type=float)
    p.add_argument("--note")
    p.add_argument("--source", help="who this number belongs to, e.g. views, analyst")

    p = sub.add_parser("resolve", help="grade due questions from the data")
    p.add_argument("--id")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--outcome", choices=("yes", "no"), help="manual resolution (with --id)")
    p.add_argument("--decided-on")
    p.add_argument("--note")
    p.add_argument("--void", help="void a question, with the reason (with --id)")

    p = sub.add_parser("score", help="Brier/log/calibration, challengers vs the engine")
    p.add_argument("--write", action="store_true", help="also write data/scorecard.yaml")

    p = sub.add_parser("backtest", help="walk-forward test: is the engine itself calibrated?")
    p.add_argument("--burn-in", type=int, default=5, help="years of history before scoring starts")
    p.add_argument("--write", action="store_true", help="also write data/backtest.yaml")

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
    elif args.cmd == "acled":
        from wopr.pipeline import acled

        acled.api_check() if args.api_check else acled.pull(force=args.force)
    elif args.cmd == "backtest":
        from wopr.engine import backtest

        report = backtest.run(burn_in=args.burn_in)
        if args.write:
            with open(DATA / "backtest.yaml", "w") as f:
                yaml.safe_dump(report, f, sort_keys=False, allow_unicode=True)
            print(f"wrote {DATA / 'backtest.yaml'}")
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
