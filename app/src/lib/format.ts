/** Number formatting for the results panel (en-GB grouping). */
const LOCALE = "en-GB";

export function fmtInt(n: number): string {
  return Math.round(n).toLocaleString(LOCALE);
}

export function fmtPeople(n: number): string {
  if (n >= 1e6) return `${(n / 1e6).toLocaleString(LOCALE, { maximumFractionDigits: 2, minimumFractionDigits: 2 })} million`;
  return fmtInt(n);
}

/** Thousands of people per year, signed: "+12.3 thousand / yr". */
export function fmtThousandsPerYear(n: number): string {
  const v = n / 1000;
  const s = Math.abs(v) < 10 ? v.toFixed(2) : v.toFixed(1);
  return `${v > 0 ? "+" : ""}${s.replace("-", "−")} thousand / yr`;
}

/** Fraction as signed percent per year: 0.0123 -> "+1.23 % p.a." */
export function fmtPctPa(f: number): string {
  if (!Number.isFinite(f)) return "n/a";
  const v = f * 100;
  return `${v > 0 ? "+" : ""}${v.toFixed(2).replace("-", "−")} % p.a.`;
}

/** Millions of a currency -> "EUR 123.4 bn" (or "PPS 12.3 bn"). */
export function fmtMoneyMillions(m: number, currency: string): string {
  const bn = m / 1000;
  const digits = bn >= 100 ? 0 : bn >= 10 ? 1 : 2;
  if (bn >= 0.1) return `${currency} ${bn.toLocaleString(LOCALE, { maximumFractionDigits: digits, minimumFractionDigits: digits })} bn`;
  return `${currency} ${m.toLocaleString(LOCALE, { maximumFractionDigits: 1 })} m`;
}

export function fmtShare(f: number): string {
  return `${(f * 100).toFixed(f < 0.1 ? 1 : 0)} %`;
}

export function fmtKm(r: number): string {
  return `${r.toLocaleString(LOCALE, { maximumFractionDigits: 1 })} km`;
}
