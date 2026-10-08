"use client";

import { useState } from "react";

import { ErrorNotice, Field, Loading } from "@/components/bits";
import { useCompany } from "@/components/shell";
import { api } from "@/lib/api";
import type { Company, Run } from "@/lib/types";
import { useData } from "@/lib/use-data";

export default function Settings() {
  const { companyId, role } = useCompany();
  const { data: c, error, setData } = useData<Company>(`/companies/${companyId}`);
  const runs = useData<Run[]>(`/companies/${companyId}/payroll-runs`);
  const [saveError, setSaveError] = useState<unknown>(null);
  const [saved, setSaved] = useState(false);
  const locked = (runs.data?.length ?? 0) > 0;

  async function save(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = Object.fromEntries(new FormData(e.currentTarget)) as Record<string, string>;
    try {
      setData(await api<Company>(`/companies/${companyId}`, {
        method: "PUT",
        json: { name: f.name, pan: f.pan || null, pay_calendar: f.pay_calendar ?? c?.pay_calendar },
      }));
      setSaveError(null);
      setSaved(true);
    } catch (err) {
      setSaveError(err);
    }
  }

  if (error) return <ErrorNotice error={error} />;
  if (!c) return <Loading what="company" />;

  return (
    <div className="stack">
      <header className="page-head">
        <div>
          <h1>Company</h1>
          <p>Details printed on TDS sheets, and how your payroll months are counted.</p>
        </div>
      </header>
      <form className="sheet" onSubmit={save} onChange={() => setSaved(false)}>
        <ErrorNotice error={saveError} />
        <fieldset disabled={role !== "admin"} style={{ border: 0, padding: 0, margin: 0 }}>
          <div className="form-grid">
            <Field label="Company name"><input name="name" defaultValue={c.name} required /></Field>
            <Field label="Company PAN"><input name="pan" defaultValue={c.pan ?? ""} inputMode="numeric" /></Field>
          </div>
          <h3 style={{ margin: "1.5rem 0 0.5rem" }}>Payroll months</h3>
          <div className="stack" style={{ gap: "0.6rem" }}>
            <label className="check">
              <input type="radio" name="pay_calendar" value="bs" defaultChecked={c.pay_calendar === "bs"} disabled={locked} />
              <span>Nepali months<br /><span className="small muted">12 runs a year, Shrawan to Ashadh.</span></span>
            </label>
            <label className="check">
              <input type="radio" name="pay_calendar" value="ad" defaultChecked={c.pay_calendar === "ad"} disabled={locked} />
              <span>
                English months<br />
                <span className="small muted">
                  13 runs a fiscal year. July is split at Shrawan 1: the year opens with the rest of July and closes with
                  the start of the next July, each paid for the days it covers.
                </span>
              </span>
            </label>
          </div>
          {locked && (
            <p className="small muted" style={{ marginTop: "0.75rem" }}>
              Fixed now that payroll exists, so past months keep their meaning.
            </p>
          )}
          {role === "admin" && (
            <div className="form-actions">
              <button className="btn">Save</button>
              {saved && <span className="tag verified" role="status">Saved</span>}
            </div>
          )}
        </fieldset>
      </form>
    </div>
  );
}
