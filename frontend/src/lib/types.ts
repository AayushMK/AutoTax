// Money and rates arrive as decimal strings from the API and are never converted to floats.
export type Money = string;
export type Role = "admin" | "accountant" | "viewer" | "employee";

export interface Me {
  id: number;
  email: string;
  name: string;
  memberships: { company_id: number; company_name: string; role: Role; employee_id: number | null }[];
}

export interface Employee {
  id: number;
  code: string;
  name: string;
  pan: string | null;
  email: string | null;
  joined_on: string;
  left_on: string | null;
}

export interface TaxProfile {
  fiscal_year: string;
  resident: boolean;
  filing: "single" | "couple";
  gender: "male" | "female" | "other";
  disabled: boolean;
  ssf_enrolled: boolean;
  approved_pension: boolean;
  remote_area: "A" | "B" | "C" | "D" | "E" | null;
  income_only_from_employment: boolean;
  life_insurance_premium: Money;
  health_insurance_premium: Money;
  building_insurance_premium: Money;
  donation: Money;
}

export interface Component {
  kind: IncomeKind;
  amount: Money;
  currency: string;
  description: string;
}

export type IncomeKind = "basic" | "allowance" | "bonus" | "dashain" | "overtime" | "benefit" | "other";

export interface SalaryStructure {
  id: number;
  effective_from: string;
  components: Component[];
  cit_monthly: Money;
  other_retirement_monthly: Money;
}

export interface EmployeeDetail extends Employee {
  tax_profiles: TaxProfile[];
  salary_structures: SalaryStructure[];
}

export interface Run {
  id: number;
  fiscal_year: string;
  month: number;
  month_label: string;
  payment_date: string;
  status: "draft" | "finalized";
  rule_set: string | null;
  rule_review_status: string | null;
  warnings: string[];
  acknowledged_unverified: string[];
  computed_at: string | null;
  finalized_at: string | null;
}

export interface PayslipSummary {
  id: number;
  employee_id: number;
  employee_code: string;
  employee_name: string;
  gross: Money;
  ssf_employee: Money;
  ssf_employer: Money;
  cit: Money;
  tds: Money;
  net_pay: Money;
  projected_annual_tax: Money;
}

export interface Adjustment {
  id: number;
  employee_id: number;
  kind: string;
  amount: Money;
  currency: string;
  description: string;
}

export interface RunDetail extends Run {
  payslips: PayslipSummary[];
  adjustments: Adjustment[];
  totals: Record<"gross" | "ssf_employee" | "ssf_employer" | "cit" | "tds" | "net_pay", Money>;
}

export interface TraceStep {
  label: string;
  amount: Money;
  detail: string;
  citation: { key: string; ref: string; source: string; status: "verified" | "corroborated" | "needs_review" } | null;
}

export interface PayslipDetail extends PayslipSummary {
  month: number;
  basic: Money;
  other_retirement: Money;
  projected_taxable_income: Money;
  inputs: {
    rule_set: string;
    lines: { kind: string; amount: Money; currency: string; recurring: boolean; description: string }[];
    fx: Record<string, { on: string; buy: string; sell: string; unit: number; source: string; override_reason: string | null }>;
    profile: Record<string, unknown>;
  };
  trace: TraceStep[];
}

export interface RuleSummary {
  version: string;
  fiscal_year: string;
  effective_from: string;
  effective_to: string;
  review_status: "draft" | "ca_reviewed";
  unverified_params: string[];
}

export interface RulesStatus {
  date: string;
  current: (RuleSummary & { sources: Record<string, boolean | null> }) | null;
  alert: string | null;
  all: RuleSummary[];
}

export interface FxRate {
  currency: string;
  on: string;
  buy: Money;
  sell: Money;
  unit: number;
  source: string;
  override_reason: string | null;
}

export interface AuditEntry {
  id: number;
  user_id: number | null;
  action: string;
  entity: string;
  entity_id: number | null;
  data: Record<string, unknown>;
  at: string;
}

export interface StatementMonth {
  month: number;
  month_label: string;
  status: "draft" | "finalized" | null;
  payment_date?: string;
  payslip_id?: number;
  run_id?: number;
  gross?: Money;
  ssf_employee?: Money;
  ssf_employer?: Money;
  cit?: Money;
  other_retirement?: Money;
  tds?: Money;
  net_pay?: Money;
}

export interface AnnualStatement {
  employee: { id: number; code: string; name: string; pan: string | null };
  fiscal_year: string;
  months: StatementMonth[];
  totals: Record<"gross" | "ssf_employee" | "ssf_employer" | "ssf_total" | "cit" | "other_retirement" | "tds" | "net_pay", Money>;
  months_paid: number;
  projected_annual_tax: Money | null;
  tds_remaining: Money | null;
}

type Contribution = Record<"ssf_employee" | "ssf_employer" | "cit", Money>;

export interface ContributionsReport {
  fiscal_year: string;
  months: ({ month: number; month_label: string; status: "draft" | "finalized" | null } & Contribution)[];
  employees: { employee_id: number; code: string; name: string; months: Record<string, Contribution>; totals: Contribution }[];
  totals: Contribution & { ssf_total: Money };
}

export interface Member {
  user_id: number;
  email: string;
  name: string;
  role: Role;
  employee_id: number | null;
  employee_name: string | null;
}

export interface Invite {
  id: number;
  email: string;
  role: Role;
  employee_id: number | null;
  employee_name: string | null;
  expires_at: string;
  token?: string | null;
}
