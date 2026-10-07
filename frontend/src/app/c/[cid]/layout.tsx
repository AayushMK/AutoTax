import { Suspense } from "react";

import { Shell } from "@/components/shell";

export default function CompanyLayout({ children }: { children: React.ReactNode }) {
  return (
    <Suspense fallback={null}>
      <Shell>{children}</Shell>
    </Suspense>
  );
}
