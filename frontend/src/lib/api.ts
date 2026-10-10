"use client";

const TOKEN_KEY = "autotax.token";

export function getToken(): string | null {
  try {
    return localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function setToken(token: string | null) {
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token);
    else localStorage.removeItem(TOKEN_KEY);
  } catch {
    /* storage unavailable: session-only sign-in */
  }
}

/**
 * Sign out with a full page load. Next keeps pages you've visited alive in memory, so a
 * client-side navigation would bring back the old login form (still "Signing in…", with the
 * password filled in) and the previous user's data. A reload drops all of it.
 */
export function signOut() {
  setToken(null);
  window.location.replace("/login");
}

export class ApiError extends Error {
  status: number;
  problems: string[];
  code?: string;
  detail: unknown;

  constructor(status: number, detail: unknown) {
    const d = detail as { message?: string; problems?: string[]; code?: string } | string | { msg: string }[] | undefined;
    let message = `Request failed (${status})`;
    let problems: string[] = [];
    let code: string | undefined;
    if (typeof d === "string") message = d;
    else if (Array.isArray(d)) problems = d.map((e) => e.msg);
    else if (d && typeof d === "object") {
      message = d.message ?? message;
      problems = d.problems ?? [];
      code = d.code;
    }
    if (Array.isArray(d)) message = "Some fields need fixing";
    super(message);
    this.status = status;
    this.problems = problems;
    this.code = code;
    this.detail = detail;
  }
}

export async function api<T = unknown>(path: string, init: RequestInit & { json?: unknown } = {}): Promise<T> {
  const headers = new Headers(init.headers);
  const token = getToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  let body = init.body;
  if (init.json !== undefined) {
    headers.set("Content-Type", "application/json");
    body = JSON.stringify(init.json);
  }
  const res = await fetch(`/api${path}`, { ...init, headers, body });
  if (res.status === 401 && !path.startsWith("/auth/login")) {
    setToken(null);
    if (typeof window !== "undefined" && !window.location.pathname.startsWith("/login")) {
      // Full reload on purpose: an expired session should drop all in-memory company data.
      // eslint-disable-next-line @next/next/no-location-assign-relative-destination
      window.location.href = "/login";
    }
  }
  if (!res.ok) {
    let detail: unknown;
    try {
      detail = (await res.json()).detail;
    } catch {
      detail = res.statusText;
    }
    throw new ApiError(res.status, detail);
  }
  if (res.status === 204) return undefined as T;
  const type = res.headers.get("content-type") ?? "";
  return (type.includes("application/json") ? res.json() : res.text()) as Promise<T>;
}

export async function download(path: string, filename: string) {
  const res = await fetch(`/api${path}`, { headers: { Authorization: `Bearer ${getToken() ?? ""}` } });
  if (!res.ok) throw new ApiError(res.status, res.statusText);
  const url = URL.createObjectURL(await res.blob());
  const a = Object.assign(document.createElement("a"), { href: url, download: filename });
  a.click();
  URL.revokeObjectURL(url);
}
