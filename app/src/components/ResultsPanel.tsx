import type { FxTable, Manifest, QueryResult } from "../engine/types";
import { currencyOptions, gdpSummary, populationSummary } from "../engine/stats";
import { fmtKm, fmtMoneyMillions, fmtPctPa, fmtPeople, fmtShare, fmtThousandsPerYear } from "../lib/format";
import type { LayerKey, Measure } from "../lib/urlState";
import { Notice, Segmented } from "./ui";

interface Props {
  manifest: Manifest;
  fx: FxTable;
  result: QueryResult | null;
  partial: boolean;
  loading: boolean;
  error: string | null;
  layer: LayerKey;
  measure: Measure;
  currency: string;
  hasPoint: boolean;
  onMeasure(m: Measure): void;
  onCurrency(c: string): void;
}

const nameOf = (m: Manifest, code: string) =>
  m.countries.find((c) => c.code === code)?.name ?? (code === "other" ? "Outside coverage" : code);

function Breakdown({ m, rows, format, label }: {
  m: Manifest; rows: Record<string, number>; format: (v: number) => string; label: string;
}) {
  const entries = Object.entries(rows).filter(([, v]) => v > 0).sort((a, b) => b[1] - a[1]);
  const total = entries.reduce((s, [, v]) => s + v, 0);
  if (!entries.length) return null;
  return (
    <table className="w-full text-xs">
      <caption className="pb-1 text-left text-[11px] font-semibold tracking-wide text-slate-500 uppercase">{label}</caption>
      <thead className="sr-only"><tr><th>Country</th><th>Value</th><th>Share</th></tr></thead>
      <tbody>
        {entries.map(([code, v]) => (
          <tr key={code} className="border-t border-slate-100">
            <th scope="row" className="py-1 text-left font-normal text-slate-700">{nameOf(m, code)}</th>
            <td className="py-1 text-right tabular-nums text-slate-900">{format(v)}</td>
            <td className="w-14 py-1 text-right tabular-nums text-slate-500">{fmtShare(v / total)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function GrowthTable({ caption, rows }: { caption: string; rows: { label: string; a?: string; b: string }[] }) {
  return (
    <table className="w-full text-sm">
      <caption className="pb-1 text-left text-[11px] font-semibold tracking-wide text-slate-500 uppercase">{caption}</caption>
      <thead className="sr-only"><tr><th>Period</th>{rows[0]?.a !== undefined && <th>Change per year</th>}<th>Growth rate</th></tr></thead>
      <tbody>
        {rows.map((r) => (
          <tr key={r.label} className="border-t border-slate-100">
            <th scope="row" className="py-1.5 text-left text-xs font-normal text-slate-600">{r.label}</th>
            {r.a !== undefined && <td className="py-1.5 text-right tabular-nums text-slate-900">{r.a}</td>}
            <td className="py-1.5 pl-2 text-right whitespace-nowrap tabular-nums font-medium text-slate-900">{r.b}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export default function ResultsPanel(p: Props) {
  const { manifest: m, fx, result: r } = p;
  if (!p.hasPoint) {
    return (
      <div className="space-y-2 text-sm text-slate-700">
        <p className="font-medium text-slate-900">Pick a point</p>
        <p>Tap or click the map, or search for a place. Drag the marker to move it; change the radius with the slider.</p>
      </div>
    );
  }
  if (p.error) return <Notice tone="warn">Could not compute this circle: {p.error}</Notice>;
  if (!r) return <p className="text-sm text-slate-600" role="status">Calculating…</p>;

  const radius = r.params.radiusKm;
  const partialCoverage = r.landKm2 > 0 && r.coveredShare < 0.995;
  const notices = (
    <>
      {partialCoverage && (
        <Notice tone="warn">
          <strong>Partial coverage:</strong> {fmtShare(r.coveredShare)} of the land in this circle is covered.
          Totals include covered countries only.
        </Notice>
      )}
      {r.landKm2 === 0 && <Notice tone="info">This circle contains no covered land.</Notice>}
    </>
  );

  const busy = (p.loading || p.partial) && <span className="text-xs font-normal text-slate-500">updating…</span>;

  if (p.layer === "population") {
    if (!r.layers[`pop_${m.years.population.latest}`]) return <p className="text-sm text-slate-600" role="status">Calculating…</p>;
    const s = populationSummary(m, r);
    return (
      <div className="space-y-3">
        <div aria-live="polite">
          <h2 className="flex items-baseline justify-between text-xs font-semibold tracking-wide text-slate-500 uppercase">
            Population within {fmtKm(radius)} {busy}
          </h2>
          <p className="text-3xl font-semibold tracking-tight text-slate-900 tabular-nums">{fmtPeople(s.total)}</p>
          <p className="text-xs text-slate-500">on 1 January {s.year}</p>
        </div>
        {notices}
        <GrowthTable caption="Growth per year"
          rows={s.growth.map((g) => ({ label: `${g.years} years (${g.fromYear}–${g.toYear})`, a: fmtThousandsPerYear(g.absPerYear), b: fmtPctPa(g.pctPerYear) }))} />
        <Breakdown m={m} rows={s.byCountry} format={fmtPeople} label="By country" />
        <p className="text-[11px] leading-snug text-slate-500">
          Reference years: population on 1 January {s.year}, compared with {m.years.population.compare.join(", ")}.
          Census 2021 1 km grid rescaled to each year's NUTS 3 totals.
        </p>
      </div>
    );
  }

  // GDP
  const g = m.years.gdp;
  if (!r.layers[`gdp_nom_eur_${g.latest}`] || !r.layers[`gdp_real_${g.latest}`]) {
    return <p className="text-sm text-slate-600" role="status">Calculating…</p>;
  }
  const options = currencyOptions(fx, r.pointCountry);
  const currency = options.includes(p.currency) ? p.currency : "EUR";
  const measure = currency !== "EUR" ? "nominal" : p.measure;
  const s = gdpSummary(m, fx, r, measure, currency);
  const unitLabel = measure === "pps" ? "PPS" : currency;
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap gap-2">
        <div className="min-w-48 flex-1">
          <Segmented label="GDP measure" size="sm" value={measure} onChange={p.onMeasure}
            options={[
              { value: "nominal", label: "Nominal (current prices)" },
              { value: "pps", label: "PPS", disabled: currency !== "EUR",
                title: currency !== "EUR" ? "PPS is shown in the EUR view only" : "Purchasing power standards" },
            ]} />
        </div>
        {options.length > 1 && (
          <div className="w-32">
            <Segmented label="Currency" size="sm" value={currency} onChange={p.onCurrency}
              options={options.map((c) => ({ value: c, label: c }))} />
          </div>
        )}
      </div>
      <div aria-live="polite">
        <h2 className="flex items-baseline justify-between text-xs font-semibold tracking-wide text-slate-500 uppercase">
          GDP within {fmtKm(radius)} {busy}
        </h2>
        <p className="text-3xl font-semibold tracking-tight text-slate-900 tabular-nums">{fmtMoneyMillions(s.totalMillions, unitLabel)}</p>
        <p className="text-xs text-slate-500">
          {s.year}, {measure === "pps" ? "purchasing power standards (EU27 2020)" : "current prices"}
          {currency !== "EUR" && `, converted at the ${fx.reference_year} average rate (1 EUR = ${fx.rates[currency][String(fx.reference_year)]} ${currency})`}
        </p>
      </div>
      {s.lowConfidence && (
        <Notice tone="warn">
          <strong>Low confidence:</strong> below {m.low_confidence_gdp_radius_km} km, GDP mostly reflects how regional GDP was
          spread over cells by population. Workplace centres are under-, residential areas over-stated.
        </Notice>
      )}
      {notices}
      <GrowthTable caption="Real GDP growth per year (constant prices)"
        rows={s.realGrowth.map((x) => ({ label: `${x.years} years (${x.fromYear}–${x.toYear})`, b: `${fmtPctPa(x.pctPerYear)} real` }))} />
      <Breakdown m={m} rows={s.byCountryMillions} format={(v) => fmtMoneyMillions(v, unitLabel)} label="By country" />
      <p className="text-[11px] leading-snug text-slate-500">
        Reference years: GDP {g.latest}; real growth compared with {g.compare.join(", ")}, at {g.real_base_year} prices and
        fixed {g.real_base_year} exchange rates, so currency movements do not affect growth.
        {g.compare.includes(2020) && " 2020 was the COVID-19 low point, which raises growth measured from 2020."}
      </p>
    </div>
  );
}

/** One-line summary for the collapsed mobile sheet. */
export function headline(m: Manifest, fx: FxTable, r: QueryResult | null, layer: LayerKey, measure: Measure,
                         currency: string): string | null {
  if (!r) return null;
  try {
    if (layer === "population") {
      return r.layers[`pop_${m.years.population.latest}`] ? `${fmtPeople(populationSummary(m, r).total)} people` : null;
    }
    if (!r.layers[`gdp_nom_eur_${m.years.gdp.latest}`] || !r.layers[`gdp_real_${m.years.gdp.latest}`]) return null;
    const cur = currencyOptions(fx, r.pointCountry).includes(currency) ? currency : "EUR";
    const meas = cur !== "EUR" ? "nominal" : measure;
    const s = gdpSummary(m, fx, r, meas, cur);
    return `GDP ${fmtMoneyMillions(s.totalMillions, meas === "pps" ? "PPS" : cur)}`;
  } catch {
    return null;
  }
}
