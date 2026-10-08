"use client";

import {
  ArrowLeftRight,
  Banknote,
  Building2,
  History,
  KeyRound,
  Landmark,
  LayoutDashboard,
  LogOut,
  Menu,
  Monitor,
  Moon,
  Sun,
  Users,
  Wallet,
  type LucideIcon,
} from "lucide-react";
import Link from "next/link";
import { useParams, usePathname, useRouter } from "next/navigation";
import { createContext, useContext, useEffect, useRef, useState } from "react";

import { getToken, setToken } from "@/lib/api";
import { ROLE_LABEL } from "@/lib/format";
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

type NavItem = { href: string; label: string; icon: LucideIcon };
type NavGroup = { label: string | null; items: NavItem[] };

function navFor(role: Role | null, hasOwnRecord: boolean): NavGroup[] {
  if (role === null) return [];
  const mine: NavItem = { href: "/my", label: "My pay", icon: Wallet };
  if (role === "employee") return [{ label: null, items: [mine] }];
  const groups: NavGroup[] = [
    { label: null, items: [{ href: "", label: "Overview", icon: LayoutDashboard }] },
    {
      label: "Payroll",
      items: [
        { href: "/employees", label: "Employees", icon: Users },
        { href: "/payroll", label: "Payroll", icon: Banknote },
      ],
    },
    {
      label: "Reports",
      items: [
        { href: "/contributions", label: "SSF, CIT & TDS", icon: Landmark },
        { href: "/fx", label: "Exchange rates", icon: ArrowLeftRight },
      ],
    },
    {
      label: "Admin",
      items: [
        ...(role === "admin"
          ? [{ href: "/team", label: "Logins", icon: KeyRound }, { href: "/settings", label: "Company", icon: Building2 }]
          : []),
        { href: "/audit", label: "Activity", icon: History },
      ],
    },
  ];
  if (hasOwnRecord) groups.push({ label: "You", items: [mine] });
  return groups;
}

type Theme = "light" | "dark" | "system";

function readTheme(): Theme {
  try {
    const t = localStorage.getItem("autotax-theme");
    return t === "light" || t === "dark" ? t : "system";
  } catch {
    return "system";
  }
}

function useTheme(): [Theme, (t: Theme) => void] {
  const [theme, setThemeState] = useState<Theme>("system");
  useEffect(() => {
    const saved = readTheme();
    if (saved !== "system") setThemeState(saved); // eslint-disable-line react-hooks/set-state-in-effect
  }, []);
  const setTheme = (t: Theme) => {
    setThemeState(t);
    const root = document.documentElement;
    if (t === "system") root.removeAttribute("data-theme");
    else root.setAttribute("data-theme", t);
    try {
      if (t === "system") localStorage.removeItem("autotax-theme");
      else localStorage.setItem("autotax-theme", t);
    } catch {
      /* storage unavailable: theme lasts for this page only */
    }
  };
  return [theme, setTheme];
}

/** Small popover menu that closes on outside click or Escape. */
function Popover({ label, trigger, children }: {
  label: string;
  trigger: React.ReactNode;
  children: (close: () => void) => React.ReactNode;
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => ref.current && !ref.current.contains(e.target as Node) && setOpen(false);
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);
  return (
    <div className={styles.popWrap} ref={ref}>
      <button type="button" className={styles.ibtn} aria-label={label} aria-expanded={open} aria-haspopup="menu"
        onClick={() => setOpen(!open)}>
        {trigger}
      </button>
      {open && <div className={styles.pop} role="menu">{children(() => setOpen(false))}</div>}
    </div>
  );
}

function initials(name: string | undefined): string {
  if (!name) return "";
  return name.split(/\s+/).map((p) => p[0]).slice(0, 2).join("").toUpperCase();
}

