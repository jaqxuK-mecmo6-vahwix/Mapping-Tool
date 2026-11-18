import type { Manifest, QueryResult } from "../engine/types";
import { GROWTH_PLUS, SHRINKING_POP_PER_YEAR, TIER_RADIUS_KM, TIERS, locationTier } from "../engine/tier";
import { fmtPctPa } from "../lib/format";

const COLOURS: Record<string, string> = {
  A: "bg-emerald-700 text-white", B: "bg-sky-700 text-white", C: "bg-amber-700 text-white", D: "bg-slate-600 text-white",
};

const fmtThreshold = (t: (typeof TIERS)[number]) =>
  t.minGdpBn ? `≥ €${t.minGdpBn} bn GDP and ≥ ${t.minPop / 1e6} M people` : "below C";

/** Screening grade for a 50 km circle; for other radii, a button that sets 50 km. */
export default function TierCard({ m, r, onRadius }: { m: Manifest; r: QueryResult; onRadius(km: number): void }) {
  const t = locationTier(m, r);
  if (!t) {
    if (r.params.radiusKm === TIER_RADIUS_KM) return null;   // data still loading
    return (
      <p className="flex items-center justify-between gap-2 rounded-lg bg-slate-50 px-3 py-2 text-xs text-slate-600 ring-1 ring-slate-200">
        Location tier is graded on a {TIER_RADIUS_KM} km circle.
        <button type="button" onClick={() => onRadius(TIER_RADIUS_KM)}
          className="shrink-0 rounded-md bg-white px-2 py-1 font-medium text-slate-900 ring-1 ring-slate-300 hover:bg-slate-100 focus-visible:outline-2 focus-visible:outline-orange-500">
          Use {TIER_RADIUS_KM} km
        </button>
      </p>
    );
  }
  const signText = t.sign === "+" ? `+ growing fast: population ${fmtPctPa(t.popGrowth)} and real GDP ${fmtPctPa(t.realGdpGrowth)} over ${t.years} years`
    : t.sign === "−" ? `− population shrinking: ${fmtPctPa(t.popGrowth)} over ${t.years} years`
    : `no sign: population ${fmtPctPa(t.popGrowth)}, real GDP ${fmtPctPa(t.realGdpGrowth)} over ${t.years} years`;
  return (
    <section aria-label="Location tier" className="rounded-lg px-3 py-2.5 ring-1 ring-slate-200">
      <div className="flex items-center gap-3">
        <span className={`flex h-11 min-w-11 items-center justify-center rounded-lg px-1.5 text-xl font-bold ${COLOURS[t.def.tier]}`}>
          {t.label}
        </span>
        <div className="min-w-0">
          <p className="text-[11px] font-semibold tracking-wide text-slate-500 uppercase">Location tier ({TIER_RADIUS_KM} km)</p>
          <p className="text-sm font-medium text-slate-900">{t.def.name}</p>
          <p className="text-xs text-slate-600">{fmtThreshold(t.def)}</p>
        </div>
      </div>
      <p className="mt-2 text-xs text-slate-600">{signText}.</p>
      {t.nearUp && (
        <p className="mt-1 text-xs text-slate-700"><strong>Borderline:</strong> within 5% of tier {t.nearUp.tier}.</p>
      )}
      {t.irelandDistorted && (
        <p className="mt-1 text-xs text-amber-900">
          <strong>Irish GDP</strong> is inflated by multinational profits booked in Ireland; judge this area by population.
        </p>
      )}
      <details className="mt-1.5 text-xs text-slate-600">
        <summary className="cursor-pointer select-none text-slate-500 hover:text-slate-800">How tiers work</summary>
        <ul className="mt-1 space-y-0.5">
          {TIERS.map((d) => <li key={d.tier}><strong>{d.tier}</strong> {d.name}: {fmtThreshold(d)}</li>)}
        </ul>
        <p className="mt-1">
          Both values must be met; GDP {m.years.gdp.latest} nominal in EUR, population {m.years.population.latest}.
          “+” = population ≥ {fmtPctPa(GROWTH_PLUS.popPerYear)} and real GDP ≥ {fmtPctPa(GROWTH_PLUS.realGdpPerYear)};
          “−” = population falling by more than {fmtPctPa(-SHRINKING_POP_PER_YEAR).replace("+", "")}. A screening grade, not investment advice.
        </p>
      </details>
    </section>
  );
}
