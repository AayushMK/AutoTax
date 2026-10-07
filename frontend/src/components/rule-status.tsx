"use client";

import { PARAM_LABEL } from "@/lib/format";
import type { RulesStatus } from "@/lib/types";

import { Stamp } from "./stamp";

export function RuleStamp({ status }: { status: RulesStatus }) {
  const c = status.current;
  if (!c) return <Stamp tone="seal" title="No tax rules for today" note="Payroll is blocked until they are added" />;
  if (c.review_status === "ca_reviewed" && c.unverified_params.length === 0) {
    return <Stamp tone="moss" title={`FY ${c.fiscal_year} rules verified`} note="Checked against the Finance Act" />;
  }
  return (
    <Stamp
      tone="seal"
      title={`FY ${c.fiscal_year} rules not yet verified`}
      note={`${c.unverified_params.length} values still need a CA check`}
    />
  );
}

export function UnverifiedList({ params }: { params: string[] }) {
  return (
    <ul className="small" style={{ columns: "16rem", margin: "0.5rem 0 0", paddingLeft: "1.1rem" }}>
      {params.map((p) => (
        <li key={p}>{PARAM_LABEL[p] ?? p}</li>
      ))}
    </ul>
  );
}
