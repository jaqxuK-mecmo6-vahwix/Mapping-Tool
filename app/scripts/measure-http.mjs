// Real HTTP cost of queries with geotiff.js against a running server (e.g. the Vite dev server):
// counts requests and response bytes, cold (first query, incl. COG headers) and warm (next query
// nearby, as while dragging). Usage:
//   node scripts/measure-http.mjs [http://localhost:5173/data/] [blockBytes]
import { fromUrl } from "geotiff";
import proj4 from "proj4";
import geodesicPkg from "geographiclib-geodesic";

const { Geodesic } = geodesicPkg;
const BASE = process.argv[2] ?? "http://localhost:5173/data/";
const BLOCK = Number(process.argv[3] ?? 16384);
const MAX_CELLS = Number(process.argv[4] ?? 100000);
proj4.defs("EPSG:3035", "+proj=laea +lat_0=52 +lon_0=10 +x_0=4321000 +y_0=3210000 +ellps=GRS80 +units=m +no_defs");

let requests = 0, bytes = 0;
const realFetch = globalThis.fetch;
globalThis.fetch = async (...a) => {
  const r = await realFetch(...a);
  const buf = await r.arrayBuffer();
  requests++; bytes += buf.byteLength;
  return new Response(buf, { status: r.status, headers: r.headers });
};

const m = await (await realFetch(BASE + "manifest.json")).json();
const level = (r) => [...m.levels_km].sort((a, b) => a - b).find((lv) => (Math.PI * r * r) / (lv * lv) <= MAX_CELLS) ?? Math.max(...m.levels_km);
function windowFor(lat, lon, r, lv) {
  let x0 = Infinity, x1 = -Infinity, y0 = Infinity, y1 = -Infinity;
  for (let a = 0; a < 360; a += 5) {
    const p = Geodesic.WGS84.Direct(lat, lon, a, r * 1000);
    const [x, y] = proj4("EPSG:4326", "EPSG:3035", [p.lon2, p.lat2]);
    x0 = Math.min(x0, x); x1 = Math.max(x1, x); y0 = Math.min(y0, y); y1 = Math.max(y1, y);
  }
  const s = m.grid.cell_m * lv;
  return [Math.floor((x0 - m.grid.xmin) / s), Math.floor((m.grid.ymax - y1) / s), Math.ceil((x1 - m.grid.xmin) / s), Math.ceil((m.grid.ymax - y0) / s)];
}

const layers = Object.keys(m.layers);
async function query(tiffs, lat, lon, r) {
  const lv = level(r);
  const w = windowFor(lat, lon, r, lv);
  await Promise.all(layers.map(async (k) => {
    const f = m.layers[k].levels[String(lv)];
    const url = BASE + f.url;
    if (!tiffs.has(url)) tiffs.set(url, fromUrl(url, { cache: true, blockSize: BLOCK }));
    const img = await (await tiffs.get(url)).getImage(0);
    await img.readRasters({ window: w, samples: [f.band ?? 0], interleave: true });
  }));
  return lv;
}

console.log(`block ${BLOCK} B, budget ${MAX_CELLS} cells, ${layers.length} layers`);
console.log("place        r_km lv | cold: req   KiB | warm (+5 km east): req   KiB");
for (const [name, lat, lon] of [["London", 51.5074, -0.1278], ["Paris", 48.8566, 2.3522], ["Warsaw", 52.2297, 21.0122]]) {
  for (const r of [10, 25, 50, 100, 200, 500]) {
    const tiffs = new Map();
    requests = 0; bytes = 0;
    const lv = await query(tiffs, lat, lon, r);
    const cold = [requests, bytes];
    requests = 0; bytes = 0;
    await query(tiffs, lat, lon + 5 / (111 * Math.cos(lat * Math.PI / 180)), r);
    console.log(`${name.padEnd(10)} ${String(r).padStart(5)} ${String(lv).padStart(2)} | ${String(cold[0]).padStart(9)} ${(cold[1] / 1024).toFixed(0).padStart(5)} | ${String(requests).padStart(22)} ${(bytes / 1024).toFixed(0).padStart(5)}`);
  }
}
