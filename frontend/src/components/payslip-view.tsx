"use client";

import { Printer } from "lucide-react";
import { useState } from "react";

import { Num } from "@/components/bits";
import { date, KIND_LABEL, money } from "@/lib/format";
import { cents, fromCents, fromNprCents, sumCents, toNprCents } from "@/lib/money";
import type { PayslipDetail, TraceStep } from "@/lib/types";

import styles from "./trace.module.css";

const TOTALS = new Set(["Assessable income", "Taxable income", "Annual tax liability", "TDS this month", "Net pay"]);
const STATUS_LABEL = { verified: "verified", corroborated: "not yet verified", needs_review: "needs review" } as const;

type Row = { label: string; note?: string; npr: bigint; foreign?: bigint };

/**
 * A payslip as employees know it: details, Addition | Deduction, net salary. Amounts can be
 * shown in the pay currency (e.g. USD) or in Nepali rupees. The full tax working sits below.
 * Shared by HR and the employee's own view.
 */
export function PayslipView({ p, back, picker }: { p: PayslipDetail; back?: React.ReactNode; picker?: React.ReactNode }) {
  const fx = Object.entries(p.inputs.fx ?? {})[0]; // the pay currency, if not NPR
  const [view, setView] = useState<"foreign" | "npr">(fx ? "foreign" : "npr");
  const showForeign = Boolean(fx) && view === "foreign";
  const cur = showForeign ? fx![0] : "NPR";

  const { additions, deductions } = payLines(p);
  const shown = (r: Row) => fromCents(showForeign ? (r.foreign ?? fromNprCents(r.npr, fx![1].buy, fx![1].unit)) : r.npr);
  const totalAdd = sumCents(additions.map((r) => cents(shown(r))));
  const totalDed = sumCents(deductions.map((r) => cents(shown(r))));
  const deferred = p.tds === "0.00" && p.tds_starts && p.inputs.tds_withheld === false;

  return (
    <div className="stack">
      <header className="page-head no-print">
        <div>
          {back && <p className="small">{back}</p>}
          <h1>Payslip</h1>
        </div>
        <div className="row">
          {fx && (
            <div className="seg" role="tablist" aria-label="Show amounts in">
              <button type="button" role="tab" aria-selected={view === "foreign"} onClick={() => setView("foreign")}>{fx[0] === "USD" ? "Dollar" : fx[0]}</button>
              <button type="button" role="tab" aria-selected={view === "npr"} onClick={() => setView("npr")}>Nepali rupees</button>
            </div>
          )}
          <button type="button" className="btn quiet" onClick={() => window.print()}><Printer />Print</button>
        </div>
      </header>

      {picker}

      <article className={`sheet ${styles.slip}`}>
        <div className={styles.slipHead}>
          <div>
            <h2 className={styles.slipTitle}>Payslip for {p.month_label}</h2>
            <p className="muted">
              Fiscal year {p.fiscal_year}, paid on {date(p.payment_date)}
              {p.run_status === "draft" && <span className="tag corroborated" style={{ marginLeft: 8 }}>Draft, not final</span>}
            </p>
          </div>
          <div className={styles.slipNet}>
            <span>Net salary</span>
            <strong>{cur} {money(fromCents(totalAdd - totalDed))}</strong>
          </div>
        </div>

        <dl className={styles.details}>
          <Detail label="Employee ID" value={p.employee.code} />
          <Detail label="Employee name" value={p.employee.name} />
          <Detail label="Marital status" value={p.employee.marital_status} />
          <Detail label="Department" value={p.employee.department} />
          <Detail label="CIT no." value={p.employee.cit_number} />
          <Detail label="Bank A/c no." value={p.employee.bank_account} />
          <Detail label="SSF no." value={p.employee.ssf_number} />
          <Detail label="Date of joining" value={date(p.employee.joined_on)} />
          <Detail label="Designation" value={p.employee.designation} />
          <Detail label="PAN no." value={p.employee.pan} />
          <Detail label="Exchange rate" value={fx ? `Rs ${money(fx[1].buy, 2)} per ${fx[1].unit} ${fx[0]}` : "Paid in Nepali rupees"}
            sub={fx ? `${fx[1].source === "OVERRIDE" ? "Bank rate" : "NRB buying rate"}, ${date(fx[1].on)}` : undefined} />
          {p.share && <Detail label="Days paid" value={`${p.inputs.period?.days_paid} of ${p.inputs.period?.month_days}`} />}
        </dl>

        <div className={styles.columns}>
          <Column title="Addition" rows={additions} shown={shown} total={totalAdd} totalLabel="Total addition" />
          <Column title="Deduction" rows={deductions} shown={shown} total={totalDed} totalLabel="Total deduction" />
        </div>
        <div className={styles.netRow}>
          <span>Net salary</span>
          <strong>{cur} {money(fromCents(totalAdd - totalDed))}</strong>
        </div>

        {(deferred || showForeign) && (
          <div className={styles.slipNotes}>
            {deferred && (
              <p className="notice small">
                No remuneration tax was withheld this month: your company starts withholding in <strong>{p.tds_starts}</strong>.
                This year’s tax (about Rs {money(p.projected_annual_tax)} so far) is then spread over the remaining months.
              </p>
            )}
            {showForeign && (
              <p className="small faint">Amounts in {fx![0]} are converted from rupees at the rate above. Tax is always worked out in rupees.</p>
            )}
          </div>
        )}
      </article>

      <details className="sheet no-print">
        <summary className={styles.workingSummary}>How the tax was worked out</summary>
        <Working p={p} />
      </details>
    </div>
  );
}

