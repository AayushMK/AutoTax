"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { Suspense, useState } from "react";

import { ErrorNotice, Field, Loading, Num } from "@/components/bits";
import { UnverifiedList } from "@/components/rule-status";
import { useCompany } from "@/components/shell";
import { Stamp } from "@/components/stamp";
import { api, ApiError, download } from "@/lib/api";
import { date, dateTime, KIND_LABEL } from "@/lib/format";
import type { Employee, RunDetail } from "@/lib/types";
import { useData } from "@/lib/use-data";

export default function Page() {
  return (
    <Suspense fallback={<Loading what="payroll run" />}>
      <RunPage />
    </Suspense>
  );
}

function RunPage() {
  const { rid } = useParams<{ rid: string }>();
  const { companyId, canEdit } = useCompany();
  const path = `/companies/${companyId}/payroll-runs/${rid}`;
  const { data: run, setData, error } = useData<RunDetail>(path);
  const employees = useData<Employee[]>(`/companies/${companyId}/employees`);
  const [busy, setBusy] = useState<"compute" | "finalize" | null>(null);
  const [actionError, setActionError] = useState<unknown>(null);
  const [confirming, setConfirming] = useState<ApiError | null>(null);
  const [ack, setAck] = useState(false);

  if (error) return <ErrorNotice error={error} />;
  if (!run) return <Loading what="payroll run" />;

  const draft = run.status === "draft";
  const editable = draft && canEdit;
  const names = new Map(employees.data?.map((e) => [e.id, `${e.code} ${e.name}`]));

  async function act(kind: "compute" | "finalize", acknowledge = false) {
    setBusy(kind);
    setActionError(null);
    try {
      const body = kind === "finalize" ? { json: { acknowledge_unverified: acknowledge } } : {};
      setData(await api<RunDetail>(`${path}/${kind}`, { method: "POST", ...body }));
      setConfirming(null);
      setAck(false);
    } catch (err) {
      if (err instanceof ApiError && err.code === "rules_unverified") setConfirming(err);
      else setActionError(err);
    } finally {
      setBusy(null);
    }
  }

  async function reloadRun() {
    setData(await api<RunDetail>(path));
  }

  return (
    <div className="stack">
      <header className="page-head">
        <div>
          <p className="small"><Link href={`/c/${companyId}/payroll`}>Payroll</Link></p>
          <h1>{run.month_label}</h1>
          <p>
            Paid on {date(run.payment_date)}, fiscal year {run.fiscal_year}.
            {run.rule_set && <> Calculated with {run.rule_set}.</>}
          </p>
        </div>
        {run.status === "finalized" ? (
          <Stamp tone="moss" title="Finalized" note={dateTime(run.finalized_at)} />
        ) : (
          editable && (
            <div className="row">
              <button className="btn quiet" disabled={busy !== null} onClick={() => act("compute")}>
                {busy === "compute" ? "Calculating…" : run.computed_at ? "Recalculate" : "Calculate payroll"}
              </button>
              <button className="btn seal" disabled={busy !== null || !run.computed_at} onClick={() => act("finalize")}
                title={run.computed_at ? undefined : "Calculate first"}>
                {busy === "finalize" ? "Finalizing…" : "Finalize month"}
              </button>
            </div>
          )
        )}
      </header>

      <ErrorNotice error={actionError} />

      {confirming && (
        <section className="sheet" style={{ borderColor: "var(--seal)" }} role="alertdialog" aria-labelledby="ack-title">
          <h2 id="ack-title">These tax values haven’t been verified yet</h2>
          <p className="muted" style={{ marginTop: "0.4rem" }}>
            {(confirming.detail as { rule_set?: string })?.rule_set} still has values that no CA has checked against the Finance Act.
            Finalizing records that you accepted them for this month.
          </p>
          <UnverifiedList params={confirming.problems} />
          <label className="check" style={{ marginTop: "1rem" }}>
            <input type="checkbox" checked={ack} onChange={(e) => setAck(e.target.checked)} />
            <span>I accept these values for {run.month_label} and understand finalized payslips can’t be changed.</span>
          </label>
          <div className="form-actions">
            <button className="btn seal" disabled={!ack || busy !== null} onClick={() => act("finalize", true)}>
              Finalize {run.month_label}
            </button>
            <button className="btn quiet" onClick={() => setConfirming(null)}>Not now</button>
          </div>
        </section>
      )}

      {run.acknowledged_unverified.length > 0 && (
        <p className="notice small">
          Finalized with {run.acknowledged_unverified.length} rule values that were not yet verified. This is recorded in the activity log.
        </p>
      )}

      {draft && run.adjustments.length + (editable ? 1 : 0) > 0 && (
        <Adjustments run={run} path={path} employees={employees.data ?? []} names={names} editable={editable} onChange={reloadRun} />
      )}

      <section className="sheet">
        <div className="spread" style={{ marginBottom: "0.75rem" }}>
          <h2>Payslips</h2>
          {run.payslips.length > 0 && (
            <button className="btn quiet small" onClick={() => download(`${path}/tds.csv`, `tds-${run.fiscal_year.replace("/", "-")}-m${run.month}.csv`)}>
              Download TDS sheet (CSV)
            </button>
          )}
        </div>
        {draft && !run.computed_at && run.payslips.length === 0 && (
          <div className="empty"><p>Nothing calculated yet. Add any one-off payments, then calculate.</p></div>
        )}
        {draft && !run.computed_at && run.payslips.length > 0 && (
          <p className="notice small" style={{ marginBottom: "0.75rem" }}>Inputs changed since the last calculation. Recalculate before finalizing.</p>
        )}
        {run.payslips.length > 0 && (
          <div className="table-scroll">
            <table className="ledger">
              <thead>
                <tr>
                  <th>Employee</th>
                  <th className="num">Gross (NPR)</th>
                  <th className="num">SSF 11%</th>
                  <th className="num">CIT</th>
                  <th className="num">TDS</th>
                  <th className="num">Net pay</th>
                  <th className="num">Employer SSF 20%</th>
                </tr>
              </thead>
              <tbody>
                {run.payslips.map((p) => (
                  <tr key={p.id}>
                    <td>
                      <Link href={`/c/${companyId}/payroll/${run.id}/payslips/${p.id}`}>{p.employee_name}</Link>{" "}
                      <span className="faint small figure">{p.employee_code}</span>
                    </td>
                    <td className="num"><Num v={p.gross} /></td>
                    <td className="num"><Num v={p.ssf_employee} /></td>
                    <td className="num"><Num v={p.cit} /></td>
                    <td className="num"><strong><Num v={p.tds} /></strong></td>
                    <td className="num"><Num v={p.net_pay} /></td>
                    <td className="num faint"><Num v={p.ssf_employer} /></td>
                  </tr>
                ))}
              </tbody>
              <tfoot>
                <tr>
                  <td>Total, {run.payslips.length} employees</td>
                  <td className="num"><Num v={run.totals.gross} /></td>
                  <td className="num"><Num v={run.totals.ssf_employee} /></td>
                  <td className="num"><Num v={run.totals.cit} /></td>
                  <td className="num"><Num v={run.totals.tds} /></td>
                  <td className="num"><Num v={run.totals.net_pay} /></td>
                  <td className="num"><Num v={run.totals.ssf_employer} /></td>
                </tr>
              </tfoot>
            </table>
          </div>
        )}
        {run.warnings.length > 0 && draft && (
          <ul className="small muted" style={{ marginTop: "1rem", paddingLeft: "1.1rem" }}>
            {run.warnings.map((w) => <li key={w}>{w}</li>)}
          </ul>
        )}
      </section>
    </div>
  );
}

