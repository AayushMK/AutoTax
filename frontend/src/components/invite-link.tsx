"use client";

import { useState } from "react";

import type { Invite } from "@/lib/types";

/** Shows a freshly created invite link once, with a copy button. */
export function InviteLink({ invite }: { invite: Invite }) {
  const [copied, setCopied] = useState(false);
  const url = `${typeof window === "undefined" ? "" : window.location.origin}/join?token=${invite.token}`;
  return (
    <div className="notice ok" role="status">
      <p>
        Send this link to <strong>{invite.email}</strong>. It works once and expires in 7 days. They choose their own password.
      </p>
      <div className="row" style={{ marginTop: "0.5rem" }}>
        <input readOnly value={url} aria-label="Invite link" className="figure" style={{ flex: "1 1 20rem" }}
          onFocus={(e) => e.currentTarget.select()} />
        <button className="btn small" type="button" onClick={async () => {
          try {
            await navigator.clipboard.writeText(url);
            setCopied(true);
          } catch {
            setCopied(false);
          }
        }}>
          {copied ? "Copied" : "Copy link"}
        </button>
      </div>
      <p className="small muted" style={{ marginTop: "0.4rem" }}>This link isn’t shown again. If it’s lost, cancel it and create a new one.</p>
    </div>
  );
}
