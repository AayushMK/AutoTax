"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { ErrorNotice, Field } from "@/components/bits";
import { api, setToken } from "@/lib/api";
import type { Me } from "@/lib/types";

import styles from "../auth.module.css";
import { Intro } from "../intro";

export default function Signup() {
  const router = useRouter();
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = Object.fromEntries(new FormData(e.currentTarget)) as Record<string, string>;
    setBusy(true);
    setError(null);
    try {
      const { token } = await api<{ token: string }>("/auth/signup", {
        method: "POST",
        json: { ...f, company_pan: f.company_pan || null },
      });
      setToken(token);
      const me = await api<Me>("/auth/me");
      router.replace(`/c/${me.memberships[0].company_id}`);
    } catch (err) {
      setError(err);
      setBusy(false);
    }
  }

  return (
    <div className={styles.wrap}>
      <Intro />
      <div className={styles.formSide}>
        <form className={styles.form} onSubmit={submit}>
          <h1>Set up your company</h1>
          <ErrorNotice error={error} />
          <Field label="Company name"><input name="company_name" required /></Field>
          <Field label="Company PAN" hint="Optional. Printed on TDS sheets."><input name="company_pan" inputMode="numeric" /></Field>
          <Field label="Your name"><input name="name" autoComplete="name" required /></Field>
          <Field label="Email"><input name="email" type="email" autoComplete="email" required /></Field>
          <Field label="Password" hint="At least 8 characters.">
            <input name="password" type="password" autoComplete="new-password" minLength={8} required />
          </Field>
          <button className="btn" disabled={busy}>{busy ? "Creating…" : "Create company"}</button>
          <p className={styles.switch}>Already have an account? <Link href="/login">Sign in</Link></p>
        </form>
      </div>
    </div>
  );
}
