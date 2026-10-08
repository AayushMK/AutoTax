"use client";

import Link from "next/link";
import { useState } from "react";

import { ErrorNotice, Field, Loading } from "@/components/bits";
import { InviteLink } from "@/components/invite-link";
import { useCompany } from "@/components/shell";
import { api } from "@/lib/api";
import { date, ROLE_LABEL } from "@/lib/format";
import type { Invite, Member } from "@/lib/types";
import { useData } from "@/lib/use-data";

export default function Team() {
  const { companyId, me, role } = useCompany();
  const members = useData<Member[]>(`/companies/${companyId}/members`);
  const invites = useData<Invite[]>(role === "admin" ? `/companies/${companyId}/invites` : null);
  const [created, setCreated] = useState<Invite | null>(null);
  const [error, setError] = useState<unknown>(null);

  async function invite(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = e.currentTarget;
    const f = Object.fromEntries(new FormData(form)) as Record<string, string>;
    try {
      setCreated(await api<Invite>(`/companies/${companyId}/invites`, { method: "POST", json: f }));
      setError(null);
      form.reset();
      invites.reload();
    } catch (err) {
      setError(err);
    }
  }

  async function act(path: string) {
    try {
      await api(path, { method: "DELETE" });
      setError(null);
      members.reload();
      invites.reload();
    } catch (err) {
      setError(err);
    }
  }

  const hr = members.data?.filter((m) => m.role !== "employee") ?? [];
  const staff = members.data?.filter((m) => m.role === "employee") ?? [];

  return (
    <div className="stack">
      <header className="page-head">
        <div>
          <h1>Logins</h1>
          <p>HR roles can see every salary. Employees see only their own finalized payslips, SSF and CIT.</p>
        </div>
      </header>

      <ErrorNotice error={error} />
      {created && <InviteLink invite={created} />}

      <form className="sheet" onSubmit={invite}>
        <h2>Invite HR staff</h2>
        <p className="small muted" style={{ margin: "0.3rem 0 0.9rem" }}>
          To give an employee access to their own pay, open their page under <Link href={`/c/${companyId}/employees`}>Employees</Link>.
        </p>
        <div className="form-grid" style={{ alignItems: "end" }}>
          <Field label="Email"><input name="email" type="email" required /></Field>
          <Field label="Access">
            <select name="role" defaultValue="accountant">
              <option value="accountant">{ROLE_LABEL.accountant}: run payroll</option>
              <option value="admin">{ROLE_LABEL.admin}: also manages logins</option>
              <option value="viewer">{ROLE_LABEL.viewer}</option>
            </select>
          </Field>
          <div><button className="btn">Create invite link</button></div>
        </div>
      </form>

      <section className="sheet">
        <h2>HR and auditors</h2>
        {members.loading && <Loading what="logins" />}
        <MemberTable rows={hr} meId={me?.id} onRemove={(id) => act(`/companies/${companyId}/members/${id}`)} />
      </section>

      <section className="sheet">
        <h2>Employees with a login</h2>
        {staff.length === 0 ? (
          <p className="muted">No employee logins yet.</p>
        ) : (
          <MemberTable rows={staff} meId={me?.id} onRemove={(id) => act(`/companies/${companyId}/members/${id}`)} />
        )}
      </section>

      {invites.data && invites.data.length > 0 && (
        <section className="sheet">
          <h2>Waiting to be accepted</h2>
          <table className="ledger">
            <tbody>
              {invites.data.map((i) => (
                <tr key={i.id}>
                  <td>{i.email}</td>
                  <td>{ROLE_LABEL[i.role]}{i.employee_name && <span className="faint small"> ({i.employee_name})</span>}</td>
                  <td className="small muted">expires {date(i.expires_at)}</td>
                  <td style={{ width: 1 }}><button className="btn quiet small" onClick={() => act(`/companies/${companyId}/invites/${i.id}`)}>Cancel</button></td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}
    </div>
  );
}

function MemberTable({ rows, meId, onRemove }: { rows: Member[]; meId?: number; onRemove: (userId: number) => void }) {
  return (
    <table className="ledger">
      <thead><tr><th>Name</th><th>Email</th><th>Access</th><th /></tr></thead>
      <tbody>
        {rows.map((m) => (
          <tr key={m.user_id}>
            <td>{m.name}{m.employee_name && m.role !== "employee" && <span className="faint small"> (also on payroll)</span>}</td>
            <td className="small">{m.email}</td>
            <td>{ROLE_LABEL[m.role]}{m.role === "employee" && m.employee_name && <span className="faint small"> for {m.employee_name}</span>}</td>
            <td style={{ width: 1 }}>
              {m.user_id !== meId && <button className="btn quiet small" onClick={() => onRemove(m.user_id)}>Remove access</button>}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
