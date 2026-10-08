"use client";

import { Num } from "@/components/bits";
import { KIND_LABEL, money } from "@/lib/format";
import type { PayslipDetail, TraceStep } from "@/lib/types";

import styles from "./trace.module.css";

const TOTALS = new Set(["Assessable income", "Taxable income", "Annual tax liability", "TDS this month", "Net pay"]);
const STATUS_LABEL = { verified: "verified", corroborated: "not yet verified", needs_review: "needs review" } as const;

/** A payslip with its full worked calculation. Shared by HR and the employee's own view. */
export function PayslipView({ p, monthLabel, back }: { p: PayslipDetail; monthLabel: string; back: React.ReactNode }) {
  const month: TraceStep[] = [];
  const annual: TraceStep[] = [];
  const withholding: TraceStep[] = [];
  for (const s of p.trace) {
    if (s.label.startsWith("  [annual] ")) annual.push({ ...s, label: s.label.replace("  [annual] ", "") });
    else if (s.label === "TDS this month" || s.label === "Net pay") withholding.push(s);
    else month.push(s);
  }

  return (
    <div className="stack">
      <header className="page-head">
        <div>
          <p className="small">{back}</p>
          <h1>{p.employee_name}</h1>
          <p>
            Payslip for {monthLabel}, worked out with {p.inputs.rule_set}. Every line shows its
            calculation and the provision it comes from.
          </p>
        </div>
        <dl className={styles.headline}>
          <div><dt>Net pay</dt><dd><Num v={p.net_pay} /></dd></div>
          <div><dt>TDS</dt><dd><Num v={p.tds} /></dd></div>
        </dl>
      </header>
      {(p.share || (p.projected_tax_without_cit && p.projected_annual_tax !== "0.00" && p.projected_tax_without_cit !== p.projected_annual_tax)) && (
        <p className="notice small">
          {p.share && <>Paid for {p.inputs.period?.days_paid} of {p.inputs.period?.month_days} days of the month. </>}
          {p.projected_tax_without_cit !== p.projected_annual_tax && p.projected_annual_tax !== "0.00" && (
            <>Without CIT, this year’s tax would be {money(p.projected_tax_without_cit)} instead of {money(p.projected_annual_tax)}.</>
          )}
        </p>
      )}

      <section className="sheet">
        <h2>Pay this month</h2>
        <table className="ledger" style={{ marginTop: "0.5rem" }}>
          <tbody>
            {p.inputs.lines.map((l, i) => (
              <tr key={i}>
                <td>
                  {KIND_LABEL[l.kind] ?? l.kind}
                  {!l.recurring && <span className="tag" style={{ marginLeft: "0.5rem" }}>one-off</span>}
                  {l.description && <span className="faint small"> ({l.description})</span>}
                </td>
                <td className="num">{l.currency} <Num v={l.amount} /></td>
              </tr>
            ))}
          </tbody>
        </table>
        {Object.entries(p.inputs.fx).map(([cur, r]) => (
          <p key={cur} className="small muted" style={{ marginTop: "0.6rem" }}>
            {cur} converted at {r.source === "OVERRIDE" ? "the company’s recorded bank rate" : "the NRB buying rate"} of{" "}
            <span className="figure">{money(r.buy, 4)}</span> per {r.unit} {cur} on {r.on}
            {r.override_reason && <>: {r.override_reason}</>}.
          </p>
        ))}
      </section>

      <section className="sheet">
        <h2>How the tax was worked out</h2>
        <Ledger title="This month" steps={month} />
        <Ledger title="Projected for the whole year" steps={annual} note="TDS is spread so the year’s total matches the annual liability. The last month settles any difference." />
        <Ledger title="Withheld this month" steps={withholding} />
      </section>
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
