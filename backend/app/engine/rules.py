"""Load and validate versioned tax rule files (rules/np/*.yaml).

A rule file is the single source of truth for every rate, cap and slab. The loader
rejects any parameter that lacks a citation, and any missing required parameter.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from fractions import Fraction
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, field_validator

from .money import D, fraction

RULES_DIR = Path(__file__).resolve().parents[3] / "rules"

Status = Literal["verified", "corroborated", "needs_review"]

REQUIRED_PARAMS = {
    "resident.slabs.single",
    "resident.slabs.couple",
    "resident.sst_waiver_schemes",
    "resident.disability_first_slab_increase",
    "nonresident.flat_rate",
    "retirement.cap_amount",
    "retirement.cap_fraction",
    "ssf.employee_rate",
    "ssf.employer_rate",
    "ssf.employer_contribution_taxable",
    "insurance.life_cap",
    "insurance.health_cap",
    "insurance.building_cap",
    "remote_area.caps",
    "donation.cap_amount",
    "donation.cap_fraction",
    "female_rebate.rate",
    "female_rebate.excluded_if_couple",
    "fx.rate_type",
    "fx.date_basis",
    "rounding.tds_places",
}


class RuleFileError(ValueError):
    pass


class Source(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str
    url: str
    page: str | None = None  # landing page the document was published on
    sha256: str | None = None


class Param(BaseModel):
    model_config = ConfigDict(extra="forbid")
    value: Any
    src: str
    ref: str
    status: Status


class Review(BaseModel):
    status: Literal["draft", "ca_reviewed"]
    reviewed_by: str | None = None
    reviewed_on: date | None = None


class RuleFile(BaseModel):
    model_config = ConfigDict(extra="forbid")
    jurisdiction: str
    fiscal_year: str
    version: int
    effective_from: date
    effective_to: date
    review: Review
    sources: dict[str, Source]
    params: dict[str, Param]

    @field_validator("params")
    @classmethod
    def _required(cls, params: dict[str, Param]) -> dict[str, Param]:
        missing = REQUIRED_PARAMS - params.keys()
        if missing:
            raise ValueError(f"missing required params: {sorted(missing)}")
        return params


@dataclass(frozen=True)
class Slab:
    width: Decimal | None  # None = unbounded top slab
    rate: Decimal
    sst: bool = False  # the 1% Social Security Tax band


@dataclass(frozen=True)
class Citation:
    key: str
    ref: str
    source_title: str
    status: Status

    def __str__(self) -> str:
        return f"{self.ref} [{self.source_title}]"


class RuleSet:
    """Typed, read-only view over a validated rule file."""

    def __init__(self, raw: RuleFile, path: Path | None = None):
        self.raw = raw
        self.path = path
        for key, p in raw.params.items():
            if p.src not in raw.sources:
                raise RuleFileError(f"param {key!r} cites unknown source {p.src!r}")
        self._slabs = {k: self._parse_slabs(k) for k in ("single", "couple")}

    # identity ---------------------------------------------------------------
    @property
    def fiscal_year(self) -> str:
        return self.raw.fiscal_year

    @property
    def version_id(self) -> str:
        return f"{self.raw.jurisdiction}/{self.raw.fiscal_year}/v{self.raw.version}"

    @property
    def effective_from(self) -> date:
        return self.raw.effective_from

    @property
    def effective_to(self) -> date:
        return self.raw.effective_to

    def unreviewed_params(self) -> list[str]:
        return sorted(k for k, p in self.raw.params.items() if p.status != "verified")

    # access -----------------------------------------------------------------
    def cite(self, key: str) -> Citation:
        p = self.raw.params[key]
        return Citation(key, p.ref, self.raw.sources[p.src].title, p.status)

    def value(self, key: str) -> Any:
        return self.raw.params[key].value

    def dec(self, key: str) -> Decimal:
        return D(self.value(key))

    def frac(self, key: str) -> Fraction:
        return fraction(self.value(key))

    def slabs(self, schedule: Literal["single", "couple"]) -> list[Slab]:
        return self._slabs[schedule]

    def _parse_slabs(self, schedule: str) -> list[Slab]:
        key = f"resident.slabs.{schedule}"
        rows = self.value(key)
        slabs = [
            Slab(
                width=None if r["width"] is None else D(r["width"]),
                rate=D(r["rate"]),
                sst=bool(r.get("sst", False)),
            )
            for r in rows
        ]
        if not slabs or slabs[-1].width is not None:
            raise RuleFileError(f"{key}: last slab must be unbounded (width: null)")
        if any(s.width is None for s in slabs[:-1]):
            raise RuleFileError(f"{key}: only the last slab may be unbounded")
        return slabs


def load_rule_file(path: Path) -> RuleSet:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        raw = RuleFile.model_validate(data)
    except Exception as e:  # pydantic/yaml errors -> one error type
        raise RuleFileError(f"{path}: {e}") from e
    return RuleSet(raw, path)


def load_all(jurisdiction: str = "np", rules_dir: Path = RULES_DIR) -> list[RuleSet]:
    """All active rule files (files in `proposed/` are drafts and never loaded).

    A fiscal year may have several versions (e.g. `2083-84.yaml`, `2083-84.v2.yaml` after a
    mid-year ordinance). A later version must not start before an earlier one.
    """
    sets = sorted(
        (load_rule_file(p) for p in (rules_dir / jurisdiction).glob("*.yaml")),
        key=lambda r: (r.effective_from, r.raw.version),
    )
    by_fy: dict[str, list[RuleSet]] = {}
    for rs in sets:
        by_fy.setdefault(rs.fiscal_year, []).append(rs)
    for fy, versions in by_fy.items():
        nums = [v.raw.version for v in versions]
        if len(set(nums)) != len(nums):
            raise RuleFileError(f"FY {fy}: duplicate version numbers {nums}")
        ordered = sorted(versions, key=lambda v: v.raw.version)
        for a, b in zip(ordered, ordered[1:]):
            if b.effective_from < a.effective_from:
                raise RuleFileError(f"FY {fy}: v{b.raw.version} starts before v{a.raw.version}")
    return sets


def rules_for_date(on: date, jurisdiction: str = "np", rules_dir: Path = RULES_DIR) -> RuleSet:
    """The highest version whose effective window covers `on`."""
    covering = [rs for rs in load_all(jurisdiction, rules_dir) if rs.effective_from <= on <= rs.effective_to]
    if not covering:
        raise RuleFileError(f"no {jurisdiction} rule file covers {on}")
    return max(covering, key=lambda rs: rs.raw.version)


def verify_source_hashes(rs: RuleSet, sources_dir: Path = RULES_DIR / "sources") -> dict[str, bool | None]:
    """Check archived source PDFs (stored as `<sha256[:16]>.pdf`) against recorded hashes.

    Returns {source_key: True (matches) | False (file present but altered) | None (no hash
    recorded, or not archived locally — run `python -m app.watcher fetch-sources`)}.
    """
    out: dict[str, bool | None] = {}
    for key, src in rs.raw.sources.items():
        path = sources_dir / f"{src.sha256[:16]}.pdf" if src.sha256 else None
        if path is None or not path.exists():
            out[key] = None
            continue
        h = hashlib.sha256()
        with path.open("rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
        out[key] = h.hexdigest() == src.sha256
    return out
