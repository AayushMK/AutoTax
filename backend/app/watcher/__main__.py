"""Rule watcher CLI.

    python -m app.watcher init            # first time: record everything currently published as seen
    python -m app.watcher run             # daily: find new documents, archive, propose drafts, write report
    python -m app.watcher status          # rule coverage / review / budget-season check (exit 1 on alert)
    python -m app.watcher extract FILE    # run the Claude extraction on a PDF you already have
    python -m app.watcher fetch-sources   # re-download archived source PDFs and verify their hashes

Exit codes for `run`: 0 nothing relevant, 10 relevant findings (report written), 2 every source failed.
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

from app.engine.gate import budget_season_alert, check_payroll_allowed
from app.engine.rules import RULES_DIR, load_all, rules_for_date, verify_source_hashes

from . import documents, extract, impact, propose, report, sources

FOUND = 10


def cmd_init(args) -> int:
    cfg = sources.load_config()
    state = sources.load_state()
    with sources.http_client() as client:
        items, errors = _scan(cfg, client)
    new = sources.diff_new(items, state)
    relevant = {i.url for i in new if cfg.is_relevant(i.title)}
    sources.mark_seen(new, state, relevant)
    sources.save_state(state)
    print(f"Baseline recorded: {len(new)} documents ({len(relevant)} look relevant):")
    for i in new:
        if i.url in relevant:
            print(f"  • {i.title}\n    {i.url}")
    for e in errors:
        print(f"  ! {e}", file=sys.stderr)
    return 0


def cmd_run(args) -> int:
    if not sources.STATE_FILE.exists():
        print("No watch state yet. Run `python -m app.watcher init` once to record the baseline.", file=sys.stderr)
        return 2
    cfg = sources.load_config()
    state = sources.load_state()
    use_claude = not args.no_extract and extract.credentials_available()
    current = rules_for_date(args.today) if _covered(args.today) else load_all()[-1]

    with sources.http_client() as client:
        items, errors = _scan(cfg, client)
        if len(errors) == len(cfg.sources):
            print("\n".join(errors), file=sys.stderr)
            return 2
        new = sources.diff_new(items, state)
        relevant_items = [i for i in new if cfg.is_relevant(i.title)][: args.limit]
        findings = [_process(i, client, current, use_claude) for i in relevant_items]

    relevant_urls = {i.url for i in relevant_items}
    alert = budget_season_alert(args.today)
    if not args.dry_run:
        sources.mark_seen(new, state, relevant_urls)
        sources.save_state(state)

    other = [i for i in new if i.url not in relevant_urls]
    print(f"{len(items)} items scanned, {len(new)} new, {len(relevant_items)} relevant.")
    if not findings:
        return 0
    text = report.render(findings, other, [alert] if alert else [], errors)
    if not use_claude:
        text += "\n_Automatic extraction skipped (no Anthropic credentials or `--no-extract`). Review documents manually._\n"
    Path(args.report).write_text(text, encoding="utf-8")
    print(f"Report: {args.report}")
    return FOUND


def _process(item, client, current, use_claude) -> report.DocFinding:
    f = report.DocFinding(item)
    try:
        f.docs = documents.archive_from_page(item.url, client)
    except Exception as e:
        f.error = f"download failed: {e}"
        return f
    if not f.docs:
        f.note = "No PDF attached to this page — read the notice text directly."
    for doc in f.docs if use_claude else []:
        try:
            x = extract.extract(doc.path, current)
        except Exception as e:  # keep going; the document is still archived and reported
            f.error = f"extraction failed for {doc.filename}: {e}"
            continue
        f.extraction = x
        if x.changes:
            src = {"key": f"doc_{doc.sha256[:12]}", "title": x.document_title or item.title, "url": doc.url, "sha256": doc.sha256}
            text, new_rules = propose.apply_changes(current, x.changes, source=src, effective_from_bs=x.effective_from_bs)
            f.draft = propose.write_draft(text, new_rules)
            f.impact = impact.impact(current, new_rules)
    return f


def _scan(cfg, client):
    items, errors = [], []
    for src in cfg.sources:
        try:
            items.extend(sources.fetch_listing(src, client))
        except Exception as e:
            errors.append(f"{src.id}: {e}")
    return items, errors


def _covered(d: date) -> bool:
    return any(rs.effective_from <= d <= rs.effective_to for rs in load_all())


def cmd_status(args) -> int:
    code = 0
    alert = budget_season_alert(args.today)
    if alert:
        print(f"ALERT: {alert}")
        code = 1
    try:
        g = check_payroll_allowed(args.today, acknowledge_unverified=True)
        rs = g.rule_set
        print(f"Rules for {args.today}: {rs.version_id} (review: {rs.raw.review.status})")
        print(f"  unverified params: {len(g.acknowledged_unverified)}")
        for key, ok in verify_source_hashes(rs).items():
            print(f"  source {key}: {'hash OK' if ok else 'not archived locally' if ok is None else 'HASH MISMATCH'}")
    except Exception as e:
        print(f"BLOCKED: {e}")
        code = 1
    return code


def cmd_extract(args) -> int:
    rules = rules_for_date(args.today)
    x = extract.extract(Path(args.pdf), rules)
    item = sources.Item("manual", str(args.pdf), Path(args.pdf).name)
    f = report.DocFinding(item, extraction=x)
    if x.changes:
        text, new_rules = propose.apply_changes(rules, x.changes, effective_from_bs=x.effective_from_bs)
        f.draft = propose.write_draft(text, new_rules)
        f.impact = impact.impact(rules, new_rules)
    print(report.render([f], [], [], []))
    return FOUND if x.changes else 0


def cmd_fetch_sources(args) -> int:
    bad = 0
    with sources.http_client() as client:
        for rs in load_all():
            for key, src in rs.raw.sources.items():
                if not src.sha256:
                    continue
                path = documents.ARCHIVE_DIR / f"{src.sha256[:16]}.pdf"
                if not path.exists():
                    print(f"downloading {key} for {rs.version_id}…")
                    doc = documents.archive(src.url, client)
                    if doc.sha256 != src.sha256:
                        print(f"  HASH MISMATCH: published file changed ({doc.sha256})")
                        bad += 1
                        continue
            for key, ok in verify_source_hashes(rs).items():
                print(f"{rs.version_id} {key}: {'OK' if ok else 'no hash recorded' if ok is None else 'MISMATCH'}")
                bad += ok is False
    return 1 if bad else 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="python -m app.watcher")
    p.add_argument("--today", type=date.fromisoformat, default=date.today())
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init").set_defaults(fn=cmd_init)
    r = sub.add_parser("run")
    r.add_argument("--report", default="rule_watch_report.md")
    r.add_argument("--no-extract", action="store_true", help="skip Claude extraction")
    r.add_argument("--dry-run", action="store_true", help="do not update the state file")
    r.add_argument("--limit", type=int, default=10, help="max relevant documents per run")
    r.set_defaults(fn=cmd_run)
    sub.add_parser("status").set_defaults(fn=cmd_status)
    e = sub.add_parser("extract")
    e.add_argument("pdf")
    e.set_defaults(fn=cmd_extract)
    sub.add_parser("fetch-sources").set_defaults(fn=cmd_fetch_sources)
    args = p.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
