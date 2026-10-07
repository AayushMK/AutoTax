"use client";

import { ApiError } from "@/lib/api";
import { money } from "@/lib/format";

export function Num({ v, places }: { v: string | null | undefined; places?: number }) {
  return <span className="figure">{money(v, places)}</span>;
}

export function ErrorNotice({ error }: { error: unknown }) {
  if (!error) return null;
  const e = error instanceof ApiError ? error : null;
  return (
    <div className="notice block" role="alert">
      <strong>{e?.message ?? String(error)}</strong>
      {e && e.problems.length > 0 && (
        <ul>
          {e.problems.map((p) => (
            <li key={p}>{p}</li>
          ))}
        </ul>
      )}
    </div>
  );
}

export function Loading({ what }: { what: string }) {
  return <p className="muted" aria-live="polite">Loading {what}…</p>;
}

export function Field({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return (
    <label className="field">
      <span>{label}</span>
      {children}
      {hint && <small>{hint}</small>}
    </label>
  );
}
