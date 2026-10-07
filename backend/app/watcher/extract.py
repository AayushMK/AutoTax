"""Optional: read a (possibly scanned) government PDF with Claude and propose rule-file changes.

Nothing here edits active rules. Output is a list of *proposals* with page numbers and verbatim
quotes, which a reviewer checks against the PDF. Requires Anthropic credentials
(ANTHROPIC_API_KEY or an `ant auth login` profile); without them the watcher skips this step.
"""

from __future__ import annotations

import base64
import io
import json
import os
from dataclasses import dataclass, field
from pathlib import Path

import anthropic
from pydantic import BaseModel, Field
from pypdf import PdfReader, PdfWriter

from app.engine.rules import RuleSet

MODEL = "claude-opus-5-5"
PAGES_PER_CHUNK = 60
MAX_CHUNK_BYTES = 22 * 1024 * 1024  # request limit is 32 MB after base64 (+33%)

SYSTEM = """You are a Nepal tax-law analyst helping keep a payroll system's tax rules exact.
You read official government documents (Finance Act / आर्थिक ऐन, Income Tax Act / आयकर ऐन,
ordinances / अध्यादेश, IRD circulars, SSF regulations). Many are scanned Nepali text.

Only report provisions that affect salary (employment income) tax computation for individuals:
tax slabs and rates, the 1% social security tax and its waivers, retirement-contribution
deductions (SSF, CIT, EPF, approved funds), insurance premium deductions, remote-area deductions,
women's rebate, disability provisions, non-resident rates, donations, foreign-currency conversion,
and TDS rounding.

Rules:
- Every item must cite the page number (in the FULL document's numbering) and a verbatim quote
  copied from that page in its original language. Never invent or paraphrase a quote.
- Map each provision onto the existing parameter keys given to you. Use `changes` only when the
  document's value differs from the current value; use `confirmations` when it matches.
- Encode proposed values as JSON in exactly the same shape as the current value
  (e.g. slabs are a list of {"width": number|null, "rate": "decimal string", "sst": bool}).
- Provisions that matter for salary tax but don't fit any key go in `unmapped_findings`.
- If this part of the document has nothing relevant, return empty lists."""


class ProposedChange(BaseModel):
    param: str = Field(description="Existing parameter key, e.g. insurance.life_cap")
    proposed_value_json: str = Field(description="New value as JSON, same shape as the current value")
    page: int
    quote: str = Field(description="Verbatim supporting text from that page, original language")
    explanation: str


class Confirmation(BaseModel):
    param: str
    page: int
    quote: str


class ChunkFindings(BaseModel):
    document_title: str | None = None
    effective_from_bs: str | None = Field(default=None, description="BS date YYYY-MM-DD if stated")
    changes: list[ProposedChange]
    confirmations: list[Confirmation]
    unmapped_findings: list[str]


@dataclass
class Extraction:
    document_title: str | None = None
    effective_from_bs: str | None = None
    changes: list[ProposedChange] = field(default_factory=list)
    confirmations: list[Confirmation] = field(default_factory=list)
    unmapped_findings: list[str] = field(default_factory=list)
    rejected: list[str] = field(default_factory=list)  # proposals that failed validation
    chunks: int = 0


def credentials_available() -> bool:
    """API key, auth token, federation env, or an `ant auth login` profile (the SDK resolves lazily)."""
    if any(os.environ.get(v) for v in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_FEDERATION_RULE_ID")):
        return True
    return (Path.home() / ".config" / "anthropic").is_dir()


def split_pdf(path: Path, pages_per_chunk: int = PAGES_PER_CHUNK) -> list[tuple[int, int, bytes]]:
    """Return (first_page, last_page, pdf_bytes) chunks, 1-indexed, each under MAX_CHUNK_BYTES."""
    reader = PdfReader(str(path))
    out: list[tuple[int, int, bytes]] = []

    def emit(start: int, end: int) -> None:  # 0-indexed, end exclusive
        w = PdfWriter()
        for i in range(start, end):
            w.add_page(reader.pages[i])
        buf = io.BytesIO()
        w.write(buf)
        data = buf.getvalue()
        if len(data) > MAX_CHUNK_BYTES and end - start > 1:
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


def extract(path: Path, rules: RuleSet, client: anthropic.Anthropic | None = None, log=print) -> Extraction:
    client = client or anthropic.Anthropic()
    result = Extraction()
    params = _current_params(rules)
    for first, last, data in split_pdf(path):
        result.chunks += 1
        log(f"  extracting pages {first}-{last} ({len(data) // 1024} KB)…")
        response = client.beta.messages.parse(
            model=MODEL,
            max_tokens=16000,
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            output_config={"effort": "high"},
            system=SYSTEM,
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "document",
                        "source": {"type": "base64", "media_type": "application/pdf", "data": base64.standard_b64encode(data).decode()},
                    },
                    {
                        "type": "text",
                        "text": (
                            f"This is pages {first}-{last} of the full document. Report page numbers in full-document numbering.\n\n"
                            f"Current rule parameters ({rules.version_id}):\n{params}"
                        ),
                    },
                ],
            }],
            output_format=ChunkFindings,
        )
        if response.stop_reason == "refusal":
            result.rejected.append(f"pages {first}-{last}: model declined ({getattr(response.stop_details, 'category', None)})")
            continue
        if response.stop_reason == "max_tokens" or response.parsed_output is None:
            result.rejected.append(f"pages {first}-{last}: incomplete response ({response.stop_reason})")
            continue
        merge(result, response.parsed_output, rules, first, last)
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
