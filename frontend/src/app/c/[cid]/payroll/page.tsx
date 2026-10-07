"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { ErrorNotice, Field, Loading } from "@/components/bits";
import { RunTable } from "@/components/run-table";
import { useCompany } from "@/components/shell";
import { api } from "@/lib/api";
import type { Run } from "@/lib/types";
import { useData } from "@/lib/use-data";

export default function Payroll() {
  const { companyId, canEdit } = useCompany();
  const router = useRouter();
  const { data, error, loading } = useData<Run[]>(`/companies/${companyId}/payroll-runs`);
  const [createError, setCreateError] = useState<unknown>(null);

  async function create(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const payment_date = new FormData(e.currentTarget).get("payment_date");
    try {
      const run = await api<Run>(`/companies/${companyId}/payroll-runs`, { method: "POST", json: { payment_date } });
      router.push(`/c/${companyId}/payroll/${run.id}`);
    } catch (err) {
      setCreateError(err);
    }
  }

  return (
    <div className="stack">
      <header className="page-head">
        <div>
          <h1>Payroll</h1>
          <p>One run per Nepali month. Finalize months in order: each month’s TDS builds on the ones before it.</p>
        </div>
      </header>

      {canEdit && (
        <form className="sheet" onSubmit={create}>
          <h2>Start a month</h2>
          <p className="small muted" style={{ margin: "0.3rem 0 0.9rem" }}>
            The payment date decides the fiscal year and month, and which exchange rate applies to foreign-currency pay.
          </p>
          <ErrorNotice error={createError} />
          <div className="row" style={{ alignItems: "flex-end" }}>
            <Field label="Salary payment date"><input type="date" name="payment_date" required /></Field>
            <button className="btn">Start payroll</button>
          </div>
        </form>
      )}

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
