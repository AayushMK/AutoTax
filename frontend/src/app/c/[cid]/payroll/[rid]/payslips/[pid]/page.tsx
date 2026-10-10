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
      <PayslipPage />
    </Suspense>
  );
}

function PayslipPage() {
  const { rid, pid } = useParams<{ rid: string; pid: string }>();
  const { companyId } = useCompany();
  const { data: p, error } = useData<PayslipDetail>(`/companies/${companyId}/payroll-runs/${rid}/payslips/${pid}`);
  if (error) return <ErrorNotice error={error} />;
  if (!p) return <Loading what="payslip" />;
  return (
    <PayslipView p={p} back={<>
      <Link href={`/c/${companyId}/payroll/${rid}`}>{p.month_label}</Link>{" / "}
      <Link href={`/c/${companyId}/employees/${p.employee_id}`}>{p.employee_name}</Link>
    </>} />
  );
}