function Adjustments({ run, path, employees, names, editable, onChange }: {
  run: RunDetail;
  path: string;
  employees: Employee[];
  names: Map<number, string>;
  editable: boolean;
  onChange: () => void;
}) {
  const [error, setError] = useState<unknown>(null);

  async function add(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = e.currentTarget;
    const f = Object.fromEntries(new FormData(form)) as Record<string, string>;
    try {
      await api(`${path}/adjustments`, {
        method: "POST",
        json: { ...f, employee_id: Number(f.employee_id), amount: f.amount.replace(/,/g, "") },
      });
      form.reset();
      setError(null);
      onChange();
    } catch (err) {
      setError(err);
    }
  }

  async function remove(id: number) {
    await api(`${path}/adjustments/${id}`, { method: "DELETE" });
    onChange();
  }

  return (
    <section className="sheet">
      <h2>One-off payments this month</h2>
      <p className="small muted" style={{ margin: "0.3rem 0 0.9rem" }}>
        Bonuses, Dashain allowance, arrears. They’re taxed this month and not projected into later months.
      </p>
      <ErrorNotice error={error} />
      {run.adjustments.length > 0 && (
        <table className="ledger" style={{ marginBottom: "1rem" }}>
          <tbody>
            {run.adjustments.map((a) => (
              <tr key={a.id}>
                <td>{names.get(a.employee_id) ?? `#${a.employee_id}`}</td>
                <td>{KIND_LABEL[a.kind] ?? a.kind}{a.description && <span className="faint small"> ({a.description})</span>}</td>
                <td className="num">{a.currency} <Num v={a.amount} /></td>
                <td style={{ width: 1 }}>{editable && <button className="btn quiet small" onClick={() => remove(a.id)}>Remove</button>}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {editable && (
        <form onSubmit={add} className="form-grid" style={{ alignItems: "end" }}>
          <Field label="Employee">
            <select name="employee_id" required>
              {employees.map((e) => <option key={e.id} value={e.id}>{e.code} {e.name}</option>)}
            </select>
          </Field>
          <Field label="Type">
            <select name="kind" defaultValue="dashain">
              {["dashain", "bonus", "overtime", "allowance", "other"].map((k) => <option key={k} value={k}>{KIND_LABEL[k]}</option>)}
            </select>
          </Field>
          <Field label="Amount"><input name="amount" required inputMode="decimal" className="figure" /></Field>
          <Field label="Currency">
            <select name="currency" defaultValue="NPR">{["NPR", "USD", "EUR", "GBP", "AUD", "INR"].map((c) => <option key={c}>{c}</option>)}</select>
          </Field>
          <Field label="Note"><input name="description" /></Field>
          <div><button className="btn quiet">Add payment</button></div>
        </form>
      )}
    </section>
  );
}
