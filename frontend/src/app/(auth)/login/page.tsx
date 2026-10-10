"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { ErrorNotice, Field } from "@/components/bits";
import { api, setToken } from "@/lib/api";
import { homeFor } from "@/lib/home";
import type { Me } from "@/lib/types";

import styles from "../auth.module.css";
import { AuthFrame, Headline } from "../intro";

export default function Login() {
  const router = useRouter();
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = e.currentTarget;
    const f = new FormData(e.currentTarget);
    setBusy(true);
    setError(null);
    try {
      const { token } = await api<{ token: string }>("/auth/login", { method: "POST", json: Object.fromEntries(f) });
      setToken(token);
      const me = await api<Me>("/auth/me");
      router.replace(homeFor(me));
      form.reset(); // don't leave the password in a page Next may keep in memory
      setBusy(false);
    } catch (err) {
      setError(err);
      setBusy(false);
    }
  }

  return (
    <AuthFrame topLink={{ href: "/signup", label: "Set up a company" }}>
      <form className={styles.form} onSubmit={submit}>
        <Headline before="Salary tax," pill="worked out." after="" sub="Sign in to your AutoTax account" />
        <ErrorNotice error={error} />
        <Field label="Email"><input name="email" type="email" autoComplete="email" placeholder="you@company.com" required /></Field>
        <Field label="Password"><input name="password" type="password" autoComplete="current-password" required /></Field>
        <button className="btn" disabled={busy}>{busy ? "Signing in…" : "Continue"}</button>
        <p className={styles.switch}>New here? <Link href="/signup">Set up your company</Link></p>
        <p className={styles.fine}>Employees: use the invite link HR sent you to set your password the first time.</p>
      </form>
    </AuthFrame>
  );
}
