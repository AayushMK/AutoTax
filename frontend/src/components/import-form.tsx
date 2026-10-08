"use client";

import { useState } from "react";

import { api } from "@/lib/api";
import { addMoney } from "@/lib/format";
import type { Employee, RunDetail } from "@/lib/types";

import { ErrorNotice } from "./bits";

type Row = { gross: string; ssf_total: string; cit: string; tds: string };
const EMPTY: Row = { gross: "", ssf_total: "", cit: "", tds: "" };
const COLS: (keyof Row)[] = ["gross", "ssf_total", "cit", "tds"];

/** Enter a month that was paid before the company used AutoTax: one row per employee. */
export function ImportForm({ run, path, employees, onSaved, onCancel }: {
  run: RunDetail;
  path: string;
  employees: Employee[];
  onSaved: (r: RunDetail) => void;
  onCancel?: () => void;
}) {
  const inService = employees.filter((e) => e.joined_on <= run.period_end && (!e.left_on || e.left_on >= run.period_start));
  const existing = new Map(run.payslips.map((p) => [p.employee_id, p]));
  const [rows, setRows] = useState<Record<number, Row>>(() =>
    Object.fromEntries(inService.map((e) => {
      const p = existing.get(e.id);
      return [e.id, p ? { gross: p.gross, ssf_total: addMoney(p.ssf_employee, p.ssf_employer), cit: p.cit, tds: p.tds } : EMPTY];
    })),
  );
  // Saved payslips already exclude the employer's 20%, so re-editing them starts unticked.
  const [includesEmployer, setIncludesEmployer] = useState(run.payslips.length === 0);
  const [paste, setPaste] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  function applyPaste() {
    // Accepts rows copied from Excel: code, gross, SSF (31%), CIT, TDS (tabs or commas).
    const byCode = new Map(inService.map((e) => [e.code.toLowerCase(), e.id]));
    const next = { ...rows };
    const unknown: string[] = [];
    for (const line of paste.split(/\r?\n/).filter((l) => l.trim())) {
      const [code, ...vals] = line.split(/\t|,(?=\s*[\d.-])/).map((v) => v.trim());
      const id = byCode.get(code.toLowerCase());
      if (!id) {
        unknown.push(code);
        continue;
      }
      next[id] = Object.fromEntries(COLS.map((c, i) => [c, (vals[i] ?? "").replace(/,/g, "")])) as Row;
    }
    setRows(next);
    setError(unknown.length ? new Error(`Not found: ${unknown.join(", ")}. Use employee codes in the first column.`) : null);
  }

  async function save() {
    setBusy(true);
    try {
      const payload = Object.entries(rows)
        .filter(([, r]) => r.gross.trim())
        .map(([id, r]) => ({
          employee_id: Number(id),
          gross: r.gross.replace(/,/g, ""),
          ssf_total: r.ssf_total.replace(/,/g, "") || "0",
          cit: r.cit.replace(/,/g, "") || "0",
          tds: r.tds.replace(/,/g, "") || "0",
        }));
      onSaved(await api<RunDetail>(`${path}/import`, {
        method: "PUT",
        json: { gross_includes_employer_ssf: includesEmployer, rows: payload },
      }));
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="sheet">
      <h2>Figures from your previous payroll</h2>
      <p className="small muted" style={{ margin: "0.3rem 0 0.9rem" }}>
        For {run.month_label}, paid before you used AutoTax. These become the history later months build on, so tax not
        withheld here is caught up in the coming months. SSF is the full 31% (11% employee + 20% employer); it’s split for you.
      </p>
      <ErrorNotice error={error} />
      <label className="check" style={{ marginBottom: "0.9rem" }}>
        <input type="checkbox" checked={includesEmployer} onChange={(e) => setIncludesEmployer(e.target.checked)} />
        <span>Gross includes the employer’s 20% SSF (cost to company), as in most salary sheets</span>
      </label>
      <div className="table-scroll">
        <table className="ledger">
          <thead>
            <tr><th>Employee</th><th className="num">Gross</th><th className="num">SSF 31%</th><th className="num">CIT</th><th className="num">TDS</th></tr>
          </thead>
          <tbody>
            {inService.map((e) => (
              <tr key={e.id}>
                <td style={{ whiteSpace: "nowrap" }}>{e.name} <span className="faint small figure">{e.code}</span></td>
                {COLS.map((c) => (
                  <td key={c}>
                    <input aria-label={`${e.name} ${c}`} inputMode="decimal" className="figure" style={{ width: "100%", textAlign: "right" }}
                      value={rows[e.id]?.[c] ?? ""} onChange={(ev) => setRows({ ...rows, [e.id]: { ...rows[e.id], [c]: ev.target.value } })} />
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <details style={{ marginTop: "1rem" }}>
        <summary className="small">Paste rows from a spreadsheet</summary>
        <p className="small muted" style={{ margin: "0.5rem 0" }}>One employee per line: code, gross, SSF 31%, CIT, TDS. Copy straight from Excel.</p>
        <textarea rows={4} style={{ width: "100%" }} className="figure" value={paste} onChange={(e) => setPaste(e.target.value)} />
        <button type="button" className="btn quiet small" onClick={applyPaste} disabled={!paste.trim()}>Fill the table</button>
      </details>
      <div className="form-actions">
        <button className="btn" onClick={save} disabled={busy}>{busy ? "Saving…" : "Save figures"}</button>
        {onCancel && <button className="btn quiet" onClick={onCancel}>Cancel</button>}
        <span className="small muted">Employees left blank are not included in this month.</span>
      </div>
    </section>
  );
}
