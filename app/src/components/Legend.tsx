import type { HeatMeta } from "../engine/types";

const fmt = (v: number) =>
  v >= 1000 ? `${Math.round(v / 100) / 10}k` : v >= 10 ? String(Math.round(v)) : v >= 1 ? v.toFixed(1) : v.toPrecision(1);

export default function Legend({ heat, label }: { heat: HeatMeta; label: string }) {
  const stops = heat.ramp.map(([r, g, b], i) => `rgb(${r} ${g} ${b}) ${(i / (heat.ramp.length - 1)) * 100}%`).join(", ");
  return (
    <figure className="rounded-lg bg-white px-2.5 py-1.5 text-[10px] text-slate-700 shadow ring-1 ring-slate-200">
      <figcaption className="mb-1 font-medium">{label} <span className="font-normal text-slate-500">({heat.unit}, log scale)</span></figcaption>
      <div className="h-2 w-44 rounded-sm" style={{ background: `linear-gradient(to right, ${stops})` }} aria-hidden="true" />
      <div className="flex w-44 justify-between tabular-nums" aria-hidden="true"><span>≤{fmt(heat.min)}</span><span>≥{fmt(heat.max)}</span></div>
      <p className="sr-only">Colour scale from {fmt(heat.min)} to {fmt(heat.max)} {heat.unit}.</p>
    </figure>
  );
}
