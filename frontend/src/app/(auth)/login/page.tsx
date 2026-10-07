"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { ErrorNotice, Field } from "@/components/bits";
import { api, setToken } from "@/lib/api";
import type { Me } from "@/lib/types";

import styles from "../auth.module.css";
import { Intro } from "../intro";

export default function Login() {
  const router = useRouter();
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    setBusy(true);
    setError(null);
    try {
      const { token } = await api<{ token: string }>("/auth/login", { method: "POST", json: Object.fromEntries(f) });
      setToken(token);
      const me = await api<Me>("/auth/me");
      router.replace(me.memberships.length ? `/c/${me.memberships[0].company_id}` : "/signup");
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
          <h1>Sign in</h1>
          <ErrorNotice error={error} />
          <Field label="Email"><input name="email" type="email" autoComplete="email" required /></Field>
          <Field label="Password"><input name="password" type="password" autoComplete="current-password" required /></Field>
          <button className="btn" disabled={busy}>{busy ? "Signing in…" : "Sign in"}</button>
          <p className={styles.switch}>New company? <Link href="/signup">Create an account</Link></p>
        </form>
      </div>
    </div>
  );
}
