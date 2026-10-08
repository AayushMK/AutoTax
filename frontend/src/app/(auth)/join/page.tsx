"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";

import { ErrorNotice, Field, Loading } from "@/components/bits";
import { api, setToken } from "@/lib/api";
import { ROLE_LABEL } from "@/lib/format";
import type { Role } from "@/lib/types";
import { useData } from "@/lib/use-data";

import styles from "../auth.module.css";
import { Brand, Intro } from "../intro";

interface InviteInfo {
  company_id: number;
  company_name: string;
  email: string;
  role: Role;
  employee_name: string | null;
  has_account: boolean;
}

export default function Page() {
  return (
    <Suspense fallback={null}>
      <Join />
    </Suspense>
  );
}

function Join() {
  const token = useSearchParams().get("token");
  const router = useRouter();
  const info = useData<InviteInfo>(token ? `/auth/invites/${encodeURIComponent(token)}` : null);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = Object.fromEntries(new FormData(e.currentTarget)) as Record<string, string>;
    setBusy(true);
    try {
      const { token: session } = await api<{ token: string }>(`/auth/invites/${encodeURIComponent(token!)}/accept`, { method: "POST", json: f });
      setToken(session);
      const { company_id, role } = info.data!;
      router.replace(role === "employee" ? `/c/${company_id}/my` : `/c/${company_id}`);
    } catch (err) {
      setError(err);
      setBusy(false);
    }
  }

  const i = info.data;
  return (
    <div className={styles.wrap}>
      <div className={styles.formSide}>
        <Brand />
        <div className={styles.formWrap}>
        <div className={styles.form}>
          {!token && <p className="notice block">This page needs the invite link HR sent you.</p>}
          {info.loading && <Loading what="invite" />}
          <ErrorNotice error={info.error} />
          {i && (
            <form className={styles.form} onSubmit={submit}>
              <p className={styles.eyebrow}>You’re invited</p>
              <h1>Join {i.company_name}</h1>
              <p className="muted">
                {i.role === "employee"
                  ? `You’ll be able to see your own payslips, SSF and CIT${i.employee_name ? ` as ${i.employee_name}` : ""}.`
                  : `You’re invited as ${ROLE_LABEL[i.role]}.`}
              </p>
              <ErrorNotice error={error} />
              <Field label="Email"><input value={i.email} readOnly /></Field>
              {i.has_account ? (
                <Field label="Your existing password" hint="You already have an AutoTax account with this email.">
                  <input name="password" type="password" autoComplete="current-password" required />
                </Field>
              ) : (
                <>
                  <Field label="Your name"><input name="name" autoComplete="name" required defaultValue={i.employee_name ?? ""} /></Field>
                  <Field label="Choose a password" hint="At least 8 characters.">
                    <input name="password" type="password" autoComplete="new-password" minLength={8} required />
                  </Field>
                </>
              )}
              <button className="btn" disabled={busy}>{busy ? "Joining…" : "Join"}</button>
            </form>
          )}
        </div>
        </div>
      </div>
      <Intro />
    </div>
  );
}
