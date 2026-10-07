"use client";

import Link from "next/link";
import { useParams, usePathname, useRouter } from "next/navigation";
import { createContext, useContext, useEffect } from "react";

import { getToken, setToken } from "@/lib/api";
import type { Me, Role } from "@/lib/types";
import { useData } from "@/lib/use-data";

import styles from "./shell.module.css";

interface CompanyCtx {
  companyId: number;
  /** null until the signed-in user has loaded */
  me: Me | null;
  role: Role | null;
  companyName: string | null;
  canEdit: boolean;
}

const Ctx = createContext<CompanyCtx | null>(null);

export function useCompany(): CompanyCtx {
  const c = useContext(Ctx);
  if (!c) throw new Error("useCompany outside company shell");
  return c;
}

const NAV = [
  { href: "", label: "Overview" },
  { href: "/employees", label: "Employees" },
  { href: "/payroll", label: "Payroll" },
  { href: "/fx", label: "Exchange rates" },
  { href: "/audit", label: "Activity" },
];

export function Shell({ children }: { children: React.ReactNode }) {
  const { cid } = useParams<{ cid: string }>();
  const pathname = usePathname();
  const router = useRouter();
  const { data: me, error } = useData<Me>("/auth/me");

  useEffect(() => {
    if (!getToken()) router.replace("/login");
  }, [router]);

  // The frame and the page render immediately; account details fill in when they arrive.
  const companyId = Number(cid);
  const membership = me?.memberships.find((m) => m.company_id === companyId) ?? null;
  const noAccess = me !== null && membership === null;
  const base = `/c/${companyId}`;
  const ctx: CompanyCtx = {
    companyId,
    me,
    role: membership?.role ?? null,
    companyName: membership?.company_name ?? null,
    canEdit: membership !== null && membership.role !== "viewer",
  };

  return (
    <Ctx.Provider value={ctx}>
      <div className={styles.frame}>
        <aside className={styles.side}>
          <Link href={base} className={styles.brand}>
            AutoTax
            <span className={styles.brandDeva} lang="ne">कर हिसाब</span>
          </Link>
          {me && me.memberships.length > 1 ? (
            <select
              className={styles.company}
              aria-label="Company"
              value={companyId}
              onChange={(e) => router.push(`/c/${e.target.value}`)}
            >
              {me.memberships.map((m) => (
                <option key={m.company_id} value={m.company_id}>{m.company_name}</option>
              ))}
            </select>
          ) : (
            <p className={styles.companyName}>{membership?.company_name ?? "\u00a0"}</p>
          )}
          <nav aria-label="Sections">
            {NAV.map((n) => {
              const href = base + n.href;
              const active = n.href === "" ? pathname === base : pathname.startsWith(href);
              return (
                <Link key={n.label} href={href} className={styles.navLink} aria-current={active ? "page" : undefined}>
                  {n.label}
                </Link>
              );
            })}
          </nav>
          <div className={styles.me}>
            <span>{me?.name}</span>
            <span className="faint small">{membership?.role}</span>
            <button
              className="btn quiet small"
              onClick={() => {
                setToken(null);
                router.replace("/login");
              }}
            >
              Sign out
            </button>
          </div>
        </aside>
        <main className={styles.main}>
          {error ? (
            <p className="notice block">Couldn’t load your account: {error.message}</p>
          ) : noAccess ? (
            <div className="empty">
              <p>You don’t have access to this company.</p>
              <Link className="btn" href="/">Go to your companies</Link>
            </div>
          ) : (
            children
          )}
        </main>
      </div>
    </Ctx.Provider>
  );
}
