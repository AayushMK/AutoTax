"use client";

import { ErrorNotice, Loading } from "@/components/bits";
import { useCompany } from "@/components/shell";
import { dateTime } from "@/lib/format";
import type { AuditEntry } from "@/lib/types";
import { useData } from "@/lib/use-data";

const ACTION: Record<string, string> = {
  "company.create": "Created the company",
  "member.set": "Changed a member’s access",
  "employee.create": "Added an employee",
  "employee.update": "Edited an employee",
  "tax_profile.set": "Saved a tax profile",
  "salary_structure.add": "Changed a salary",
  "salary_structure.delete": "Deleted a salary",
  "payroll.create": "Started a payroll month",
  "payroll.adjustment.add": "Added a one-off payment",
  "payroll.adjustment.delete": "Removed a one-off payment",
  "payroll.compute": "Calculated payroll",
  "payroll.finalize": "Finalized payroll",
  "payroll.delete": "Deleted a draft payroll",
  "fx.sync": "Fetched NRB rates",
  "fx.override": "Saved a bank exchange rate",
};

function summary(e: AuditEntry): string {
  const d = e.data as Record<string, unknown>;
  switch (e.action) {
    case "payroll.finalize":
      return `${d.rule_set}, total TDS ${d.total_tds}${Array.isArray(d.acknowledged_unverified) && d.acknowledged_unverified.length ? `, accepted ${d.acknowledged_unverified.length} unverified rule values` : ""}`;
    case "payroll.compute":
      return `${d.employees} employees, total TDS ${d.total_tds}`;
    case "employee.create":
      return `${d.code} ${d.name}`;
    case "tax_profile.set":
      return `FY ${d.fiscal_year}`;
    case "fx.override":
      return `${d.currency} on ${d.on}: ${d.buy} (${d.reason})`;
    case "payroll.create":
      return `FY ${d.fiscal_year} month ${d.month}`;
    default:
      return "";
  }
}

export default function Audit() {
  const { companyId, me } = useCompany();
  const { data, error, loading } = useData<AuditEntry[]>(`/companies/${companyId}/audit`);

  return (
    <div className="stack">
      <header className="page-head">
        <div>
          <h1>Activity</h1>
          <p>Every change to employees, rates and payroll, with who made it. Entries can’t be edited or removed.</p>
        </div>
      </header>
      <section className="sheet">
        {loading && <Loading what="activity" />}
        <ErrorNotice error={error} />
        {data && (
          <div className="table-scroll">
            <table className="ledger">
              <thead><tr><th>When</th><th>Who</th><th>What</th><th>Details</th></tr></thead>
              <tbody>
                {data.map((e) => (
                  <tr key={e.id}>
                    <td className="small" style={{ whiteSpace: "nowrap" }}>{dateTime(e.at)}</td>
                    <td className="small">{e.user_id === me?.id ? "You" : `User #${e.user_id}`}</td>
                    <td>{ACTION[e.action] ?? e.action}</td>
                    <td className="small muted">{summary(e)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}
