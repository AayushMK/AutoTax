"use client";

import Link from "next/link";

import { money } from "@/lib/format";
import type { ContributionsReport, Period } from "@/lib/types";
import { useData } from "@/lib/use-data";

import { Loading } from "./bits";

/** A fiscal year as a grid of month tiles: finalized, draft, imported or not started yet. */
export function MonthGrid({ companyId, fiscalYear, canStart }: { companyId: number; fiscalYear: string; canStart: boolean }) {
  const fy = fiscalYear.replace("/", "-");
  const periods = useData<Period[]>(`/companies/${companyId}/payroll-runs/periods/${fy}`);
  const report = useData<ContributionsReport>(`/companies/${companyId}/reports/contributions/${fy}?include_drafts=true`);
  if (!periods.data) return <Loading what="months" />;
  const totals = new Map(report.data?.months.map((m) => [m.month, m]));

  return (
    <div className="monthgrid">
      {periods.data.map((p) => {
        const t = totals.get(p.index);
        const kind = !p.run_id ? "empty" : p.status === "draft" ? "draft" : p.source === "imported" ? "imported" : "done";
        const status = { empty: "Not started", draft: "Draft", imported: "Imported", done: "Finalized" }[kind];
        const body = (
          <>
            <span className="month__name">{p.label}</span>
            <span className="month__status">{status}</span>
            {t && p.run_id ? (
              <span className="month__fig">
                TDS <strong>{money(t.tds)}</strong>
                <br />
                Gross {money(t.gross)}
              </span>
            ) : (
              <span className="month__fig">{canStart ? "Start from Payroll" : " "}</span>
            )}
          </>
        );
        return p.run_id ? (
          <Link key={p.index} href={`/c/${companyId}/payroll/${p.run_id}`} className={`month month--${kind}`}>{body}</Link>
        ) : canStart ? (
          <Link key={p.index} href={`/c/${companyId}/payroll`} className="month month--empty">{body}</Link>
        ) : (
          <div key={p.index} className="month month--empty">{body}</div>
        );
      })}
    </div>
  );
}
