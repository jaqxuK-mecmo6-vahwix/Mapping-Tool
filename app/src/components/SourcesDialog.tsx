import { useEffect, useRef } from "react";
import type { Manifest } from "../engine/types";

const A = ({ href, children }: { href: string; children: React.ReactNode }) => (
  <a href={href} target="_blank" rel="noreferrer" className="text-orange-700 underline">{children}</a>
);

export default function SourcesDialog({ open, onClose, manifest }: { open: boolean; onClose(): void; manifest: Manifest }) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const d = ref.current;
    if (!d) return;
    if (open && !d.open) d.showModal();
    if (!open && d.open) d.close();
  }, [open]);
  const built = manifest.countries.filter((c) => c.built).map((c) => c.name);
  const has = (code: string) => manifest.countries.some((c) => c.code === code && c.built);
  const y = manifest.years;

  return (
    <dialog ref={ref} onClose={onClose} aria-labelledby="sources-title"
      className="m-auto max-h-[85dvh] w-[min(42rem,calc(100vw-2rem))] rounded-xl p-0 shadow-2xl backdrop:bg-slate-900/40">
      <div className="sticky top-0 flex items-center justify-between border-b border-slate-200 bg-white px-5 py-3">
        <h2 id="sources-title" className="text-base font-semibold text-slate-900">Sources, methods and licences</h2>
        <button type="button" onClick={onClose} autoFocus
          className="rounded-md px-2 py-1 text-sm text-slate-600 ring-1 ring-slate-300 hover:bg-slate-50 focus-visible:outline-2 focus-visible:outline-orange-500">
          Close
        </button>
      </div>
      <div className="space-y-4 px-5 py-4 text-sm leading-relaxed text-slate-700">
        <section>
          <h3 className="font-semibold text-slate-900">Coverage of this build</h3>
          <p>{built.join(", ")}. Data built {new Date(manifest.generated).toLocaleDateString("en-GB")}.
            Population: 1 January {y.population.latest} (compared with {y.population.compare.join(", ")}).
            GDP: {y.gdp.latest} (real growth compared with {y.gdp.compare.join(", ")}).</p>
        </section>
        <section>
          <h3 className="font-semibold text-slate-900">Data</h3>
          <ul className="list-disc space-y-1 pl-5">
            <li>Population grid: Eurostat, <A href="https://ec.europa.eu/eurostat/web/gisco/geodata/population-distribution/population-grids">Census 2021 population grid</A> (V3), 1 km. © European Union. CC BY 4.0.</li>
            <li>Grid cells with NUTS codes and land share: Eurostat GISCO <A href="https://ec.europa.eu/eurostat/web/gisco/geodata/grids">1 km grid</A>. © European Union; administrative boundaries © EuroGeographics.</li>
            <li>Regional population: Eurostat <A href="https://ec.europa.eu/eurostat/databrowser/view/demo_r_pjanaggr3/default/table">demo_r_pjanaggr3</A>.</li>
            <li>Regional GDP: Eurostat <A href="https://ec.europa.eu/eurostat/databrowser/view/nama_10r_3gdp/default/table">nama_10r_3gdp</A> (current prices, EUR and PPS) and <A href="https://ec.europa.eu/eurostat/databrowser/view/nama_10r_2gvagr/default/table">nama_10r_2gvagr</A> (volume).</li>
            {has("UK") && <>
              <li>United Kingdom (no Eurostat data after 2019): population grid from <A href="https://hub.worldpop.org/geodata/listing?id=136">WorldPop</A> 2021
                constrained 100 m counts (R2025A, alpha), CC BY 4.0, WorldPop, University of Southampton; local authority boundaries (May 2023),
                population (<A href="https://www.ons.gov.uk/peoplepopulationandcommunity/populationandmigration/populationestimates/datasets/populationestimatesforukenglandandwalesscotlandandnorthernireland">mid-year estimates</A>)
                and <A href="https://www.ons.gov.uk/economy/grossdomesticproductgdp/datasets/regionalgrossdomesticproductlocalauthorities">GDP by local authority</A>:
                Office for National Statistics, Open Government Licence v3.0. Contains OS data © Crown copyright and database right.</li>
            </>}
            {has("CH") && <li>Switzerland GDP: Federal Statistical Office (BFS), <A href="https://www.bfs.admin.ch/asset/de/36251918">GDP by canton</A> 2011–2024. Source: BFS.</li>}
            {has("NO") && <li>Norway GDP: Statistics Norway (SSB), <A href="https://www.ssb.no/en/statbank/table/09391">StatBank table 09391</A>, CC BY 4.0.</li>}
            <li>Purchasing power parities: Eurostat <A href="https://ec.europa.eu/eurostat/databrowser/view/prc_ppp_ind/default/table">prc_ppp_ind</A> (PPS for the UK, Switzerland and Norway).</li>
            <li>Exchange rates: Eurostat/ECB <A href="https://ec.europa.eu/eurostat/databrowser/view/ert_bil_eur_a/default/table">ert_bil_eur_a</A>, annual averages.</li>
            <li>Country outlines for the coverage mask: Eurostat GISCO countries 2024. © EuroGeographics.</li>
            <li>Base map: <A href="https://openfreemap.org">OpenFreeMap</A>, © <A href="https://openmaptiles.org">OpenMapTiles</A>, data © <A href="https://www.openstreetmap.org/copyright">OpenStreetMap contributors</A> (ODbL).</li>
            <li>Place search: <A href="https://nominatim.org">Nominatim</A>, © OpenStreetMap contributors.</li>
          </ul>
        </section>
        <section>
          <h3 className="font-semibold text-slate-900">Method (modified data)</h3>
          <ul className="list-disc space-y-1 pl-5">
            <li>Census 2021 cell populations are rescaled within each NUTS 3 region so they add up to that year's Eurostat total.
              {has("UK") && " In the UK, WorldPop 2021 cells are rescaled within each local authority to the ONS estimate; population on 1 January is the mean of the two mid-year (30 June) estimates around it."}</li>
            <li>Regional GDP is allocated to cells in proportion to the same year's cell population. At small radii this
              puts GDP where people live rather than where they work.</li>
            <li>Real growth: regional constant-price GDP at {y.gdp.real_base_year} prices, converted to EUR at fixed {y.gdp.real_base_year} rates.
              While the ARDECO service is unavailable, NUTS 3 GDP is deflated with its NUTS 2 region's GDP deflator, and each
              country's regional total is benchmarked to the latest national chain-linked volumes (Eurostat nama_10_gdp).
              {(has("UK") || has("CH") || has("NO")) && " UK, Swiss and Norwegian regions use the volume series of ONS, BFS and SSB. Norwegian county value added is scaled to Eurostat's mainland GDP (excluding offshore oil and gas)."}</li>
            <li>Circle sums use the geodesic circle on the WGS84 ellipsoid; edge cells count by the share of the cell inside
              (4×4 sub-sampling). Large circles use coarser 2–32 km cells whose values are exact sums of the 1 km cells.</li>
            <li>Growth: % p.a. is the compound annual growth rate (end/start)<sup>1/n</sup> − 1; absolute change per year is (end − start)/n.</li>
            <li>PPS: Eurostat converts regional GDP to PPS with one national factor, so a circle's PPS is the sum of each
              country's EUR part times that country's factor.</li>
            <li>Regional GDP that cannot be located (extra-regio, e.g. embassies and offshore activity) is not included.</li>
          </ul>
        </section>
        <section>
          <h3 className="font-semibold text-slate-900">Use</h3>
          <p>Non-commercial project. Figures are estimates derived from official statistics and are not official statistics.</p>
        </section>
      </div>
    </dialog>
  );
}
