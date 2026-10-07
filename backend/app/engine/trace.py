"""Human-readable calculation trace. Every number in a result is explained here."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from .money import fmt
from .rules import Citation


@dataclass(frozen=True)
class Step:
    label: str
    amount: Decimal
    detail: str = ""
    citation: Citation | None = None

    def __str__(self) -> str:
        cite = f"  ⟨{self.citation}⟩" if self.citation else ""
        detail = f" = {self.detail}" if self.detail else ""
        return f"{self.label}: {fmt(self.amount)}{detail}{cite}"


@dataclass
class Trace:
    steps: list[Step] = field(default_factory=list)

    def add(self, label: str, amount: Decimal, detail: str = "", citation: Citation | None = None) -> Decimal:
        self.steps.append(Step(label, amount, detail, citation))
        return amount

    def extend(self, other: "Trace", prefix: str = "") -> None:
        for s in other.steps:
            self.steps.append(Step(prefix + s.label, s.amount, s.detail, s.citation))

    def __str__(self) -> str:
        return "\n".join(str(s) for s in self.steps)
