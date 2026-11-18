import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Engine } from "./engine/client";
import { currencyOptions } from "./engine/stats";
import type { FxTable, Manifest, QueryResult } from "./engine/types";
import { LayerControl, RadiusControl, SearchBox } from "./components/Controls";
import Legend from "./components/Legend";
import MapView from "./components/MapView";
import ResultsPanel, { headline } from "./components/ResultsPanel";
import SourcesDialog from "./components/SourcesDialog";
import { parseHash, toHash, type AppState } from "./lib/urlState";

/** Data folder, absolute (the worker resolves URLs against its own script location, not the page):
 *  `data/` next to index.html unless VITE_DATA_URL points elsewhere (e.g. another host with CORS). */
const DATA_URL: string = new URL(import.meta.env.VITE_DATA_URL ?? "data/", document.baseURI).toString();
const QUERY_DEBOUNCE_MS = 120;

export default function App() {
  const [state, setState] = useState<AppState>(() => parseHash(window.location.hash));
  const [boot, setBoot] = useState<{ manifest: Manifest; fx: FxTable } | null>(null);
  const [bootError, setBootError] = useState<string | null>(null);
  const [result, setResult] = useState<QueryResult | null>(null);
  const [partial, setPartial] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showHeat, setShowHeat] = useState(true);
  const [sourcesOpen, setSourcesOpen] = useState(false);
  const [sheetOpen, setSheetOpen] = useState(() => window.matchMedia("(min-width: 768px)").matches);
  const engine = useRef<Engine | null>(null);
  const centre = useRef<() => void>(() => {});

  // --- engine --------------------------------------------------------------------------------------
  useEffect(() => {
    const e = new Engine(DATA_URL, {
      onResult(r, isPartial) {
        setResult(r);
        setPartial(isPartial);
        setLoading(false);
        setError(null);
      },
      onError(msg) {
        setError(msg);
        setLoading(false);
      },
    });
    engine.current = e;
    e.ready.then(setBoot, (err: Error) => setBootError(err.message));
    return () => e.dispose();
  }, []);

  const hasPoint = state.lat !== undefined && state.lon !== undefined;

  useEffect(() => {
    if (!boot || !hasPoint) return;
    setLoading(true);
    const t = setTimeout(() => engine.current?.query(state.lat!, state.lon!, state.radiusKm, state.layer), QUERY_DEBOUNCE_MS);
    return () => clearTimeout(t);
    // the layer only changes read priority; switching layers must not re-run the query
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [boot, state.lat, state.lon, state.radiusKm]);

  // --- URL state -----------------------------------------------------------------------------------
  useEffect(() => {
    const h = toHash(state);
    if (h !== window.location.hash) history.replaceState(null, "", h);
  }, [state]);
  useEffect(() => {
    const onHash = () => setState(parseHash(window.location.hash));
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);

  // reset the currency when the point moves to a country where it is not offered
  useEffect(() => {
    if (!boot || !result || partial) return;
    // only judge a result for the current point (a stale one would reset a shared link's currency)
    if (result.params.lat !== state.lat || result.params.lon !== state.lon) return;
    if (!currencyOptions(boot.fx, result.pointCountry).includes(state.currency)) {
      setState((s) => ({ ...s, currency: "EUR" }));
    }
  }, [boot, result, partial, state.currency, state.lat, state.lon]);

  const pick = useCallback((lat: number, lon: number) => setState((s) => ({ ...s, lat, lon })), []);
  const point = useMemo(() => (hasPoint ? { lat: state.lat!, lon: state.lon! } : undefined), [hasPoint, state.lat, state.lon]);

  if (bootError) {
    return <main className="p-6 text-sm text-red-800" role="alert">Could not load the data manifest: {bootError}</main>;
  }

  const heat = boot?.manifest.heat?.[state.layer];
  const controls = (
    <div className="space-y-2.5">
      <RadiusControl radiusKm={state.radiusKm} onRadius={(r) => setState((s) => ({ ...s, radiusKm: r }))} />
      <LayerControl layer={state.layer} showHeat={showHeat}
        onLayer={(layer) => setState((s) => ({ ...s, layer }))} onHeat={setShowHeat} onCentre={() => centre.current()} />
    </div>
  );

  return (
    <main className="relative h-dvh w-full overflow-hidden">
      <h1 className="sr-only">RadiusStats Europe: population and GDP within a radius</h1>
      {/* mobile: search bar on top */}
      <div className="absolute inset-x-2 top-2 z-10 md:hidden">
        <SearchBox id="place-search-mobile" onPlace={pick} />
      </div>

      {heat && showHeat && (
        <div className="absolute top-14 right-2 z-10 md:top-3 md:right-3">
          <Legend heat={heat} label={state.layer === "population" ? "Population density" : "GDP density"} />
        </div>
      )}

      {/* results: bottom sheet on mobile, side panel on desktop */}
      <section aria-label="Results"
        className={`absolute inset-x-0 bottom-0 z-10 flex flex-col rounded-t-2xl bg-white shadow-[0_-4px_24px_rgb(0_0_0/0.15)]
          md:inset-x-auto md:top-3 md:bottom-3 md:left-3 md:w-[25rem] md:rounded-2xl md:shadow-xl
          ${sheetOpen ? "max-h-[72dvh]" : "max-h-[10.5rem]"} md:max-h-none`}>
        <button type="button" onClick={() => setSheetOpen((v) => !v)} aria-expanded={sheetOpen}
          aria-label={sheetOpen ? "Collapse results" : "Expand results"}
          className="mx-auto flex w-full flex-col items-center pt-1.5 pb-1 md:hidden">
          <span className="h-1.5 w-10 rounded-full bg-slate-300" aria-hidden="true" />
        </button>
        <header className="flex items-center justify-between px-4 pt-1 md:pt-4">
          {!sheetOpen && boot && hasPoint && headline(boot.manifest, boot.fx, result, state.layer, state.measure, state.currency) ? (
            <p className="text-sm font-semibold text-slate-900 tabular-nums md:hidden" aria-hidden="true">
              {headline(boot.manifest, boot.fx, result, state.layer, state.measure, state.currency)}
              <span className="font-normal text-slate-500"> within {state.radiusKm} km</span>
            </p>
          ) : null}
          <p className={`text-sm font-semibold text-slate-900 ${!sheetOpen && hasPoint && result ? "hidden md:block" : ""}`}>
            RadiusStats <span className="font-normal text-slate-500">Europe</span>
          </p>
          <button type="button" onClick={() => setSourcesOpen(true)}
            className="rounded-md px-2 py-1 text-xs text-slate-600 underline-offset-2 hover:underline focus-visible:outline-2 focus-visible:outline-orange-500">
            Sources &amp; licences
          </button>
        </header>
        <div className="hidden px-4 pt-3 md:block"><SearchBox onPlace={pick} /></div>
        <div className="px-4 pt-2.5 pb-3">{controls}</div>
        <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain border-t border-slate-100 px-4 pt-3 pb-[max(1rem,env(safe-area-inset-bottom))]">
          {boot ? (
            <ResultsPanel manifest={boot.manifest} fx={boot.fx} result={result} partial={partial} loading={loading}
              error={error} layer={state.layer} measure={state.measure} currency={state.currency} hasPoint={hasPoint}
              onMeasure={(measure) => setState((s) => ({ ...s, measure }))}
              onCurrency={(currency) => setState((s) => ({ ...s, currency, measure: currency === "EUR" ? s.measure : "nominal" }))} />
          ) : (
            <p className="text-sm text-slate-600" role="status">Loading data…</p>
          )}
        </div>
      </section>

      {/* the map comes last in the DOM so keyboard focus reaches search and controls first;
          it is drawn underneath them (z-0) */}
      {boot && (
        <MapView manifest={boot.manifest} dataUrl={DATA_URL} point={point} radiusKm={state.radiusKm}
          layer={state.layer} showHeat={showHeat} onPick={pick} centreRef={centre} />
      )}

      {boot && <SourcesDialog open={sourcesOpen} onClose={() => setSourcesOpen(false)} manifest={boot.manifest} />}
    </main>
  );
}
