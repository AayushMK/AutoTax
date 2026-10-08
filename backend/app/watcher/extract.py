"""Optional: read a (possibly scanned) government PDF with an AI model and propose rule changes.

Nothing here edits active rules. Output is a list of *proposals* with page numbers and verbatim
quotes, which a reviewer checks against the PDF. The model is pluggable (see providers.py:
Gemini free tier or Claude); without any API key the watcher skips this step.
"""

from __future__ import annotations

import io
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

from pypdf import PdfReader, PdfWriter

from app.engine.rules import RuleSet

from .providers import ChunkFailed, Provider, get_provider
from .schema import ChunkFindings, Confirmation, ProposedChange

__all__ = ["ChunkFindings", "Confirmation", "Extraction", "ProposedChange", "extract", "merge", "split_pdf"]


@dataclass
class Extraction:
    document_title: str | None = None
    effective_from_bs: str | None = None
    changes: list[ProposedChange] = field(default_factory=list)
    confirmations: list[Confirmation] = field(default_factory=list)
    unmapped_findings: list[str] = field(default_factory=list)
    rejected: list[str] = field(default_factory=list)  # proposals that failed validation
    chunks: int = 0
    provider: str = ""


def split_pdf(path: Path, pages_per_chunk: int, max_bytes: int) -> list[tuple[int, int, bytes]]:
    """Return (first_page, last_page, pdf_bytes) chunks, 1-indexed, each under max_bytes."""
    reader = PdfReader(str(path))
    out: list[tuple[int, int, bytes]] = []

    def emit(start: int, end: int) -> None:  # 0-indexed, end exclusive
        w = PdfWriter()
        for i in range(start, end):
            w.add_page(reader.pages[i])
        buf = io.BytesIO()
        w.write(buf)
        data = buf.getvalue()
        if len(data) > max_bytes and end - start > 1:
            mid = (start + end) // 2
            emit(start, mid)
            emit(mid, end)
        else:
            out.append((start + 1, end, data))

    for s in range(0, len(reader.pages), pages_per_chunk):
        emit(s, min(s + pages_per_chunk, len(reader.pages)))
    return out


def _current_params(rules: RuleSet) -> str:
    return json.dumps(
        {k: {"value": p.value, "ref": p.ref} for k, p in rules.raw.params.items()},
        ensure_ascii=False,
        indent=1,
    )


def _progress(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def extract(path: Path, rules: RuleSet, provider: Provider | None = None, log=_progress) -> Extraction:
    provider = provider or get_provider()
    if provider is None:
        raise RuntimeError("no extraction provider: set GEMINI_API_KEY (free) or ANTHROPIC_API_KEY")
    result = Extraction(provider=f"{provider.name}:{provider.model}")
    params = _current_params(rules)
    for first, last, data in split_pdf(path, provider.pages_per_chunk, provider.max_chunk_bytes):
        result.chunks += 1
        log(f"  [{provider.name}] reading pages {first}-{last} ({len(data) // 1024} KB)…")
        prompt = (
            f"This is pages {first}-{last} of the full document. Report page numbers in full-document numbering.\n\n"
            f"Current rule parameters ({rules.version_id}):\n{params}"
        )
        try:
            found = provider.read_chunk(data, prompt)
        except ChunkFailed as e:
            result.rejected.append(f"pages {first}-{last}: {e}")
            continue
        merge(result, found, rules, first, last)
    return result


def merge(result: Extraction, found: ChunkFindings, rules: RuleSet, first: int, last: int) -> None:
    result.document_title = result.document_title or found.document_title
    result.effective_from_bs = result.effective_from_bs or found.effective_from_bs
    result.unmapped_findings.extend(found.unmapped_findings)
    for c in found.confirmations:
        if c.param in rules.raw.params and first <= c.page <= last:
            result.confirmations.append(c)
        else:
            result.rejected.append(f"confirmation for {c.param!r} p.{c.page}: unknown param or page outside chunk")
    for ch in found.changes:
        problem = validate_change(ch, rules)
        if not problem and not first <= ch.page <= last:
            problem = f"page {ch.page} outside chunk {first}-{last}"
        if problem:
            result.rejected.append(f"{ch.param}: {problem}")
        elif json.loads(ch.proposed_value_json) == rules.value(ch.param):
            result.confirmations.append(Confirmation(param=ch.param, page=ch.page, quote=ch.quote))
        else:
            result.changes.append(ch)


def validate_change(ch: ProposedChange, rules: RuleSet) -> str | None:
    from .propose import apply_changes  # local import: propose depends on this module's types

    if ch.param not in rules.raw.params:
        return "unknown parameter key"
    if not ch.quote.strip():
        return "missing verbatim quote"
    try:
        json.loads(ch.proposed_value_json)
    except json.JSONDecodeError as e:
        return f"proposed value is not valid JSON ({e})"
    try:
        apply_changes(rules, [ch])
    except Exception as e:  # new value breaks the rule-file schema (e.g. malformed slabs)
        return f"invalid value: {e}"
    return None
