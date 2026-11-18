// Estimates how many bytes a query downloads, from the COG tile index of a build:
// for each test circle and cell budget, the pyramid level the engine would choose, the window it
// reads and the compressed tiles that window touches (all layers, and the first "visible" group).
// Range requests are rounded up to the 16 KiB blocks geotiff.js fetches. Usage:
//   node scripts/measure-bytes.mjs [../data/build] [budget1,budget2,...]
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { fromFile } from "geotiff";
import proj4 from "proj4";
import geodesicPkg from "geographiclib-geodesic";

const { Geodesic } = geodesicPkg;
const BUILD = process.argv[2] ?? fileURLToPath(new URL("../../data/build/", import.meta.url));
const BUDGETS = (process.argv[3] ?? "25000,50000,100000,250000").split(",").map(Number);
const BLOCK = 16 * 1024;   // = BLOCK_BYTES in src/engine/source.ts
proj4.defs("EPSG:3035", "+proj=laea +lat_0=52 +lon_0=10 +x_0=4321000 +y_0=3210000 +ellps=GRS80 +units=m +no_defs");
const m = JSON.parse(readFileSync(BUILD + "/manifest.json", "utf8"));

const PLACES = { Paris: [48.8566, 2.3522], London: [51.5074, -0.1278], Warsaw: [52.2297, 21.0122], Oslo: [59.9139, 10.7522] };
const RADII = [10, 25, 50, 100, 200, 350, 500];

function level(r, budget) {
  for (const lv of [...m.levels_km].sort((a, b) => a - b)) if ((Math.PI * r * r) / (lv * lv) <= budget) return lv;
  return Math.max(...m.levels_km);
}
function windowFor(lat, lon, r, lv) {
  const g = Geodesic.WGS84;
  let x0 = Infinity, x1 = -Infinity, y0 = Infinity, y1 = -Infinity;
  for (let a = 0; a < 360; a += 5) {
    const p = g.Direct(lat, lon, a, r * 1000);
    const [x, y] = proj4("EPSG:4326", "EPSG:3035", [p.lon2, p.lat2]);
    x0 = Math.min(x0, x); x1 = Math.max(x1, x); y0 = Math.min(y0, y); y1 = Math.max(y1, y);
  }
  const size = m.grid.cell_m * lv;
  return { c0: Math.floor((x0 - m.grid.xmin) / size) - 1, c1: Math.ceil((x1 - m.grid.xmin) / size) + 1,
           r0: Math.floor((m.grid.ymax - y1) / size) - 1, r1: Math.ceil((m.grid.ymax - y0) / size) + 1 };
}

const tiffCache = new Map();
async function tileIndex(url) {
  if (!tiffCache.has(url)) {
    const t = await fromFile(BUILD + "/" + url);
    const img = await t.getImage(0);
    const fd = img.fileDirectory;
    tiffCache.set(url, { tw: img.getTileWidth(), th: img.getTileHeight(), across: Math.ceil(img.getWidth() / img.getTileWidth()),
      down: Math.ceil(img.getHeight() / img.getTileHeight()), off: fd.TileOffsets, cnt: fd.TileByteCounts });
  }
  return tiffCache.get(url);
}
async function bytesFor(url, w) {
  const t = await tileIndex(url);
  const blocks = new Set();
  let raw = 0;
  for (let ty = Math.max(0, Math.floor(w.r0 / t.th)); ty <= Math.min(t.down - 1, Math.floor(w.r1 / t.th)); ty++) {
    for (let tx = Math.max(0, Math.floor(w.c0 / t.tw)); tx <= Math.min(t.across - 1, Math.floor(w.c1 / t.tw)); tx++) {
      const i = ty * t.across + tx;
      const o = Number(t.off[i]), n = Number(t.cnt[i]);
      raw += n;
      for (let b = Math.floor(o / BLOCK); b <= Math.floor((o + Math.max(n, 1) - 1) / BLOCK); b++) blocks.add(b);
    }
  }
  return { raw, fetched: blocks.size * BLOCK };
}

const all = Object.keys(m.layers);
const popGroup = [...all.filter((k) => m.layers[k].kind === "population"), "country", "land_covered"];
const kb = (b) => (b / 1024).toFixed(0).padStart(6);
console.log(`build ${BUILD}; levels ${m.levels_km}; ${all.length} layers`);
for (const budget of BUDGETS) {
  console.log(`\n== budget ${budget} cells`);
  console.log("place      r_km  lv  cells   first-group KiB (fetched)   all layers KiB (fetched)");
  let worst = 0;
  for (const [name, [lat, lon]] of Object.entries(PLACES)) {
    for (const r of RADII) {
      const lv = level(r, budget);
      const w = windowFor(lat, lon, r, lv);
      // layers may share one multi-band file per level: count each file once
      let a = { raw: 0, fetched: 0 }, f = { raw: 0, fetched: 0 };
      const urlsAll = new Set(all.map((k) => m.layers[k].levels[String(lv)].url));
      const urlsFirst = new Set(popGroup.map((k) => m.layers[k].levels[String(lv)].url));
      for (const u of urlsAll) {
        const b = await bytesFor(u, w);
        a.raw += b.raw; a.fetched += b.fetched;
        if (urlsFirst.has(u)) { f.raw += b.raw; f.fetched += b.fetched; }
      }
      worst = Math.max(worst, a.fetched);
      const cells = Math.round((Math.PI * r * r) / (lv * lv));
      console.log(`${name.padEnd(9)} ${String(r).padStart(5)} ${String(lv).padStart(3)} ${String(cells).padStart(6)}   ${kb(f.raw)} (${kb(f.fetched)})            ${kb(a.raw)} (${kb(a.fetched)})`);
    }
  }
  console.log(`worst case all layers: ${(worst / 1048576).toFixed(2)} MiB`);
}
