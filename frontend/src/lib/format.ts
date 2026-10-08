/** Format a decimal string the Nepali way (lakh/crore grouping): 12,34,567.89. No floats. */
export function money(v: string | null | undefined, places = 2): string {
  if (v === null || v === undefined || v === "") return "—";
  const s = String(v).trim();
  const neg = s.startsWith("-");
  const [intRaw, frac = ""] = s.replace(/^[-+]/, "").split(".");
  const int = intRaw.replace(/^0+(?=\d)/, "") || "0";
  const last3 = int.slice(-3);
  const rest = int.slice(0, -3);
  const grouped = rest ? `${rest.replace(/\B(?=(\d{2})+(?!\d))/g, ",")},${last3}` : last3;
  const f = places > 0 ? `.${(frac + "0".repeat(places)).slice(0, places)}` : "";
  return `${neg ? "−" : ""}${grouped}${f}`;
}

export function isZero(v: string | null | undefined): boolean {
  return !v || /^-?0*(\.0*)?$/.test(v);
}

export function date(d: string | null | undefined): string {
  if (!d) return "—";
  const x = new Date(d.length === 10 ? `${d}T00:00:00` : d);
  return x.toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });
}

export function dateTime(d: string | null | undefined): string {
  if (!d) return "—";
  return new Date(d).toLocaleString("en-GB", { day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" });
}

export const ROLE_LABEL: Record<string, string> = {
  admin: "HR admin",
  accountant: "HR / payroll",
  viewer: "Auditor (read only)",
  employee: "Employee",
};

/** Add two decimal strings exactly (2 places). */
export function addMoney(a: string | undefined, b: string | undefined): string {
  const cents = (v?: string) => {
    if (!v) return BigInt(0);
    const neg = v.startsWith("-");
    const [i, f = ""] = v.replace(/^[-+]/, "").split(".");
    const n = BigInt(i || "0") * BigInt(100) + BigInt((f + "00").slice(0, 2));
    return neg ? -n : n;
  };
  const t = cents(a) + cents(b);
  const neg = t < BigInt(0);
  const abs = neg ? -t : t;
  const s = `${abs / BigInt(100)}.${(abs % BigInt(100)).toString().padStart(2, "0")}`;
  return neg ? `-${s}` : s;
}

export const KIND_LABEL: Record<string, string> = {
  basic: "Basic salary",
  allowance: "Allowance",
  bonus: "Bonus",
  dashain: "Dashain allowance",
  overtime: "Overtime",
  benefit: "Taxable benefit",
  other: "Other income",
};

/** Human names for rule parameters shown in review lists. */
export const PARAM_LABEL: Record<string, string> = {
  "resident.slabs.single": "Tax slabs (individual)",
  "resident.slabs.couple": "Tax slabs (couple)",
  "resident.sst_waiver_schemes": "Social security tax waiver",
  "resident.disability_first_slab_increase": "Disability: first slab increase",
  "nonresident.flat_rate": "Non-resident rate",
  "retirement.cap_amount": "Retirement deduction cap",
  "retirement.cap_fraction": "Retirement deduction: share of income",
  "ssf.employee_rate": "SSF employee rate",
  "ssf.employer_rate": "SSF employer rate",
  "ssf.employer_contribution_taxable": "Employer SSF counted as income",
  "insurance.life_cap": "Life insurance cap",
  "insurance.health_cap": "Health insurance cap",
  "insurance.building_cap": "Building insurance cap",
  "remote_area.caps": "Remote area deductions",
  "donation.cap_amount": "Donation cap",
  "donation.cap_fraction": "Donation: share of income",
  "female_rebate.rate": "Women's tax rebate",
  "female_rebate.excluded_if_couple": "Women's rebate on couple filing",
  "fx.rate_type": "Exchange rate used (buying/selling)",
  "fx.date_basis": "Exchange rate date",
  "rounding.tds_places": "TDS rounding",
};
