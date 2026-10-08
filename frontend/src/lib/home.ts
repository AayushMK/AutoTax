import type { Me } from "./types";

/** Where a signed-in person lands: employees go to their own pay, HR to the company overview. */
export function homeFor(me: Me): string {
  const m = me.memberships[0];
  if (!m) return "/signup";
  return m.role === "employee" ? `/c/${m.company_id}/my` : `/c/${m.company_id}`;
}
