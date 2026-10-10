"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { Suspense } from "react";

import { ErrorNotice, Field, Loading } from "@/components/bits";
import { PayslipView } from "@/components/payslip-view";
import { api } from "@/lib/api";
import { useCompany } from "@/components/shell";
import type { AnnualStatement, PayslipDetail } from "@/lib/types";
import { useData } from "@/lib/use-data";

export default function Page() {
  return (
    <Suspense fallback={<Loading what="payslip" />}>
      <MyPayslip />
    </Suspense>
  );
}

function MyPayslip() {
  const { pid } = useParams<{ pid: string }>();
  const { companyId } = useCompany();
  const base = `/companies/${companyId}/me`;
  const { data: p, error } = useData<PayslipDetail>(`${base}/payslips/${pid}`);
  if (error) return <ErrorNotice error={error} />;
  if (!p) return <Loading what="payslip" />;
  return (
    <PayslipView
      p={p}
      back={<Link href={`/c/${companyId}/my`}>My pay</Link>}
      picker={<Picker companyId={companyId} current={p} />}
    />
  );
}

/** Pick another payslip by fiscal year and month, like the HR system's filter bar. */
function Picker({ companyId, current }: { companyId: number; current: PayslipDetail }) {
  const router = useRouter();
  const base = `/companies/${companyId}/me`;
  const years = useData<string[]>(`${base}/years`);
  const st = useData<AnnualStatement>(`${base}/annual/${current.fiscal_year.replace("/", "-")}`);
  const paid = st.data?.months.filter((m) => m.payslip_id) ?? [];

  async function pickYear(fy: string) {
    const s = await api<AnnualStatement>(`${base}/annual/${fy.replace("/", "-")}`);
    const last = [...s.months].reverse().find((m) => m.payslip_id);
    if (last) router.push(`/c/${companyId}/my/payslips/${last.payslip_id}`);
  }

  return (
    <div className="sheet no-print">
      <div className="row" style={{ alignItems: "flex-end" }}>
        <Field label="Fiscal year">
          <select value={current.fiscal_year} onChange={(e) => pickYear(e.target.value)}>
            {(years.data ?? [current.fiscal_year]).map((y) => <option key={y} value={y}>{y}</option>)}
          </select>
        </Field>
        <Field label="Month">
          <select value={current.id} onChange={(e) => router.push(`/c/${companyId}/my/payslips/${e.target.value}`)}>
            {paid.map((m) => <option key={m.month} value={m.payslip_id}>{m.month_label}</option>)}
            {!paid.length && <option value={current.id}>{current.month_label}</option>}
          </select>
        </Field>
        <ErrorNotice error={st.error} />
      </div>
    </div>
  );
}
