"use client";

import Link from "next/link";
import { useParams, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";

import { ErrorNotice, Field, Loading, Num } from "@/components/bits";
import { useCompany } from "@/components/shell";
import { api } from "@/lib/api";
import { date, KIND_LABEL } from "@/lib/format";
import { InviteLink } from "@/components/invite-link";
import { YearFigures, YearTable } from "@/components/year-table";
import type { AnnualStatement, Component, EmployeeDetail, IncomeKind, Invite, Member, RulesStatus, TaxProfile } from "@/lib/types";
import { useData } from "@/lib/use-data";

export default function Page() {
  return (
    <Suspense fallback={<Loading what="employee" />}>
      <EmployeePage />
    </Suspense>
  );
}

function EmployeePage() {
  const { eid } = useParams<{ eid: string }>();
  const isNew = useSearchParams().get("new") === "1";
  const { companyId } = useCompany();
  const path = `/companies/${companyId}/employees/${eid}`;
  const { data: emp, error, reload } = useData<EmployeeDetail>(path);
  const rules = useData<RulesStatus>("/rules/status");
  const fiscalYears = (rules.data?.all ?? []).map((r) => r.fiscal_year).reverse();
  const [fy, setFy] = useState<string | null>(null);
  const activeFy = fy ?? rules.data?.current?.fiscal_year ?? fiscalYears[0];

  if (error) return <ErrorNotice error={error} />;
  if (!emp) return <Loading what="employee" />;

  return (
    <div className="stack">
      <header className="page-head">
        <div>
          <p className="small"><Link href={`/c/${companyId}/employees`}>Employees</Link></p>
          <h1>{emp.name}</h1>
          <p>
            <span className="figure">{emp.code}</span>. Joined {date(emp.joined_on)}
            {emp.left_on && `, left ${date(emp.left_on)}`}. PAN {emp.pan ?? "not recorded"}.
          </p>
        </div>
      </header>

      {isNew && emp.tax_profiles.length === 0 && (
        <div className="notice">Next: fill in the tax profile below, then add the salary structure.</div>
      )}

      <DetailsForm emp={emp} path={path} onSaved={reload} />

      {activeFy && (
        <TaxProfileForm
          key={activeFy + emp.tax_profiles.length}
          fy={activeFy}
          fiscalYears={fiscalYears}
          onFy={setFy}
          path={path}
          existing={emp.tax_profiles.find((t) => t.fiscal_year === activeFy)}
          onSaved={reload}
        />
      )}

      <Structures emp={emp} path={path} onChange={reload} />

      {activeFy && <EmployeeYear employeeId={emp.id} fy={activeFy} />}

      <PortalAccess emp={emp} />
    </div>
  );
}

function EmployeeYear({ employeeId, fy }: { employeeId: number; fy: string }) {
  const { companyId } = useCompany();
  const { data: st, error } = useData<AnnualStatement>(`/companies/${companyId}/employees/${employeeId}/annual/${fy.replace("/", "-")}`);
  return (
    <section className="sheet">
      <h2>FY {fy}: SSF, CIT and tax by month</h2>
      <ErrorNotice error={error} />
      {st && (
        <>
          <div style={{ margin: "0.9rem 0 1.25rem" }}><YearFigures st={st} /></div>
          {st.months_paid === 0 ? (
            <p className="muted">No payroll for this employee in FY {fy} yet.</p>
          ) : (
            <YearTable st={st} payslipHref={(pid, rid) => `/c/${companyId}/payroll/${rid}/payslips/${pid}`} />
          )}
        </>
      )}
    </section>
  );
}

function PortalAccess({ emp }: { emp: EmployeeDetail }) {
  const { companyId, role } = useCompany();
  const members = useData<Member[]>(`/companies/${companyId}/members`);
  const invites = useData<Invite[]>(role === "admin" ? `/companies/${companyId}/invites` : null);
  const [created, setCreated] = useState<Invite | null>(null);
  const [error, setError] = useState<unknown>(null);
  const login = members.data?.find((m) => m.employee_id === emp.id);
  const pending = invites.data?.find((i) => i.employee_id === emp.id);

  async function invite(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const email = new FormData(e.currentTarget).get("email");
    try {
      setCreated(await api<Invite>(`/companies/${companyId}/invites`, {
        method: "POST", json: { email, role: "employee", employee_id: emp.id },
      }));
      setError(null);
      invites.reload();
    } catch (err) {
      setError(err);
    }
  }

  return (
    <section className="sheet">
      <h2>Login</h2>
      <p className="small muted" style={{ margin: "0.3rem 0 0.9rem" }}>
        With a login, {emp.name} can see their own finalized payslips, SSF and CIT, and nobody else’s.
      </p>
      <ErrorNotice error={error} />
      {created && <InviteLink invite={created} />}
      {login ? (
        <p>Has a login: <strong>{login.email}</strong>.</p>
      ) : pending && !created ? (
        <p>Invite sent to <strong>{pending.email}</strong>, waiting to be accepted (expires {date(pending.expires_at)}).</p>
      ) : role === "admin" && !created ? (
        <form className="row" style={{ alignItems: "flex-end" }} onSubmit={invite}>
          <Field label="Their email"><input name="email" type="email" required defaultValue={emp.email ?? ""} /></Field>
          <button className="btn quiet">Create invite link</button>
        </form>
      ) : !created ? (
        <p className="muted">No login yet. An HR admin can invite them.</p>
      ) : null}
    </section>
  );
}

function DetailsForm({ emp, path, onSaved }: { emp: EmployeeDetail; path: string; onSaved: () => void }) {
  const { canEdit } = useCompany();
  const [error, setError] = useState<unknown>(null);
  const [saved, setSaved] = useState(false);

  async function save(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = Object.fromEntries(new FormData(e.currentTarget)) as Record<string, string>;
    const opt = (k: string) => (f[k]?.trim() ? f[k].trim() : null);
    try {
      await api(path, {
        method: "PUT",
        json: {
          code: f.code, name: f.name, joined_on: f.joined_on, left_on: opt("left_on"), pan: opt("pan"), email: opt("email"),
          department: opt("department"), designation: opt("designation"), cit_number: opt("cit_number"),
          ssf_number: opt("ssf_number"), bank_account: opt("bank_account"),
        },
      });
      setError(null);
      setSaved(true);
      onSaved();
    } catch (err) {
      setError(err);
    }
  }

  return (
    <form className="sheet" onSubmit={save} onChange={() => setSaved(false)}>
      <h2>Employee details</h2>
      <p className="small muted" style={{ margin: "-6px 0 14px" }}>Printed on payslips. The employee sees only their own.</p>
      <ErrorNotice error={error} />
      <fieldset disabled={!canEdit}>
        <div className="form-grid">
          <Field label="Employee ID"><input name="code" defaultValue={emp.code} required /></Field>
          <Field label="Full name"><input name="name" defaultValue={emp.name} required /></Field>
          <Field label="Department"><input name="department" defaultValue={emp.department ?? ""} /></Field>
          <Field label="Designation"><input name="designation" defaultValue={emp.designation ?? ""} /></Field>
          <Field label="PAN no."><input name="pan" inputMode="numeric" defaultValue={emp.pan ?? ""} /></Field>
          <Field label="SSF no."><input name="ssf_number" defaultValue={emp.ssf_number ?? ""} /></Field>
          <Field label="CIT no."><input name="cit_number" defaultValue={emp.cit_number ?? ""} /></Field>
          <Field label="Bank A/c no."><input name="bank_account" defaultValue={emp.bank_account ?? ""} /></Field>
          <Field label="Email"><input name="email" type="email" defaultValue={emp.email ?? ""} /></Field>
          <Field label="Joined on"><input name="joined_on" type="date" defaultValue={emp.joined_on} required /></Field>
          <Field label="Left on" hint="Leave empty while employed"><input name="left_on" type="date" defaultValue={emp.left_on ?? ""} /></Field>
        </div>
        {canEdit && (
          <div className="form-actions">
            <button className="btn">Save details</button>
            {saved && <span className="tag verified" role="status">Saved</span>}
          </div>
        )}
      </fieldset>
    </form>
  );
}

function TaxProfileForm({ fy, fiscalYears, onFy, path, existing, onSaved }: {
  fy: string;
  fiscalYears: string[];
  onFy: (fy: string) => void;
  path: string;
  existing?: TaxProfile;
  onSaved: () => void;
}) {
  const { canEdit } = useCompany();
  const [error, setError] = useState<unknown>(null);
  const [saved, setSaved] = useState(false);
  const p = existing;

  async function save(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    const bool = (k: string) => f.get(k) === "on";
    const dec = (k: string) => (String(f.get(k) || "0").replace(/,/g, "") || "0");
    try {
      await api(`${path}/tax-profiles/${fy.replace("/", "-")}`, {
        method: "PUT",
        json: {
          resident: f.get("resident") === "yes",
          filing: f.get("filing"),
          gender: f.get("gender"),
          disabled: bool("disabled"),
          ssf_enrolled: bool("ssf_enrolled"),
          approved_pension: bool("approved_pension"),
          remote_area: f.get("remote_area") || null,
          income_only_from_employment: bool("income_only_from_employment"),
          life_insurance_premium: dec("life_insurance_premium"),
          health_insurance_premium: dec("health_insurance_premium"),
          building_insurance_premium: dec("building_insurance_premium"),
          donation: dec("donation"),
          prior_income: dec("prior_income"),
          prior_retirement: dec("prior_retirement"),
          prior_tds: dec("prior_tds"),
        },
      });
      setError(null);
      setSaved(true);
      onSaved();
    } catch (err) {
      setError(err);
    }
  }

  return (
    <form className="sheet" onSubmit={save} onChange={() => setSaved(false)}>
      <div className="spread">
        <h2>Tax profile</h2>
        <label className="row small">
          Fiscal year
          <select value={fy} onChange={(e) => onFy(e.target.value)}>
            {fiscalYears.map((y) => <option key={y} value={y}>{y}</option>)}
          </select>
        </label>
      </div>
      {!p && <p className="notice" style={{ marginTop: "0.75rem" }}>No profile for {fy} yet. Payroll for this year needs one.</p>}
      <ErrorNotice error={error} />
      <fieldset disabled={!canEdit} style={{ border: 0, padding: 0, margin: "1rem 0 0" }}>
        <div className="form-grid">
          <Field label="Residency">
            <select name="resident" defaultValue={p?.resident === false ? "no" : "yes"}>
              <option value="yes">Resident</option>
              <option value="no">Non-resident (flat rate)</option>
            </select>
          </Field>
          <Field label="Assessed as">
            <select name="filing" defaultValue={p?.filing ?? "single"}>
              <option value="single">Individual</option>
              <option value="couple">Couple</option>
            </select>
          </Field>
          <Field label="Gender">
            <select name="gender" defaultValue={p?.gender ?? "male"}>
              <option value="male">Male</option>
              <option value="female">Female</option>
              <option value="other">Other</option>
            </select>
          </Field>
          <Field label="Remote area" hint="Category from the Schedule">
            <select name="remote_area" defaultValue={p?.remote_area ?? ""}>
              <option value="">Not applicable</option>
              {["A", "B", "C", "D", "E"].map((c) => <option key={c} value={c}>Category {c}</option>)}
            </select>
          </Field>
        </div>
        <div className="form-grid" style={{ marginTop: "1rem" }}>
          <label className="check"><input type="checkbox" name="ssf_enrolled" defaultChecked={p?.ssf_enrolled} /><span>Contributes to SSF<br /><span className="faint small">11% employee, 20% employer of basic</span></span></label>
          <label className="check"><input type="checkbox" name="approved_pension" defaultChecked={p?.approved_pension} /><span>Contributes to an approved pension fund</span></label>
          <label className="check"><input type="checkbox" name="disabled" defaultChecked={p?.disabled} /><span>Person with disability</span></label>
          <label className="check"><input type="checkbox" name="income_only_from_employment" defaultChecked={p?.income_only_from_employment ?? true} /><span>Salary is their only income<br /><span className="faint small">Needed for the women’s rebate</span></span></label>
        </div>
        <h3 style={{ margin: "1.25rem 0 0.6rem" }}>Yearly premiums and donations</h3>
        <p className="small muted" style={{ marginBottom: "0.75rem" }}>Enter what the employee pays in {fy}, with receipts on file. Caps are applied automatically.</p>
        <div className="form-grid">
          <Field label="Life insurance (NPR)"><input name="life_insurance_premium" inputMode="decimal" defaultValue={p?.life_insurance_premium ?? "0"} /></Field>
          <Field label="Health insurance (NPR)"><input name="health_insurance_premium" inputMode="decimal" defaultValue={p?.health_insurance_premium ?? "0"} /></Field>
          <Field label="Building insurance (NPR)"><input name="building_insurance_premium" inputMode="decimal" defaultValue={p?.building_insurance_premium ?? "0"} /></Field>
          <Field label="Donations (NPR)"><input name="donation" inputMode="decimal" defaultValue={p?.donation ?? "0"} /></Field>
        </div>
        <h3 style={{ margin: "1.25rem 0 0.6rem" }}>Previous employer this fiscal year</h3>
        <p className="small muted" style={{ marginBottom: "0.75rem" }}>
          If they joined mid-year, copy these from the previous employer’s salary certificate. Their income is taxed together
          with yours for {fy}, and the tax they already withheld is credited.
        </p>
        <div className="form-grid">
          <Field label="Income there (NPR)" hint="Including that employer’s SSF/fund contributions"><input name="prior_income" inputMode="decimal" defaultValue={p?.prior_income ?? "0"} /></Field>
          <Field label="SSF, CIT and funds there (NPR)"><input name="prior_retirement" inputMode="decimal" defaultValue={p?.prior_retirement ?? "0"} /></Field>
          <Field label="TDS withheld there (NPR)"><input name="prior_tds" inputMode="decimal" defaultValue={p?.prior_tds ?? "0"} /></Field>
        </div>
        {canEdit && (
          <div className="form-actions">
            <button className="btn">Save tax profile</button>
            {saved && <span className="tag verified" role="status">Saved</span>}
          </div>
        )}
      </fieldset>
    </form>
  );
}

const KINDS: IncomeKind[] = ["basic", "allowance", "overtime", "benefit", "other"];

function Structures({ emp, path, onChange }: { emp: EmployeeDetail; path: string; onChange: () => void }) {
  const { canEdit } = useCompany();
  const [adding, setAdding] = useState(emp.salary_structures.length === 0);
  const [rows, setRows] = useState<Component[]>([{ kind: "basic", amount: "", currency: "NPR", description: "" }]);
  const [citMode, setCitMode] = useState<"fixed" | "fill_cap">("fixed");
  const [error, setError] = useState<unknown>(null);
  const structures = [...emp.salary_structures].reverse();

  async function save(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    try {
      await api(`${path}/salary-structures`, {
        method: "POST",
        json: {
          effective_from: f.get("effective_from"),
          components: rows.map((r) => ({ ...r, amount: r.amount.replace(/,/g, "") })),
          cit_mode: citMode,
          cit_monthly: citMode === "fixed" ? String(f.get("cit_monthly") || "0").replace(/,/g, "") : "0",
          other_retirement_monthly: String(f.get("other_retirement_monthly") || "0").replace(/,/g, ""),
        },
      });
      setError(null);
      setAdding(false);
      setRows([{ kind: "basic", amount: "", currency: "NPR", description: "" }]);
      onChange();
    } catch (err) {
      setError(err);
    }
  }

  async function remove(id: number) {
    try {
      await api(`${path}/salary-structures/${id}`, { method: "DELETE" });
      onChange();
    } catch (err) {
      setError(err);
    }
  }

  const set = (i: number, patch: Partial<Component>) => setRows(rows.map((r, j) => (j === i ? { ...r, ...patch } : r)));

  return (
    <section className="sheet">
      <div className="spread">
        <h2>Monthly salary</h2>
        {canEdit && !adding && <button className="btn quiet" onClick={() => setAdding(true)}>Change salary</button>}
      </div>
      <p className="small muted" style={{ margin: "0.4rem 0 1rem" }}>
        Amounts in USD or other currencies are converted at the NRB rate on each payment date. One-off bonuses are added on the payroll run instead.
      </p>
      <ErrorNotice error={error} />

      {adding && canEdit && (
        <form onSubmit={save} className="stack" style={{ marginBottom: "1.5rem" }}>
          <div className="form-grid">
            <Field label="Effective from"><input type="date" name="effective_from" required defaultValue={emp.salary_structures.length ? "" : emp.joined_on} /></Field>
            <Field label="CIT" hint={citMode === "fill_cap" ? "CIT tops up SSF and other funds to the retirement deduction limit (5 lakh or a third of income), spread over the year." : undefined}>
              <select value={citMode} onChange={(e) => setCitMode(e.target.value as "fixed" | "fill_cap")}>
                <option value="fixed">A fixed amount each month</option>
                <option value="fill_cap">Fill up to the deduction limit</option>
              </select>
            </Field>
            {citMode === "fixed" && <Field label="CIT per month (NPR)"><input name="cit_monthly" inputMode="decimal" defaultValue="0" /></Field>}
            <Field label="Other retirement fund per month (NPR)"><input name="other_retirement_monthly" inputMode="decimal" defaultValue="0" /></Field>
          </div>
          <table className="ledger">
            <thead><tr><th>Pay item</th><th className="num">Amount per month</th><th>Currency</th><th>Note</th><th /></tr></thead>
            <tbody>
              {rows.map((r, i) => (
                <tr key={i}>
                  <td>
                    <select aria-label="Pay item" value={r.kind} onChange={(e) => set(i, { kind: e.target.value as IncomeKind })}>
                      {KINDS.map((k) => <option key={k} value={k}>{KIND_LABEL[k]}</option>)}
                    </select>
                  </td>
                  <td><input aria-label="Amount" required inputMode="decimal" className="figure" style={{ textAlign: "right", width: "100%" }} value={r.amount} onChange={(e) => set(i, { amount: e.target.value })} /></td>
                  <td>
                    <select aria-label="Currency" value={r.currency} onChange={(e) => set(i, { currency: e.target.value })}>
                      {["NPR", "USD", "EUR", "GBP", "AUD", "INR"].map((c) => <option key={c}>{c}</option>)}
                    </select>
                  </td>
                  <td><input aria-label="Note" value={r.description} onChange={(e) => set(i, { description: e.target.value })} /></td>
                  <td>{rows.length > 1 && <button type="button" className="btn quiet small" onClick={() => setRows(rows.filter((_, j) => j !== i))}>Remove</button>}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="form-actions" style={{ marginTop: 0 }}>
            <button type="button" className="btn quiet small" onClick={() => setRows([...rows, { kind: "allowance", amount: "", currency: rows[0].currency, description: "" }])}>Add pay item</button>
          </div>
          <div className="form-actions" style={{ marginTop: 0 }}>
            <button className="btn">Save salary</button>
            {emp.salary_structures.length > 0 && <button type="button" className="btn quiet" onClick={() => setAdding(false)}>Cancel</button>}
          </div>
        </form>
      )}

      {structures.length === 0 && !adding && <p className="muted">No salary recorded.</p>}
      {structures.map((s, i) => (
        <div key={s.id} style={{ marginTop: i ? "1.25rem" : 0, opacity: i ? 0.7 : 1 }}>
          <div className="spread">
            <h3>{i === 0 ? "Current" : "Earlier"}, from {date(s.effective_from)}</h3>
            {canEdit && <button className="btn quiet small" onClick={() => remove(s.id)}>Delete</button>}
          </div>
          <table className="ledger" style={{ marginTop: "0.5rem" }}>
            <tbody>
              {s.components.map((c, j) => (
                <tr key={j}>
                  <td>{KIND_LABEL[c.kind] ?? c.kind}{c.description && <span className="faint small"> ({c.description})</span>}</td>
                  <td className="num">{c.currency} <Num v={c.amount} /></td>
                </tr>
              ))}
              {s.cit_mode === "fill_cap" ? (
                <tr><td>CIT contribution</td><td className="num small">Fills up to the deduction limit</td></tr>
              ) : s.cit_monthly !== "0.00" && <tr><td>CIT contribution</td><td className="num">NPR <Num v={s.cit_monthly} /></td></tr>}
              {s.other_retirement_monthly !== "0.00" && <tr><td>Other retirement fund</td><td className="num">NPR <Num v={s.other_retirement_monthly} /></td></tr>}
            </tbody>
          </table>
        </div>
      ))}
    </section>
  );
}