export function Shell({ children }: { children: React.ReactNode }) {
  const { cid } = useParams<{ cid: string }>();
  const pathname = usePathname();
  const router = useRouter();
  const { data: me, error } = useData<Me>("/auth/me");
  const [theme, setTheme] = useTheme();
  const [drawerAt, setDrawerAt] = useState<string | null>(null);
  const drawer = drawerAt === pathname; // navigating closes the drawer

  useEffect(() => {
    if (!getToken()) router.replace("/login");
  }, [router]);

  const isEmployee = me?.memberships.find((m) => m.company_id === Number(cid))?.role === "employee";
  const onOwnPages = pathname.startsWith(`/c/${cid}/my`);
  useEffect(() => {
    // Employees only ever see their own pay; send them there from any HR page.
    if (isEmployee && !onOwnPages) router.replace(`/c/${cid}/my`);
  }, [isEmployee, onOwnPages, cid, router]);

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
    canEdit: membership !== null && membership.role !== "viewer" && membership.role !== "employee",
  };
  const groups = navFor(membership?.role ?? null, Boolean(membership?.employee_id));
  const ThemeIcon = theme === "dark" ? Moon : theme === "light" ? Sun : Monitor;

  return (
    <Ctx.Provider value={ctx}>
      <div className={`${styles.app} ${drawer ? styles.navOpen : ""}`}>
        <header className={styles.topbar}>
          <div className={styles.topLeft}>
            <button type="button" className={`${styles.ibtn} ${styles.menuBtn}`} aria-label="Open menu"
              aria-expanded={drawer} aria-controls="app-sidebar" onClick={() => setDrawerAt(drawer ? null : pathname)}>
              <Menu size={20} />
            </button>
            <Link href={isEmployee ? `${base}/my` : base} className={styles.brand}>
              <span className={styles.brandMark} aria-hidden="true">A</span>
              <span className={styles.brandStack}>
                <span className={styles.brandName}>AutoTax</span>
                <span className={styles.brandSub} lang="ne">कर हिसाब</span>
              </span>
            </Link>
            {me && me.memberships.length > 1 ? (
              <select className={styles.company} aria-label="Company" value={companyId}
                onChange={(e) => {
                  const m = me.memberships.find((x) => x.company_id === Number(e.target.value));
                  router.push(m?.role === "employee" ? `/c/${e.target.value}/my` : `/c/${e.target.value}`);
                }}>
                {me.memberships.map((m) => <option key={m.company_id} value={m.company_id}>{m.company_name}</option>)}
              </select>
            ) : (
              membership && <span className={styles.companyName}>{membership.company_name}</span>
            )}
          </div>
          <div className={styles.topRight}>
            <Popover label="Theme" trigger={<ThemeIcon size={18} />}>
              {(close) => (
                <>
                  <div className={styles.menuLabel}>Theme</div>
                  {([["light", "Light", Sun], ["dark", "Dark", Moon], ["system", "Match device", Monitor]] as const).map(([t, label, Icon]) => (
                    <button key={t} type="button" role="menuitemradio" aria-checked={theme === t} className={styles.menuItem}
                      onClick={() => { setTheme(t); close(); }}>
                      <Icon size={16} />{label}
                    </button>
                  ))}
                </>
              )}
            </Popover>
            <Popover label={`Account menu for ${me?.name ?? ""}`} trigger={
              <span className={styles.userTrigger}>
                <span className={styles.avatar} aria-hidden="true">{initials(me?.name)}</span>
                <span className={styles.userName}>{me?.name}</span>
              </span>
            }>
              {() => (
                <>
                  <div className={styles.userId}>
                    <span className={`${styles.avatar} ${styles.avatarLg}`} aria-hidden="true">{initials(me?.name)}</span>
                    <span>
                      <span className={styles.userIdName}>{me?.name}</span>
                      <span className={styles.userIdRole}>{membership ? ROLE_LABEL[membership.role] : ""}</span>
                      <span className={styles.userIdRole}>{me?.email}</span>
                    </span>
                  </div>
                  <hr className={styles.menuSep} />
                  <button type="button" role="menuitem" className={styles.menuItem}
                    onClick={() => { setToken(null); router.replace("/login"); }}>
                    <LogOut size={16} />Sign out
                  </button>
                </>
              )}
            </Popover>
          </div>
        </header>

        <aside className={styles.sidebar} id="app-sidebar" aria-label="Main menu">
          <nav className={styles.nav} aria-label="Primary">
            {groups.map((g, i) => (
              <div key={g.label ?? i}>
                {g.label && <div className={styles.navLabel}>{g.label}</div>}
                {g.items.map((n) => {
                  const href = base + n.href;
                  const active = n.href === "" ? pathname === base : pathname.startsWith(href);
                  const Icon = n.icon;
                  return (
                    <Link key={n.href} href={href} className={styles.navItem} aria-current={active ? "page" : undefined}>
                      <Icon size={16} aria-hidden="true" />
                      <span>{n.label}</span>
                    </Link>
                  );
                })}
              </div>
            ))}
          </nav>
        </aside>
        <div className={styles.scrim} onClick={() => setDrawerAt(null)} aria-hidden="true" />

        <main className={styles.main}>
          <div className={styles.inner}>
            {error ? (
              <p className="notice block">Couldn’t load your account: {error.message}</p>
            ) : isEmployee && !onOwnPages ? null : noAccess ? (
              <div className="empty">
                <p>You don’t have access to this company.</p>
                <Link className="btn" href="/">Go to your companies</Link>
              </div>
            ) : (
              children
            )}
          </div>
        </main>
      </div>
    </Ctx.Provider>
  );
}
