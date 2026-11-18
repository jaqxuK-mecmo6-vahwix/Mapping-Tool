import type { Manifest, QueryResult } from "../engine/types";
import { GROWTH_PLUS, SHRINKING_POP_PER_YEAR, TIER_SETS, type TierDef, locationTier, tierSetFor } from "../engine/tier";
import { fmtPctPa } from "../lib/format";

const COLOURS: Record<string, string> = {
  A: "bg-emerald-700 text-white", B: "bg-sky-700 text-white", C: "bg-amber-700 text-white", D: "bg-slate-600 text-white",
};

const fmtThreshold = (t: TierDef) =>
  t.minGdpBn ? `≥ €${t.minGdpBn} bn GDP and ≥ ${t.minPop / 1e6} M people` : "below C";

const BUTTON = "shrink-0 rounded-md bg-white px-2 py-1 font-medium text-slate-900 ring-1 ring-slate-300 hover:bg-slate-100 focus-visible:outline-2 focus-visible:outline-orange-500";

/** Screening grade for a 25 km or 50 km circle; for other radii, buttons that set one of them. */
export default function TierCard({ m, r, onRadius }: { m: Manifest; r: QueryResult; onRadius(km: number): void }) {
  const t = locationTier(m, r);
  const others = TIER_SETS.filter((s) => s.radiusKm !== r.params.radiusKm);
  if (!t) {
    if (tierSetFor(r.params.radiusKm)) return null;   // data still loading
    return (
      <div className="flex flex-wrap items-center justify-between gap-2 rounded-lg bg-slate-50 px-3 py-2 text-xs text-slate-600 ring-1 ring-slate-200">
        <span>Location tiers are graded on {TIER_SETS.map((s) => `${s.radiusKm} km`).join(" or ")} circles.</span>
        <span className="flex gap-1.5">
          {TIER_SETS.map((s) => (
            <button key={s.radiusKm} type="button" onClick={() => onRadius(s.radiusKm)} className={BUTTON}>Use {s.radiusKm} km</button>
          ))}
        </span>
      </div>
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
          <p className="text-[11px] font-semibold tracking-wide text-slate-500 uppercase">{t.set.title} ({t.set.radiusKm} km)</p>
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
      <div className="mt-1.5 flex items-center justify-between gap-2 text-xs">
        <details className="min-w-0 text-slate-600">
        <summary className="cursor-pointer select-none text-slate-500 hover:text-slate-800">How tiers work</summary>
        <ul className="mt-1 space-y-0.5">
          {t.set.tiers.map((d) => <li key={d.tier}><strong>{d.tier}</strong> {d.name}: {fmtThreshold(d)}</li>)}
        </ul>
        <p className="mt-1">
          Both values must be met; GDP {m.years.gdp.latest} nominal in EUR, population {m.years.population.latest}.
          “+” = population ≥ {fmtPctPa(GROWTH_PLUS.popPerYear)} and real GDP ≥ {fmtPctPa(GROWTH_PLUS.realGdpPerYear)};
          “−” = population falling by more than {fmtPctPa(-SHRINKING_POP_PER_YEAR).replace("+", "")}.
          The {TIER_SETS[0].radiusKm} km city tier grades the city and its inner suburbs; the {TIER_SETS[1].radiusKm} km
          market tier grades the whole commuting region. A screening grade, not investment advice.
        </p>
        </details>
        {others.map((s) => (
          <button key={s.radiusKm} type="button" onClick={() => onRadius(s.radiusKm)} className={`${BUTTON} self-start`}>
            Compare {s.radiusKm} km
          </button>
        ))}
      </div>
    </section>
  );
}
