/** Notion-style hues, picked stably per id so a person keeps their colour everywhere. */
export const HUES = ["blue", "green", "orange", "purple", "pink", "yellow", "red", "brown"] as const;
export type Hue = (typeof HUES)[number] | "gray";

export function hueFor(id: number | string): Hue {
  const n = typeof id === "number" ? id : [...id].reduce((a, c) => a + c.charCodeAt(0), 0);
  return HUES[Math.abs(n) % HUES.length];
}

export function initials(name: string | undefined | null): string {
  if (!name) return "";
  return name.split(/\s+/).map((p) => p[0]).slice(0, 2).join("").toUpperCase();
}
