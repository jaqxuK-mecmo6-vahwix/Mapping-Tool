import { useEffect, useRef, useState } from "react";
import maplibregl, { type GeoJSONSource, type Map as MlMap } from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { Protocol } from "pmtiles";
import type { FeatureCollection } from "geojson";
import { geodesicCircle } from "../engine/geometry";
import type { Manifest } from "../engine/types";
import type { LayerKey } from "../lib/urlState";

const STYLE = "https://tiles.openfreemap.org/styles/positron";
/** Panning is restricted to the coverage area (Azores/Canaries to Cyprus, Crete to North Cape). */
const MAX_BOUNDS: [[number, number], [number, number]] = [[-35, 24], [48, 73]];
const EUROPE: [[number, number], [number, number]] = [[-11, 35], [32, 71]];

let protocolAdded = false;

interface Props {
  manifest: Manifest;
  dataUrl: string;
  point?: { lat: number; lon: number };
  radiusKm: number;
  layer: LayerKey;
  showHeat: boolean;
  onPick(lat: number, lon: number): void;
  /** filled with a function that places the point at the map centre (keyboard / button access) */
  centreRef?: React.MutableRefObject<() => void>;
}

function circleGeoJSON(point: Props["point"], r: number): FeatureCollection {
  if (!point) return { type: "FeatureCollection", features: [] };
  const ring = geodesicCircle(point.lat, point.lon, r, 128);
  ring.push(ring[0]);
  return { type: "FeatureCollection", features: [{ type: "Feature", properties: {}, geometry: { type: "Polygon", coordinates: [ring] } }] };
}

