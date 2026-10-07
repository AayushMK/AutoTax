"""Markdown report used as the pull-request body."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from app.engine.money import fmt

from .documents import ArchivedDoc
from .extract import Extraction
from .impact import ImpactRow
from .sources import Item


@dataclass
class DocFinding:
    item: Item
    docs: list[ArchivedDoc] = field(default_factory=list)
    extraction: Extraction | None = None
    draft: Path | None = None
    impact: list[ImpactRow] = field(default_factory=list)
    error: str | None = None
    note: str | None = None


def render(findings: list[DocFinding], other_new: list[Item], alerts: list[str], errors: list[str]) -> str:
    out = ["# Rule watch: new government documents", ""]
    out += [
        "> Nothing in this PR changes active tax rules. Drafts live in `rules/np/proposed/`.",
        "> A reviewer must check each proposed value against the cited page, then move the draft into `rules/np/`.",
        "",
    ]
    for a in alerts:
        out.append(f"**⚠️ {a}**\n")
    for f in findings:
        out += [f"## {f.item.title}", f"Source: `{f.item.source_id}` — {f.item.url}", ""]
        if f.error:
            out += [f"❌ Could not process: {f.error}", ""]
            continue
        for d in f.docs:
            layer = "text layer" if d.has_text_layer else "**scanned (no text layer)**"
            out.append(f"- `{d.filename}` — {d.pages or '?'} pages, {d.size // 1024} KB, {layer}, sha256 `{d.sha256}`")
        if f.note:
            out += ["", f.note]
        x = f.extraction
        if x:
            out += ["", f"### Proposed changes ({len(x.changes)})"]
            if x.effective_from_bs:
                out.append(f"Effective from (BS): **{x.effective_from_bs}**")
            if x.changes:
                out += ["", "| Param | Proposed | Page | Quote |", "|---|---|---|---|"]
                for c in x.changes:
                    val = json.dumps(json.loads(c.proposed_value_json), ensure_ascii=False)
                    out.append(f"| `{c.param}` | `{_cell(val, 80)}` | {c.page} | {_cell(c.quote, 160)} |")
            if x.confirmations:
                out += ["", f"<details><summary>Confirmed unchanged ({len(x.confirmations)}) — candidates to mark <code>verified</code></summary>", ""]
                out += [f"- `{c.param}` p.{c.page}: {_cell(c.quote, 160)}" for c in x.confirmations]
                out += ["", "</details>"]
            if x.unmapped_findings:
                out += ["", "**Salary-relevant provisions with no matching parameter (may need engine changes):**"]
                out += [f"- {u}" for u in x.unmapped_findings]
            if x.rejected:
                out += ["", "<details><summary>Rejected model output</summary>", ""] + [f"- {r}" for r in x.rejected] + ["", "</details>"]
        if f.draft:
            out += ["", f"Draft rule file: `{f.draft.relative_to(f.draft.parents[3])}`"]
        changed = [r for r in f.impact if r.delta]
        if f.impact:
            out += ["", f"### Impact on sample employees ({len(changed)} of {len(f.impact)} change)"]
            if changed:
                out += ["", "| Case | Tax before | Tax after | Δ |", "|---|---:|---:|---:|"]
                out += [f"| {r.case} | {fmt(r.before)} | {fmt(r.after)} | {fmt(r.delta)} |" for r in changed]
        out.append("")
    if other_new:
        out += [f"<details><summary>Other new documents, judged not relevant ({len(other_new)})</summary>", ""]
        out += [f"- {i.title} — {i.url}" for i in other_new]
        out += ["", "</details>", ""]
    if errors:
        out += ["## Errors", ""] + [f"- {e}" for e in errors]
    return "\n".join(out) + "\n"


def _cell(text: str, n: int) -> str:
    t = " ".join(text.split()).replace("|", "\\|")
    return t if len(t) <= n else t[: n - 1] + "…"
