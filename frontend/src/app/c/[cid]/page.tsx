"use client";

import { ArrowLeftRight, Banknote, KeyRound, Landmark, PiggyBank, Receipt, TrendingUp, UserPlus, Users } from "lucide-react";
import Link from "next/link";

import { ErrorNotice } from "@/components/bits";
import { MonthGrid } from "@/components/month-grid";
import { RuleStamp, UnverifiedList } from "@/components/rule-status";
import { useCompany } from "@/components/shell";
import { date, money } from "@/lib/format";
import type { ContributionsReport, Employee, Run, RulesStatus } from "@/lib/types";
import { useData } from "@/lib/use-data";

export default function Overview() {
  const { companyId, companyName, canEdit, role } = useCompany();
  const rules = useData<RulesStatus>("/rules/status");
  const runs = useData<Run[]>(`/companies/${companyId}/payroll-runs`);
  const employees = useData<Employee[]>(`/companies/${companyId}/employees`);
  const base = `/c/${companyId}`;
  const draft = runs.data?.find((r) => r.status === "draft");
  const last = runs.data?.find((r) => r.status === "finalized");
  // The year with the latest payroll, else the year the rules say is current.
  const fy = runs.data?.[0]?.fiscal_year ?? rules.data?.current?.fiscal_year ?? null;
  const report = useData<ContributionsReport>(fy ? `/companies/${companyId}/reports/contributions/${fy.replace("/", "-")}` : null);
  const t = report.data?.totals;
  const active = employees.data?.filter((e) => !e.left_on).length;
  const unverified = rules.data?.current?.unverified_params ?? [];

  return (
    <div className="stack">
      <header className="page-head">
        <div>
          <h1>{companyName ?? " "}</h1>
          <p>
            {last ? `Last finalized payroll: ${last.month_label}.` : "No finalized payroll yet."}
            {fy && ` Figures below are for FY ${fy}.`}
          </p>
        </div>
      </header>

      <ErrorNotice error={runs.error ?? rules.error} />

      <section className="bento gridframe" aria-label="At a glance">
        <span className="corner corner--tl" aria-hidden="true" />
        <span className="corner corner--tr" aria-hidden="true" />
        <span className="corner corner--bl" aria-hidden="true" />
        <span className="corner corner--br" aria-hidden="true" />
        {draft ? (
          <Link href={`${base}/payroll/${draft.id}`} className="tile tile--accent span-7">
            <span className="tile__label">Payroll in progress</span>
            <span className="tile__title">{draft.month_label} is waiting to be finalized</span>
            <span className="tile__meta">
              {draft.computed_at ? "Calculated. Check the payslips, then finalize." : "Not calculated yet."} Paid on {date(draft.payment_date)}.
            </span>
            <span className="tile__foot"><span className="arrow">Continue payroll →</span></span>
          </Link>
        ) : (
          <Link href={`${base}/payroll`} className="tile tile--accent span-7">
            <span className="tile__label">Payroll</span>
            <span className="tile__title">{last ? "Start the next month" : "Run your first payroll"}</span>
            <span className="tile__meta">{last ? `${last.month_label} is finalized.` : "Add employees first, then start a month."}</span>
            <span className="tile__foot"><span className="arrow">Go to payroll →</span></span>
          </Link>
        )}

        <div className="tile tile--plain span-5">
          <div className="spread">
            <span className="tile__label">Tax rules</span>
            {rules.data && <RuleStamp status={rules.data} />}
          </div>
          {rules.data?.current && (
            <span className="tile__meta">
              {rules.data.current.version} applies {date(rules.data.current.effective_from)} to {date(rules.data.current.effective_to)}.
              {unverified.length > 0 && " Finalizing asks you to accept the unchecked values until a CA verifies them."}
            </span>
          )}
          {rules.data?.alert && <p className="notice block small">{rules.data.alert}</p>}
          {unverified.length > 0 && (
            <details className="tile__foot">
              <summary className="small">See the {unverified.length} values to check</summary>
              <UnverifiedList params={unverified} />
            </details>
          )}
        </div>

        <Stat hue="blue" icon={<Users />} label="Employees" value={active === undefined ? "…" : String(active)}
          meta={employees.data && employees.data.length !== active ? `in service, ${employees.data.length - (active ?? 0)} left earlier` : "in service"} />
        <Stat hue="orange" icon={<Receipt />} label={`TDS, FY ${fy ?? ""}`} value={t ? money(t.tds) : "…"} meta="withheld in finalized months" />
        <Stat hue="green" icon={<PiggyBank />} label="SSF, 31%" value={t ? money(t.ssf_total) : "…"}
          meta={t ? `${money(t.ssf_employee)} employees + ${money(t.ssf_employer)} company` : ""} />
        <Stat hue="purple" icon={<TrendingUp />} label="CIT" value={t ? money(t.cit) : "…"} meta="deposited this year" />
      </section>

      {fy && (
        <section className="sheet">
          <div className="spread" style={{ marginBottom: 16 }}>
            <h2>FY {fy}, month by month</h2>
            <Link href={`${base}/payroll`} className="small">All payroll runs</Link>
          </div>
          <MonthGrid companyId={companyId} fiscalYear={fy} canStart={canEdit} />
        </section>
      )}

      <section aria-label="Shortcuts">
        <h2 style={{ marginBottom: 12 }}>Go to</h2>
        <div className="linkgrid">
          {canEdit && <Shortcut hue="blue" href={`${base}/employees`} icon={<UserPlus />} title="Add an employee" text="Tax profile and salary, in NPR or USD" />}
          <Shortcut hue="green" href={`${base}/payroll`} icon={<Banknote />} title="Payroll" text="Calculate, review and finalize a month" />
          <Shortcut hue="purple" href={`${base}/contributions`} icon={<Landmark />} title="SSF, CIT & TDS" text="By month and year, with the IRD sheet" />
          <Shortcut hue="orange" href={`${base}/fx`} icon={<ArrowLeftRight />} title="Exchange rates" text="NRB rates and your bank’s rate" />
          {role === "admin" && <Shortcut hue="pink" href={`${base}/team`} icon={<KeyRound />} title="Logins" text="Invite HR and give employees access" />}
        </div>
      </section>
    </div>
  );
}

function Stat({ hue, icon, label, value, meta }: { hue: string; icon: React.ReactNode; label: string; value: string; meta: string }) {
  return (
    <div className={`tile hue-${hue} span-3`}>
      <span className="chip-icon" style={{ background: "var(--bg)" }}>{icon}</span>
      <span className="tile__label">{label}</span>
      <span className="tile__value">{value}</span>
      <span className="tile__meta">{meta}</span>
    </div>
  );
}

function Shortcut({ hue, href, icon, title, text }: { hue: string; href: string; icon: React.ReactNode; title: string; text: string }) {
  return (
    <Link href={href} className={`linkcard hue-${hue}`}>
      <span className="chip-icon">{icon}</span>
      <span>
        <strong style={{ display: "block", color: "var(--text)", fontSize: 14 }}>{title} →</strong>
        <span>{text}</span>
      </span>
    </Link>
  );
}
