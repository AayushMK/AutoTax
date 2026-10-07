"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { ErrorNotice, Field, Loading } from "@/components/bits";
import { useCompany } from "@/components/shell";
import { api } from "@/lib/api";
import { date } from "@/lib/format";
import type { Employee } from "@/lib/types";
import { useData } from "@/lib/use-data";

export default function Employees() {
  const { companyId, canEdit } = useCompany();
  const router = useRouter();
  const { data, error, loading } = useData<Employee[]>(`/companies/${companyId}/employees`);
  const [adding, setAdding] = useState(false);
  const [saveError, setSaveError] = useState<unknown>(null);
  const [query, setQuery] = useState("");

  async function add(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = Object.fromEntries(new FormData(e.currentTarget)) as Record<string, string>;
    try {
      const emp = await api<Employee>(`/companies/${companyId}/employees`, {
        method: "POST",
        json: { ...f, pan: f.pan || null, email: f.email || null, left_on: null },
      });
      router.push(`/c/${companyId}/employees/${emp.id}?new=1`);
    } catch (err) {
      setSaveError(err);
    }
  }

  const q = query.trim().toLowerCase();
  const shown = data?.filter((e) => !q || e.name.toLowerCase().includes(q) || e.code.toLowerCase().includes(q));

  return (
    <div className="stack">
      <header className="page-head">
        <div>
          <h1>Employees</h1>
          <p>Each employee needs a tax profile for the fiscal year and a salary structure before payroll can run.</p>
        </div>
        {canEdit && !adding && <button className="btn" onClick={() => setAdding(true)}>Add employee</button>}
      </header>

      {adding && (
        <form className="sheet" onSubmit={add}>
          <h2>New employee</h2>
          <ErrorNotice error={saveError} />
          <div className="form-grid" style={{ marginTop: "0.75rem" }}>
            <Field label="Employee code"><input name="code" required placeholder="E-014" /></Field>
            <Field label="Full name"><input name="name" required /></Field>
            <Field label="PAN" hint="Personal PAN, for TDS sheets"><input name="pan" inputMode="numeric" /></Field>
            <Field label="Email"><input name="email" type="email" /></Field>
            <Field label="Joined on"><input name="joined_on" type="date" required /></Field>
          </div>
          <div className="form-actions">
            <button className="btn">Add and set up tax profile</button>
            <button type="button" className="btn quiet" onClick={() => setAdding(false)}>Cancel</button>
          </div>
        </form>
      )}

      <section className="sheet">
        {loading && <Loading what="employees" />}
        <ErrorNotice error={error} />
        {data && data.length === 0 && !adding && (
          <div className="empty">
            <p>No employees yet.</p>
            {canEdit && <button className="btn quiet" onClick={() => setAdding(true)}>Add the first employee</button>}
          </div>
        )}
        {data && data.length > 0 && (
          <>
            {data.length > 8 && (
              <input
                type="search"
                placeholder="Find by name or code"
                aria-label="Find employee"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                style={{ marginBottom: "0.75rem", width: "min(100%, 22rem)" }}
              />
            )}
            <div className="table-scroll">
              <table className="ledger">
                <thead>
                  <tr><th>Code</th><th>Name</th><th>PAN</th><th>Joined</th><th>Left</th></tr>
                </thead>
                <tbody>
                  {shown!.map((e) => (
                    <tr key={e.id}>
                      <td className="figure">{e.code}</td>
                      <td><Link href={`/c/${companyId}/employees/${e.id}`}>{e.name}</Link></td>
                      <td className="figure">{e.pan ?? <span className="faint">—</span>}</td>
                      <td>{date(e.joined_on)}</td>
                      <td>{e.left_on ? date(e.left_on) : <span className="faint">—</span>}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        )}
      </section>
    </div>
  );
}
