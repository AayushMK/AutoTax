"use client";

import { useState } from "react";

import { ErrorNotice, Loading } from "@/components/bits";
import { useCompany } from "@/components/shell";
import { YearFigures, YearMonths, YearTable } from "@/components/year-table";
import { date } from "@/lib/format";
import type { AnnualStatement, Employee } from "@/lib/types";
import { useData } from "@/lib/use-data";

export default function MyPay() {
  const { companyId, companyName } = useCompany();
  const base = `/companies/${companyId}/me`;
  const record = useData<Employee>(base);
  const years = useData<string[]>(`${base}/years`);
  const [picked, setPicked] = useState<string | null>(null);
  const [view, setView] = useState<"months" | "table">("months");
  const fy = picked ?? years.data?.[0] ?? null;
  const st = useData<AnnualStatement>(fy ? `${base}/annual/${fy.replace("/", "-")}` : null);

  return (
    <div className="stack">
      <header className="page-head">
        <div>
          <h1>My pay</h1>
          {record.data && (
            <p>
              {record.data.name} (<span className="figure">{record.data.code}</span>) at {companyName ?? "your company"}, joined{" "}
              {date(record.data.joined_on)}
            </p>
          )}
        </div>
        {years.data && years.data.length > 1 && (
          <label className="row small">
            Fiscal year
            <select value={fy ?? ""} onChange={(e) => setPicked(e.target.value)}>
              {years.data.map((y) => <option key={y} value={y}>{y}</option>)}
            </select>
          </label>
        )}
      </header>

      <ErrorNotice error={record.error ?? years.error ?? st.error} />
      {st.loading && <Loading what="your pay" />}

      {st.data && (
        <>
          <section>
            <YearFigures st={st.data} />
            <p className="small muted" style={{ marginTop: "1rem" }}>
              SSF is 31% of your basic salary: 11% deducted from your pay and 20% added by the employer. Both, and your CIT, reduce
              your taxable income up to the legal limit.
            </p>
          </section>

          <section className="sheet">
            <div className="spread" style={{ alignItems: "center" }}>
              <h2 style={{ margin: 0 }}>FY {st.data.fiscal_year}, month by month</h2>
              <div className="seg" role="tablist" aria-label="Show as">
                <button type="button" role="tab" aria-selected={view === "months"} onClick={() => setView("months")}>Months</button>
                <button type="button" role="tab" aria-selected={view === "table"} onClick={() => setView("table")}>Table</button>
              </div>
            </div>
            <p className="small muted" style={{ margin: "4px 0 16px" }}>
              Only months HR has finalized appear here. Open a month to see how its tax was worked out.
            </p>
            {st.data.months_paid === 0 ? (
              <p className="muted">No finalized pay for this year yet.</p>
            ) : view === "months" ? (
              <YearMonths st={st.data} payslipHref={(pid) => `/c/${companyId}/my/payslips/${pid}`} />
            ) : (
              <YearTable st={st.data} payslipHref={(pid) => `/c/${companyId}/my/payslips/${pid}`} />
            )}
          </section>
        </>
      )}
    </div>
  );
}
