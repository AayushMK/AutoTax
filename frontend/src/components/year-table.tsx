"use client";

import Link from "next/link";

import type { AnnualStatement } from "@/lib/types";

import { Num } from "./bits";

/** Month-by-month pay with SSF and CIT, and the year's totals. */
export function YearTable({ st, payslipHref }: { st: AnnualStatement; payslipHref: (payslipId: number, runId: number) => string }) {
  const t = st.totals;
  return (
    <div className="table-scroll">
      <table className="ledger">
        <thead>
          <tr>
            <th>Month</th>
            <th className="num">Gross</th>
            <th className="num">SSF 11% (you)</th>
            <th className="num">SSF 20% (employer)</th>
            <th className="num">CIT</th>
            <th className="num">TDS</th>
            <th className="num">Net pay</th>
          </tr>
        </thead>
        <tbody>
          {st.months.map((m) =>
            m.payslip_id ? (
              <tr key={m.month}>
                <td>
                  <Link href={payslipHref(m.payslip_id, m.run_id!)}>{m.month_label}</Link>
                  {m.status === "draft" && <span className="tag needs_review" style={{ marginLeft: "0.5rem" }}>draft</span>}
                  {m.source === "imported" && <span className="tag" style={{ marginLeft: "0.5rem" }} title="Entered from payroll done before AutoTax">imported</span>}
                  {m.share && <span className="faint small" style={{ marginLeft: "0.4rem" }}>{m.share} of the month</span>}
                </td>
                <td className="num"><Num v={m.gross} /></td>
                <td className="num"><Num v={m.ssf_employee} /></td>
                <td className="num"><Num v={m.ssf_employer} /></td>
                <td className="num"><Num v={m.cit} /></td>
                <td className="num"><Num v={m.tds} /></td>
                <td className="num"><Num v={m.net_pay} /></td>
              </tr>
            ) : (
              <tr key={m.month} className="faint">
                <td>{m.month_label}</td>
                <td colSpan={6} className="small">Not paid yet</td>
              </tr>
            ),
          )}
        </tbody>
        <tfoot>
          <tr>
            <td>Year so far, {st.months_paid} {st.months_paid === 1 ? "month" : "months"}</td>
            <td className="num"><Num v={t.gross} /></td>
            <td className="num"><Num v={t.ssf_employee} /></td>
            <td className="num"><Num v={t.ssf_employer} /></td>
            <td className="num"><Num v={t.cit} /></td>
            <td className="num"><Num v={t.tds} /></td>
            <td className="num"><Num v={t.net_pay} /></td>
          </tr>
        </tfoot>
      </table>
    </div>
  );
}

/** The three numbers people ask about first. */
export function YearFigures({ st }: { st: AnnualStatement }) {
  return (
    <dl className="figures">
      <div><dt>SSF this year (11% + 20%)</dt><dd><Num v={st.totals.ssf_total} /></dd></div>
      <div><dt>CIT this year</dt><dd><Num v={st.totals.cit} /></dd></div>
      <div><dt>Tax paid so far</dt><dd><Num v={st.totals.tds} /></dd></div>
      {st.projected_annual_tax && (
        <div><dt>Tax for the whole year, projected</dt><dd><Num v={st.projected_annual_tax} /></dd></div>
      )}
      {st.cit_tax_saving && st.cit_tax_saving !== "0.00" && (
        <div><dt>Tax saved by CIT this year</dt><dd><Num v={st.cit_tax_saving} /></dd></div>
      )}
    </dl>
  );
}