function Detail({ label, value, sub }: { label: string; value: string | null | undefined; sub?: string }) {
  return (
    <div>
      <dt>{label}</dt>
      <dd>{value || <span className="faint">Not recorded</span>}{sub && <span className={styles.detailSub}>{sub}</span>}</dd>
    </div>
  );
}

function Column({ title, rows, shown, total, totalLabel }: {
  title: string;
  rows: Row[];
  shown: (r: Row) => string;
  total: bigint;
  totalLabel: string;
}) {
  return (
    <table className={`ledger ${styles.col}`}>
      <thead><tr><th colSpan={2}>{title}</th></tr></thead>
      <tbody>
        {rows.map((r) => (
          <tr key={r.label}>
            <td>{r.label}{r.note && <span className="faint small"> {r.note}</span>}</td>
            <td className="num"><Num v={shown(r)} /></td>
          </tr>
        ))}
      </tbody>
      <tfoot><tr><td>{totalLabel}</td><td className="num"><Num v={fromCents(total)} /></td></tr></tfoot>
    </table>
  );
}

/** Split the payslip into the Addition and Deduction lines employees expect. */
function payLines(p: PayslipDetail): { additions: Row[]; deductions: Row[] } {
  const fxEntry = Object.entries(p.inputs.fx ?? {});
  const rates = Object.fromEntries(fxEntry);
  const [num, den] = (p.share ?? "1/1").split("/").map(Number);
  const additions: Row[] = [];
  for (const l of p.inputs.lines ?? []) {
    const share: [number, number] = l.recurring ? [num, den] : [1, 1];
    const amt = cents(l.amount);
    const r = rates[l.currency];
    const npr = r ? toNprCents(amt, r.buy, r.unit, share) : toNprCents(amt, "1", 1, share);
    const foreign = r ? toNprCents(amt, "1", 1, share) : undefined; // same currency: exact, no reconversion
    const label = l.description ? capitalise(l.description) : KIND_LABEL[l.kind] ?? l.kind;
    additions.push({ label: uniqueLabel(additions, label), npr, foreign });
  }
  if (!additions.length) additions.push({ label: "Gross pay", note: "(entered from earlier payroll)", npr: cents(p.gross) });
  // Line conversions are rounded one by one; settle any paisa difference on the largest line.
  const grossDiff = cents(p.gross) - sumCents(additions.map((a) => a.npr));
  if (grossDiff !== BigInt(0) && additions.length) {
    const big = additions.reduce((a, b) => (b.npr > a.npr ? b : a));
    big.npr += grossDiff;
  }
  if (p.ssf_employer !== "0.00") additions.push({ label: "SSF 20%", note: "(employer)", npr: cents(p.ssf_employer) });

  const deductions: Row[] = [];
  const ssfTotal = cents(p.ssf_employee) + cents(p.ssf_employer);
  if (ssfTotal !== BigInt(0)) deductions.push({ label: "SSF 31%", note: "(11% you + 20% employer)", npr: ssfTotal });
  if (p.cit !== "0.00") deductions.push({ label: "CIT contribution", npr: cents(p.cit) });
  if (p.other_retirement !== "0.00") deductions.push({ label: "Retirement fund", npr: cents(p.other_retirement) });
  deductions.push({ label: "Remuneration tax", note: "(TDS)", npr: cents(p.tds) });
  return { additions, deductions };
}

function capitalise(s: string): string {
  return s.charAt(0).toUpperCase() + s.slice(1);
}

function uniqueLabel(rows: Row[], label: string): string {
  let l = label;
  for (let n = 2; rows.some((r) => r.label === l); n++) l = `${label} (${n})`;
  return l;
}

function Working({ p }: { p: PayslipDetail }) {
  const month: TraceStep[] = [];
  const annual: TraceStep[] = [];
  const withholding: TraceStep[] = [];
  for (const s of p.trace) {
    if (s.label.startsWith("  [annual] ")) annual.push({ ...s, label: s.label.replace("  [annual] ", "") });
    else if (s.label === "TDS this month" || s.label === "Net pay") withholding.push(s);
    else month.push(s);
  }
  return (
    <div style={{ marginTop: 12 }}>
      <p className="small muted">
        Worked out with {p.inputs.rule_set ?? "figures entered from earlier payroll"}. Every line shows its calculation and the provision it comes from.
      </p>
      <Ledger title="This month" steps={month} />
      <Ledger title="Projected for the whole year" steps={annual} note="TDS is spread so the year’s total matches the annual liability. The last month settles any difference." />
      <Ledger title="Withheld this month" steps={withholding} />
    </div>
  );
}

function Ledger({ title, steps, note }: { title: string; steps: TraceStep[]; note?: string }) {
  if (!steps.length) return null;
  return (
    <div className={styles.block}>
      <h3>{title}</h3>
      {note && <p className="small muted">{note}</p>}
      <ol className={styles.ledger}>
        {steps.map((s, i) => (
          <li key={i} className={TOTALS.has(s.label) ? styles.total : undefined}>
            <div className={styles.line}>
              <span className={styles.label}>{s.label}</span>
              <span className={styles.amount}><Num v={s.amount} /></span>
            </div>
            {(s.detail || s.citation) && (
              <div className={styles.working}>
                {s.detail && <span className={styles.detail}>{s.detail}</span>}
                {s.citation && (
                  <cite className={`${styles.cite} ${styles[s.citation.status]}`} title={s.citation.source}>
                    {s.citation.ref}
                    <span>{s.citation.source}, {STATUS_LABEL[s.citation.status]}</span>
                  </cite>
                )}
              </div>
            )}
          </li>
        ))}
      </ol>
    </div>
  );
}
