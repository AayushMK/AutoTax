/** Exact decimal arithmetic on money strings, in paisa/cents as BigInt. Never floats. */

const TEN = BigInt(10);

function scaled(v: string, scale: number): bigint {
  const s = v.trim();
  const neg = s.startsWith("-");
  const [i, f = ""] = s.replace(/^[-+]/, "").split(".");
  const n = BigInt(i || "0") * TEN ** BigInt(scale) + BigInt((f + "0".repeat(scale)).slice(0, scale) || "0");
  return neg ? -n : n;
}

/** Integer division rounding half away from zero (the same as Python's ROUND_HALF_UP on money). */
function divRound(a: bigint, b: bigint): bigint {
  const neg = (a < BigInt(0)) !== (b < BigInt(0));
  const [x, y] = [a < BigInt(0) ? -a : a, b < BigInt(0) ? -b : b];
  const q = (x * BigInt(2) + y) / (y * BigInt(2));
  return neg ? -q : q;
}

export function cents(v: string | null | undefined): bigint {
  return v ? scaled(v, 2) : BigInt(0);
}

export function fromCents(c: bigint): string {
  const neg = c < BigInt(0);
  const a = neg ? -c : c;
  return `${neg ? "-" : ""}${a / BigInt(100)}.${(a % BigInt(100)).toString().padStart(2, "0")}`;
}

/** amount (in `currency` cents) × rate / unit × share, as NPR cents. rate has up to 6 decimals. */
export function toNprCents(amountCents: bigint, rate: string, unit: number, share: [number, number] = [1, 1]): bigint {
  const r = scaled(rate, 6);
  return divRound(amountCents * r * BigInt(share[0]), BigInt(unit) * BigInt(share[1]) * TEN ** BigInt(6));
}

/** NPR cents ÷ (rate / unit), as cents of the foreign currency. */
export function fromNprCents(nprCents: bigint, rate: string, unit: number): bigint {
  return divRound(nprCents * BigInt(unit) * TEN ** BigInt(6), scaled(rate, 6));
}

export function sumCents(xs: bigint[]): bigint {
  return xs.reduce((a, b) => a + b, BigInt(0));
}
