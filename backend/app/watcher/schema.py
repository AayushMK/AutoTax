"""Instructions and output schema shared by every extraction provider."""

from __future__ import annotations

from pydantic import BaseModel, Field

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