export default function MapView({ manifest, dataUrl, point, radiusKm, layer, showHeat, onPick, centreRef }: Props) {
  const el = useRef<HTMLDivElement>(null);
  const map = useRef<MlMap | null>(null);
  const marker = useRef<maplibregl.Marker | null>(null);
  const ready = useRef(false);
  const applyLayer = useRef<() => void>(() => {});
  /** bumps when a (new) map instance has finished loading, so marker/circle effects re-run */
  const [epoch, setEpoch] = useState(0);
  const latest = useRef({ point, radiusKm, layer, showHeat, onPick });
  latest.current = { point, radiusKm, layer, showHeat, onPick };

  // --- create the map once ------------------------------------------------------------------------
  useEffect(() => {
    if (!el.current) return;
    if (!protocolAdded) {
      maplibregl.addProtocol("pmtiles", new Protocol().tile);
      protocolAdded = true;
    }
    const m = new maplibregl.Map({
      container: el.current,
      style: STYLE,
      bounds: point ? undefined : EUROPE,
      center: point ? [point.lon, point.lat] : undefined,
      zoom: point ? 8 : undefined,
      maxBounds: MAX_BOUNDS,
      minZoom: 2.5,
      maxZoom: 14,
      attributionControl: { compact: true },
      dragRotate: false,
      pitchWithRotate: false,
      touchPitch: false,
    });
    m.touchZoomRotate.disableRotation();
    m.addControl(new maplibregl.NavigationControl({ showCompass: false }), "bottom-right");
    m.getCanvas().setAttribute("aria-label", "Map. Click or tap to place the point. With the map focused, press Enter to place it at the map centre.");
    map.current = m;
    if (import.meta.env.DEV) (window as unknown as { __rsMap: MlMap }).__rsMap = m;

    m.on("load", () => {
      const abs = (u: string) => new URL(u, new URL(dataUrl, window.location.href)).toString();
      const firstSymbol = m.getStyle().layers.find((l) => l.type === "symbol")?.id;

      for (const key of ["population", "gdp"] as const) {
        const h = manifest.heat?.[key];
        if (!h) continue;
        m.addSource(`heat-${key}`, {
          type: "raster", url: `pmtiles://${abs(h.url)}`, tileSize: 256,
          attribution: "Heat map: RadiusStats Europe from Eurostat/GISCO data",
        });
        m.addLayer({
          id: `heat-${key}`, type: "raster", source: `heat-${key}`,
          paint: { "raster-opacity": 0.6, "raster-resampling": "nearest", "raster-fade-duration": 0 },
          layout: { visibility: "none" },
        }, firstSymbol);
      }

      m.addSource("coverage-mask", { type: "geojson", data: abs(manifest.coverage_mask?.url ?? "coverage_mask.geojson") });
      m.addLayer({ id: "coverage-mask", type: "fill", source: "coverage-mask",
        paint: { "fill-color": "#64748b", "fill-opacity": 0.45 } }, firstSymbol);

      m.addSource("circle", { type: "geojson", data: circleGeoJSON(latest.current.point, latest.current.radiusKm) });
      m.addLayer({ id: "circle-fill", type: "fill", source: "circle", paint: { "fill-color": "#f97316", "fill-opacity": 0.08 } });
      m.addLayer({ id: "circle-line", type: "line", source: "circle", paint: { "line-color": "#c2410c", "line-width": 2 } });
      ready.current = true;
      applyLayer.current();
      setEpoch((e) => e + 1);
    });

    // keep the point clear of the desktop side panel (≥ md: panel is 25rem + margins on the left)
    const mq = window.matchMedia("(min-width: 768px)");
    const pad = () => m.setPadding({ left: mq.matches ? 424 : 0, top: 0, right: 0, bottom: mq.matches ? 0 : 170 });
    pad();
    mq.addEventListener("change", pad);

    m.on("click", (e) => latest.current.onPick(e.lngLat.lat, e.lngLat.lng));
    const container = m.getCanvasContainer();
    const placeAtCentre = () => {
      const c = m.getCenter();
      latest.current.onPick(c.lat, c.lng);
    };
    if (centreRef) centreRef.current = placeAtCentre;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Enter") placeAtCentre();
    };
    container.addEventListener("keydown", onKey);

    applyLayer.current = () => {
      if (!ready.current) return;
      for (const key of ["population", "gdp"]) {
        if (m.getLayer(`heat-${key}`)) {
          m.setLayoutProperty(`heat-${key}`, "visibility",
            latest.current.showHeat && latest.current.layer === key ? "visible" : "none");
        }
      }
    };

    return () => {
      container.removeEventListener("keydown", onKey);
      mq.removeEventListener("change", pad);
      marker.current?.remove();
      marker.current = null;
      m.remove();
      map.current = null;
      ready.current = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [manifest, dataUrl]);

  // --- point marker + circle ---------------------------------------------------------------------
  useEffect(() => {
    const m = map.current;
    if (!m) return;
    if (point) {
      if (!marker.current) {
        const dot = document.createElement("div");
        dot.className = "rs-marker";
        dot.setAttribute("aria-hidden", "true");
        marker.current = new maplibregl.Marker({ element: dot, draggable: true })
          .setLngLat([point.lon, point.lat]).addTo(m);
        marker.current.on("drag", () => {
          const p = marker.current!.getLngLat();
          (m.getSource("circle") as GeoJSONSource | undefined)?.setData(circleGeoJSON({ lat: p.lat, lon: p.lng }, latest.current.radiusKm));
        });
        marker.current.on("dragend", () => {
          const p = marker.current!.getLngLat();
          latest.current.onPick(p.lat, p.lng);
        });
      } else {
        marker.current.setLngLat([point.lon, point.lat]);
      }
    } else if (marker.current) {
      marker.current.remove();
      marker.current = null;
    }
    const setData = () => (m.getSource("circle") as GeoJSONSource | undefined)?.setData(circleGeoJSON(point, radiusKm));
    if (ready.current) setData();
  }, [point?.lat, point?.lon, radiusKm, epoch]); // eslint-disable-line react-hooks/exhaustive-deps

  // --- heat layer visibility ---------------------------------------------------------------------
  useEffect(() => {
    applyLayer.current();
  }, [layer, showHeat]);

  // --- fly to a searched place (point changes far outside the view) ----------------------------
  useEffect(() => {
    const m = map.current;
    if (!m || !point) return;
    const b = m.getBounds();
    if (!b.contains([point.lon, point.lat])) m.easeTo({ center: [point.lon, point.lat], zoom: Math.max(m.getZoom(), 8) });
  }, [point?.lat, point?.lon]); // eslint-disable-line react-hooks/exhaustive-deps

  // maplibre sets `position: relative` on its container, so the sizing lives on a wrapper
  return (
    <div className="absolute inset-0">
      <div ref={el} className="h-full w-full" role="application" aria-label="Map of Europe" />
    </div>
  );
}
