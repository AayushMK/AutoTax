"use client";

import Link from "next/link";
import { useState } from "react";

import { ErrorNotice, Loading, Num } from "@/components/bits";
import { useCompany } from "@/components/shell";
import { download } from "@/lib/api";
import { addMoney } from "@/lib/format";
import type { ContributionsReport, RulesStatus } from "@/lib/types";
import { useData } from "@/lib/use-data";

type View = "ssf_total" | "ssf_employee" | "ssf_employer" | "cit" | "tds" | "gross";
const VIEWS: { key: View; label: string }[] = [
  { key: "ssf_total", label: "SSF 31%" },
  { key: "ssf_employee", label: "SSF 11% employee" },
  { key: "ssf_employer", label: "SSF 20% employer" },
  { key: "cit", label: "CIT" },
  { key: "tds", label: "TDS" },
  { key: "gross", label: "Gross pay" },
];

type Cell = Record<"gross" | "ssf_employee" | "ssf_employer" | "cit" | "tds", string>;
const pick = (c: Cell | undefined, v: View) =>
  !c ? undefined : v === "ssf_total" ? addMoney(c.ssf_employee, c.ssf_employer) : c[v];

export default function Contributions() {
  const { companyId } = useCompany();
  const rules = useData<RulesStatus>("/rules/status");
  const years = (rules.data?.all ?? []).map((r) => r.fiscal_year).reverse();
  const [picked, setPicked] = useState<string | null>(null);
  const [drafts, setDrafts] = useState(false);
  const [view, setView] = useState<View>("ssf_total");
  const fy = picked ?? rules.data?.current?.fiscal_year ?? years[0] ?? null;
  const path = fy ? `/companies/${companyId}/reports/contributions/${fy.replace("/", "-")}` : null;
  const { data: r, error, loading } = useData<ContributionsReport>(path && `${path}?include_drafts=${drafts}`);
  const paidMonths = r?.months.filter((m) => m.status) ?? [];

  return (
    <div className="stack">
      <header className="page-head">
        <div>
          <h1>SSF, CIT & TDS</h1>
          <p>For each employee, month by month and for the whole year. Download for SSF and CIT remittance, or the TDS sheet in IRD’s layout.</p>
        </div>
        {fy && (
          <div className="row">
            <button className="btn quiet" onClick={() => download(`${path}.csv?include_drafts=${drafts}`, `ssf-cit-${fy.replace("/", "-")}.csv`)}>
              SSF & CIT (CSV)
            </button>
            <button className="btn quiet" onClick={() => download(`/companies/${companyId}/reports/tds/${fy.replace("/", "-")}.csv?include_drafts=${drafts}`, `tds-ird-${fy.replace("/", "-")}.csv`)}>
              TDS detail for IRD (CSV)
            </button>
          </div>
        )}
      </header>

      <section className="sheet">
        <div className="row" style={{ marginBottom: "1rem", justifyContent: "space-between" }}>
          <div className="seg" role="tablist" aria-label="Show">
            {VIEWS.map((v) => (
              <button key={v.key} type="button" role="tab" aria-selected={view === v.key} onClick={() => setView(v.key)}>
                {v.label}
              </button>
            ))}
          </div>
          <div className="row small">
            <label className="check"><input type="checkbox" checked={drafts} onChange={(e) => setDrafts(e.target.checked)} /> Include draft months</label>
            <select aria-label="Fiscal year" value={fy ?? ""} onChange={(e) => setPicked(e.target.value)}>
              {years.map((y) => <option key={y} value={y}>FY {y}</option>)}
            </select>
          </div>
        </div>

        {r && (
          <dl className="figures" style={{ marginBottom: "1.25rem" }}>
            <div><dt>SSF for the year (31%)</dt><dd><Num v={r.totals.ssf_total} /></dd></div>
            <div><dt>Deducted from employees (11%)</dt><dd><Num v={r.totals.ssf_employee} /></dd></div>
            <div><dt>Paid by the company (20%)</dt><dd><Num v={r.totals.ssf_employer} /></dd></div>
            <div><dt>CIT for the year</dt><dd><Num v={r.totals.cit} /></dd></div>
            <div><dt>TDS for the year</dt><dd><Num v={r.totals.tds} /></dd></div>
          </dl>
        )}

        {loading && <Loading what="contributions" />}
        <ErrorNotice error={error} />
        {r && r.employees.length === 0 && (
          <p className="muted">No {drafts ? "" : "finalized "}payroll in FY {r.fiscal_year} yet.</p>
        )}
        {r && r.employees.length > 0 && (
          <div className="table-scroll">
            <table className="ledger">
              <thead>
                <tr>
                  <th>Employee</th>
                  {paidMonths.map((m) => (
                    <th key={m.month} className="num">
                      {m.month_label.replace(/ \d{4}/, "")}
                      {m.status === "draft" && <span className="faint"> (draft)</span>}
                    </th>
                  ))}
                  <th className="num">Year</th>
                </tr>
              </thead>
              <tbody>
                {r.employees.map((e) => (
                  <tr key={e.employee_id}>
                    <td style={{ whiteSpace: "nowrap" }}>
                      <Link href={`/c/${companyId}/employees/${e.employee_id}`}>{e.name}</Link>{" "}
                      <span className="faint small figure">{e.code}</span>
                    </td>
                    {paidMonths.map((m) => (
                      <td key={m.month} className="num"><Num v={pick(e.months[String(m.month)], view)} /></td>
                    ))}
                    <td className="num"><strong><Num v={pick(e.totals, view)} /></strong></td>
                  </tr>
                ))}
              </tbody>
              <tfoot>
                <tr>
                  <td>Company total</td>
                  {paidMonths.map((m) => <td key={m.month} className="num"><Num v={pick(m, view)} /></td>)}
                  <td className="num"><Num v={pick(r.totals, view)} /></td>
                </tr>
              </tfoot>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}
