"use client";

import Link from "next/link";

import { ErrorNotice, Loading } from "@/components/bits";
import { RuleStamp, UnverifiedList } from "@/components/rule-status";
import { RunTable } from "@/components/run-table";
import { useCompany } from "@/components/shell";
import { date } from "@/lib/format";
import type { Employee, Run, RulesStatus } from "@/lib/types";
import { useData } from "@/lib/use-data";

export default function Overview() {
  const { companyId, companyName } = useCompany();
  const rules = useData<RulesStatus>("/rules/status");
  const runs = useData<Run[]>(`/companies/${companyId}/payroll-runs`);
  const employees = useData<Employee[]>(`/companies/${companyId}/employees`);
  const base = `/c/${companyId}`;
  const draft = runs.data?.find((r) => r.status === "draft");

  return (
    <div className="stack">
      <header className="page-head">
        <div>
          <h1>{companyName ?? "\u00a0"}</h1>
          <p>
            {employees.data ? `${employees.data.length} employees.` : "…"}
            {runs.data?.[0] && ` Last payroll: ${runs.data[0].month_label}.`}
          </p>
        </div>
        {draft ? (
          <Link className="btn" href={`${base}/payroll/${draft.id}`}>Continue {draft.month_label} payroll</Link>
        ) : (
          <Link className="btn" href={`${base}/payroll`}>Run payroll</Link>
        )}
      </header>

      <section className="sheet">
        <div className="spread">
          <div style={{ maxWidth: "60ch" }}>
            <h2>Tax rules</h2>
            {rules.loading && <Loading what="rules" />}
            <ErrorNotice error={rules.error} />
            {rules.data?.current && (
              <p className="muted" style={{ marginTop: "0.5rem" }}>
                {rules.data.current.version} applies from {date(rules.data.current.effective_from)} to{" "}
                {date(rules.data.current.effective_to)}.
                {rules.data.current.unverified_params.length > 0 &&
                  " You can run payroll, but finalizing asks you to accept these values until a CA marks them verified:"}
              </p>
            )}
          </div>
          {rules.data && <RuleStamp status={rules.data} />}
        </div>
        {rules.data?.current && rules.data.current.unverified_params.length > 0 && (
          <UnverifiedList params={rules.data.current.unverified_params} />
        )}
        {rules.data?.alert && <div className="notice block" style={{ marginTop: "1rem" }}>{rules.data.alert}</div>}
      </section>

      <section className="sheet">
        <div className="spread" style={{ marginBottom: "0.75rem" }}>
          <h2>Payroll runs</h2>
          <Link href={`${base}/payroll`}>All runs</Link>
        </div>
        {runs.loading && <Loading what="payroll runs" />}
        <ErrorNotice error={runs.error} />
        {runs.data && runs.data.length === 0 && (
          <div className="empty">
            <p>No payroll yet. Add your employees, then run the first month.</p>
            <Link className="btn quiet" href={`${base}/employees`}>Add employees</Link>
          </div>
        )}
        {runs.data && runs.data.length > 0 && <RunTable runs={runs.data.slice(0, 6)} base={base} />}
      </section>
    </div>
  );
}
