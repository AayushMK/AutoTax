"use client";

import { useState } from "react";

import { ErrorNotice, Field, Loading } from "@/components/bits";
import { useCompany } from "@/components/shell";
import { api } from "@/lib/api";
import { date, money } from "@/lib/format";
import type { FxRate } from "@/lib/types";
import { useData } from "@/lib/use-data";

function iso(d: Date) {
  return d.toISOString().slice(0, 10);
}

export default function Fx() {
  const { companyId, canEdit } = useCompany();
  const [today] = useState(() => new Date());
  const [currency, setCurrency] = useState("USD");
  const [range, setRange] = useState(() => ({ start: iso(new Date(today.getTime() - 30 * 864e5)), end: iso(today) }));
  const q = new URLSearchParams({ currency, ...range }).toString();
  const { data, error, loading, reload } = useData<FxRate[]>(`/companies/${companyId}/fx/rates?${q}`);
  const [msg, setMsg] = useState<string | null>(null);
  const [actionError, setActionError] = useState<unknown>(null);
  const [syncing, setSyncing] = useState(false);

  async function sync() {
    setSyncing(true);
    setActionError(null);
    try {
      const r = await api<{ rates: number }>(`/companies/${companyId}/fx/sync`, { method: "POST", json: { ...range, currencies: [currency] } });
      setMsg(`Fetched ${r.rates} ${currency} rates from Nepal Rastra Bank.`);
      reload();
    } catch (err) {
      setActionError(err);
    } finally {
      setSyncing(false);
    }
  }

  async function override(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = e.currentTarget;
    const f = Object.fromEntries(new FormData(form)) as Record<string, string>;
    try {
      await api(`/companies/${companyId}/fx/overrides`, { method: "POST", json: { ...f, currency, unit: Number(f.unit || 1) } });
      form.reset();
      setMsg(`Saved the bank rate for ${f.on}. Payroll on that date uses it instead of the NRB rate.`);
      setActionError(null);
      reload();
    } catch (err) {
      setActionError(err);
    }
  }

  return (
    <div className="stack">
      <header className="page-head">
        <div>
          <h1>Exchange rates</h1>
          <p>Foreign-currency pay is converted at Nepal Rastra Bank’s published buying rate on the payment date. Rates are fetched automatically when payroll runs.</p>
        </div>
      </header>

      {msg && <p className="notice ok" role="status">{msg}</p>}
      <ErrorNotice error={actionError} />

      <section className="sheet">
        <div className="row" style={{ alignItems: "flex-end", marginBottom: "1rem" }}>
          <Field label="Currency">
            <select value={currency} onChange={(e) => setCurrency(e.target.value)}>
              {["USD", "EUR", "GBP", "AUD", "INR", "JPY"].map((c) => <option key={c}>{c}</option>)}
            </select>
          </Field>
          <Field label="From"><input type="date" value={range.start} onChange={(e) => setRange({ ...range, start: e.target.value })} /></Field>
          <Field label="To"><input type="date" value={range.end} onChange={(e) => setRange({ ...range, end: e.target.value })} /></Field>
          {canEdit && <button className="btn quiet" onClick={sync} disabled={syncing}>{syncing ? "Fetching…" : "Fetch from NRB"}</button>}
        </div>
        {loading && <Loading what="rates" />}
        <ErrorNotice error={error} />
        {data && data.length === 0 && <p className="muted">No {currency} rates stored for these dates. Fetch them from NRB.</p>}
        {data && data.length > 0 && (
          <div className="table-scroll">
            <table className="ledger">
              <thead>
                <tr><th>Date</th><th className="num">Buying</th><th className="num">Selling</th><th>Per</th><th>Source</th></tr>
              </thead>
              <tbody>
                {[...data].reverse().map((r) => (
                  <tr key={`${r.on}-${r.source}`}>
                    <td>{date(r.on)}</td>
                    <td className="num figure">{money(r.buy, 2)}</td>
                    <td className="num figure">{money(r.sell, 2)}</td>
                    <td>{r.unit} {r.currency}</td>
                    <td>{r.source === "OVERRIDE" ? <span className="tag corroborated" title={r.override_reason ?? ""}>Bank rate: {r.override_reason}</span> : "NRB"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {canEdit && (
        <form className="sheet" onSubmit={override}>
          <h2>Use the bank’s rate for a date</h2>
          <p className="small muted" style={{ margin: "0.3rem 0 0.9rem" }}>
            Only if your auditor requires the rate the bank actually credited. Record the credit advice or reference so it can be checked.
          </p>
          <div className="form-grid">
            <Field label="Date"><input type="date" name="on" required /></Field>
            <Field label={`Buying (NPR per ${currency})`}><input name="buy" inputMode="decimal" required className="figure" /></Field>
            <Field label={`Selling (NPR per ${currency})`}><input name="sell" inputMode="decimal" required className="figure" /></Field>
            <Field label="Per units"><input name="unit" inputMode="numeric" defaultValue="1" /></Field>
            <Field label="Reason or reference"><input name="reason" required minLength={3} placeholder="Credit advice no." /></Field>
          </div>
          <div className="form-actions"><button className="btn quiet">Save bank rate</button></div>
        </form>
      )}
    </div>
  );
}
