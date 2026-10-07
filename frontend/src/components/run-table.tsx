"use client";

import Link from "next/link";

import { date } from "@/lib/format";
import type { Run } from "@/lib/types";

export function RunTable({ runs, base }: { runs: Run[]; base: string }) {
  return (
    <div className="table-scroll">
      <table className="ledger">
        <thead>
          <tr>
            <th>Month</th>
            <th>Paid on</th>
            <th>Rules</th>
            <th>Status</th>
          </tr>
        </thead>
        <tbody>
          {runs.map((r) => (
            <tr key={r.id}>
              <td><Link href={`${base}/payroll/${r.id}`}>{r.month_label}</Link> <span className="faint small">FY {r.fiscal_year}</span></td>
              <td>{date(r.payment_date)}</td>
              <td className="small">{r.rule_set ?? "—"}</td>
              <td>
                {r.status === "finalized" ? (
                  <span className="tag verified">Finalized {date(r.finalized_at)}</span>
                ) : r.computed_at ? (
                  <span className="tag">Draft, computed</span>
                ) : (
                  <span className="tag needs_review">Draft, not computed</span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
