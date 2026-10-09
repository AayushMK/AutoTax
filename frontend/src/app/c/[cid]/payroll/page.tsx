"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { ErrorNotice, Field, Loading } from "@/components/bits";
import { MonthGrid } from "@/components/month-grid";
import { RunTable } from "@/components/run-table";
import { useCompany } from "@/components/shell";
import { api } from "@/lib/api";
import type { Company, Period, Run, RulesStatus } from "@/lib/types";
import { useData } from "@/lib/use-data";

export default function Payroll() {
  const { companyId, canEdit } = useCompany();
  const { data, error, loading } = useData<Run[]>(`/companies/${companyId}/payroll-runs`);
  const company = useData<Company>(`/companies/${companyId}`);

  return (
    <div className="stack">
      <header className="page-head">
        <div>
          <h1>Payroll</h1>
          <p>
            One run per {company.data?.pay_calendar === "ad" ? "English month (July twice a year, split at Shrawan 1)" : "Nepali month"}.
            Finalize in order: each month’s TDS builds on the ones before it.
          </p>
        </div>
      </header>

      <YearGrid companyId={companyId} runs={data} canStart={canEdit} />

      {canEdit && company.data && <StartRun company={company.data} />}

      <section className="sheet">
        <h2>All runs</h2>
        {loading && <Loading what="payroll runs" />}
        <ErrorNotice error={error} />
        {data && data.length === 0 && <p className="muted">No payroll runs yet.</p>}
        {data && data.length > 0 && <RunTable runs={data} base={`/c/${companyId}`} />}
      </section>
    </div>
  );
}

function YearGrid({ companyId, runs, canStart }: { companyId: number; runs: Run[] | null; canStart: boolean }) {
  const rules = useData<RulesStatus>("/rules/status");
  const years = [...new Set([...(runs ?? []).map((r) => r.fiscal_year), ...(rules.data?.all ?? []).map((r) => r.fiscal_year)])].sort().reverse();
  const [picked, setPicked] = useState<string | null>(null);
  const fy = picked ?? runs?.[0]?.fiscal_year ?? rules.data?.current?.fiscal_year ?? null;
  if (!fy) return null;
  return (
    <section className="sheet">
      <div className="spread" style={{ marginBottom: 16 }}>
        <h2>FY {fy}</h2>
        <select aria-label="Fiscal year" value={fy} onChange={(e) => setPicked(e.target.value)}>
          {years.map((y) => <option key={y} value={y}>FY {y}</option>)}
        </select>
      </div>
      <MonthGrid companyId={companyId} fiscalYear={fy} canStart={canStart} />
    </section>
  );
}

function StartRun({ company }: { company: Company }) {
  const router = useRouter();
  const ad = company.pay_calendar === "ad";
  const rules = useData<RulesStatus>(ad ? "/rules/status" : null);
  const years = (rules.data?.all ?? []).map((r) => r.fiscal_year).reverse();
  const [picked, setPicked] = useState<string | null>(null);
  const fy = picked ?? rules.data?.current?.fiscal_year ?? years[0] ?? null;
  const ps = useData<Period[]>(ad && fy ? `/companies/${company.id}/payroll-runs/periods/${fy.replace("/", "-")}` : null);
  const open = ps.data?.filter((p) => !p.run_id) ?? [];
  const [error, setError] = useState<unknown>(null);

  async function create(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = Object.fromEntries(new FormData(e.currentTarget)) as Record<string, string>;
    try {
      const run = await api<Run>(`/companies/${company.id}/payroll-runs`, {
        method: "POST",
        json: ad ? { payment_date: f.payment_date, fiscal_year: fy, period: Number(f.period) } : { payment_date: f.payment_date },
      });
      router.push(`/c/${company.id}/payroll/${run.id}`);
    } catch (err) {
      setError(err);
    }
  }

  return (
    <form className="sheet" onSubmit={create}>
      <h2>Start a month</h2>
      <p className="small muted" style={{ margin: "0.3rem 0 0.9rem" }}>
        {ad
          ? "Pick the period, then the date salary is paid. Foreign-currency pay uses the NRB rate on the payment date."
          : "The payment date decides the fiscal year and month, and which exchange rate applies to foreign-currency pay."}
        {" "}For months paid before you started using AutoTax, start the month and enter its figures instead of calculating.
      </p>
      <ErrorNotice error={error} />
      <div className="row" style={{ alignItems: "flex-end" }}>
        {ad && (
          <>
            <Field label="Fiscal year">
              <select value={fy ?? ""} onChange={(e) => setPicked(e.target.value)}>
                {years.map((y) => <option key={y} value={y}>{y}</option>)}
              </select>
            </Field>
            <Field label="Period">
              <select name="period" required disabled={!open.length}>
                {open.map((p) => <option key={p.index} value={p.index}>{p.label}</option>)}
              </select>
            </Field>
          </>
        )}
        <Field label="Salary payment date"><input type="date" name="payment_date" required /></Field>
        <button className="btn" disabled={ad && !open.length}>Start payroll</button>
      </div>
      {ad && ps.data && !open.length && <p className="small muted" style={{ marginTop: "0.5rem" }}>Every period of FY {fy} has a run.</p>}
    </form>
  );
}
