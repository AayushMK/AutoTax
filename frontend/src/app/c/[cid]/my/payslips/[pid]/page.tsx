"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { Suspense } from "react";

import { ErrorNotice, Loading } from "@/components/bits";
import { PayslipView } from "@/components/payslip-view";
import { useCompany } from "@/components/shell";
import type { PayslipDetail } from "@/lib/types";
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
  const { data: p, error } = useData<PayslipDetail & { inputs: { month_label?: string } }>(`/companies/${companyId}/me/payslips/${pid}`);
  if (error) return <ErrorNotice error={error} />;
  if (!p) return <Loading what="payslip" />;
  return (
    <PayslipView
      p={p}
      monthLabel={p.inputs.month_label ?? `month ${p.month}`}
      back={<Link href={`/c/${companyId}/my`}>My pay</Link>}
    />
  );
}
