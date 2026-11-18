import { useEffect, useRef, useState } from "react";
import { searchPlaces, type Place } from "../lib/nominatim";
import { RADIUS_MAX, RADIUS_MIN, clampRadius, type LayerKey } from "../lib/urlState";
import { Segmented } from "./ui";

interface Props {
  radiusKm: number;
  layer: LayerKey;
  showHeat: boolean;
  onRadius(r: number): void;
  onLayer(l: LayerKey): void;
  onHeat(v: boolean): void;
  onPlace(lat: number, lon: number): void;
  onCentre(): void;
}

export function SearchBox({ onPlace, id = "place-search" }: Pick<Props, "onPlace"> & { id?: string }) {
  const [q, setQ] = useState("");
  const [results, setResults] = useState<Place[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const ctl = useRef<AbortController | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    const text = q.trim();
    if (text.length < 2) return;
    ctl.current?.abort();
    ctl.current = new AbortController();
    setBusy(true);
    setError(null);
    try {
      const r = await searchPlaces(text, ctl.current.signal);
      setResults(r);
      if (r.length === 1) pick(r[0]);
    } catch (err) {
      if ((err as Error).name !== "AbortError") setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  function pick(p: Place) {
    onPlace(p.lat, p.lon);
    setResults(null);
    setQ(p.name.split(",")[0]);
  }

  return (
    <div className="relative">
      <form role="search" onSubmit={submit} className="flex gap-1.5">
        <label htmlFor={id} className="sr-only">Search for a place</label>
        <input id={id} type="search" value={q} onChange={(e) => setQ(e.target.value)}
          placeholder="Search a place…" autoComplete="off" enterKeyHint="search"
          className="min-w-0 flex-1 rounded-lg border-0 bg-white px-3 py-2 text-sm text-slate-900 shadow-sm ring-1 ring-slate-300 placeholder:text-slate-400 focus:ring-2 focus:ring-orange-500 focus:outline-none" />
        <button type="submit" disabled={busy}
          className="rounded-lg bg-slate-800 px-3 py-2 text-sm font-medium text-white shadow-sm hover:bg-slate-700 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-orange-500 disabled:opacity-60">
          {busy ? "…" : "Search"}
        </button>
      </form>
      {error && <p className="mt-1 text-xs text-red-700" role="alert">{error}</p>}
      {results && (
        <div className="absolute inset-x-0 top-full z-20 mt-1 overflow-hidden rounded-lg bg-white shadow-lg ring-1 ring-slate-200">
          {results.length === 0 ? (
            <p className="px-3 py-2 text-sm text-slate-600" role="status">No places found in the covered countries.</p>
          ) : (
            <ul aria-label="Search results" className="max-h-64 overflow-auto">
              {results.map((p) => (
                <li key={`${p.lat},${p.lon}`}>
                  <button type="button" onClick={() => pick(p)}
                    className="block w-full px-3 py-2 text-left text-sm text-slate-800 hover:bg-slate-50 focus-visible:bg-orange-50 focus-visible:outline-none">
                    {p.name}
                  </button>
                </li>
              ))}
            </ul>
          )}
          <p className="border-t border-slate-100 px-3 py-1 text-[10px] text-slate-500">
            Search by <a className="underline" href="https://nominatim.openstreetmap.org/" target="_blank" rel="noreferrer">Nominatim</a>,
            data © <a className="underline" href="https://www.openstreetmap.org/copyright" target="_blank" rel="noreferrer">OpenStreetMap contributors</a>
          </p>
        </div>
      )}
    </div>
  );
}

export function RadiusControl({ radiusKm, onRadius }: Pick<Props, "radiusKm" | "onRadius">) {
  const [text, setText] = useState(String(radiusKm));
  useEffect(() => setText(String(radiusKm)), [radiusKm]);
  // slider is linear in sqrt(r) so small radii stay controllable on a phone
  const toSlider = (r: number) => Math.round(Math.sqrt(r) * 100);
  const fromSlider = (v: number) => {
    const r = (v / 100) ** 2;
    return r < 10 ? Math.round(r * 2) / 2 : r < 100 ? Math.round(r) : Math.round(r / 5) * 5;
  };
  const commit = () => {
    const r = clampRadius(Number(text.replace(",", ".")));
    setText(String(r));
    onRadius(r);
  };
  return (
    <div className="flex items-center gap-2">
      <label htmlFor="radius-slider" className="shrink-0 text-xs font-medium text-slate-600">Radius</label>
      <input id="radius-slider" type="range" min={toSlider(RADIUS_MIN)} max={toSlider(RADIUS_MAX)} step={1}
        value={toSlider(radiusKm)} onChange={(e) => onRadius(clampRadius(fromSlider(Number(e.target.value))))}
        aria-valuetext={`${radiusKm} kilometres`} className="min-w-0 flex-1 accent-orange-600" />
      <div className="flex shrink-0 items-center rounded-md bg-white ring-1 ring-slate-300 focus-within:ring-2 focus-within:ring-orange-500">
        <label htmlFor="radius-input" className="sr-only">Radius in kilometres</label>
        <input id="radius-input" inputMode="decimal" value={text} onChange={(e) => setText(e.target.value)}
          onBlur={commit} onKeyDown={(e) => e.key === "Enter" && commit()}
          className="w-14 rounded-md border-0 bg-transparent px-2 py-1 text-right text-sm tabular-nums focus:outline-none" />
        <span className="pr-2 text-xs text-slate-500" aria-hidden="true">km</span>
      </div>
    </div>
  );
}

export function LayerControl({ layer, showHeat, onLayer, onHeat, onCentre }: Pick<Props, "layer" | "showHeat" | "onLayer" | "onHeat" | "onCentre">) {
  return (
    <div className="flex flex-wrap items-center gap-2">
      <div className="min-w-44 flex-1">
        <Segmented label="Layer" value={layer} onChange={onLayer}
          options={[{ value: "population", label: "Population" }, { value: "gdp", label: "GDP" }]} />
      </div>
      <label className="flex items-center gap-1.5 text-xs text-slate-700">
        <input type="checkbox" aria-label="Show heat map" checked={showHeat} onChange={(e) => onHeat(e.target.checked)} className="accent-orange-600" />
        Heat map
      </label>
      <button type="button" onClick={onCentre}
        className="rounded-md px-2 py-1 text-xs text-slate-700 ring-1 ring-slate-300 hover:bg-slate-50 focus-visible:outline-2 focus-visible:outline-orange-500">
        Point at map centre
      </button>
    </div>
  );
}
