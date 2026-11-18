// Check a deployed site (GitHub Pages or any host): pages load, the data manifest is valid, and the
// data files answer HTTP Range requests uncompressed (geotiff.js and PMTiles need byte ranges).
//   node scripts/check-deploy.mjs https://<user>.github.io/<repo>/
const base = new URL(process.argv[2] ?? "http://localhost:4173/radiusstats-europe/");
if (!base.pathname.endsWith("/")) base.pathname += "/";
let failed = 0;
const ok = (cond, label, detail = "") => {
  console.log(`${cond ? "PASS" : "FAIL"}  ${label}${detail ? `  (${detail})` : ""}`);
  if (!cond) failed++;
};

const page = await fetch(base);
ok(page.ok && (await page.text()).includes("RadiusStats"), "index.html", `${page.status} ${base}`);
for (const f of ["sw.js", "manifest.webmanifest", "icon.svg"]) {
  const r = await fetch(new URL(f, base));
  ok(r.ok, f, String(r.status));
}

const data = new URL("data/", base);
const mr = await fetch(new URL("manifest.json", data));
const m = mr.ok ? await mr.json() : null;
ok(m?.schema === 2 && m?.layers, "data/manifest.json", m ? `${m.countries.filter((c) => c.built).length} countries, built ${m.generated}` : String(mr.status));
if (m) {
  const files = [m.layers.country.levels["1"].url, m.layers.country.levels["32"].url, m.heat.population.url, m.heat.gdp.url];
  for (const f of files) {
    const r = await fetch(new URL(f, data), { headers: { Range: "bytes=100-1123" } });
    const body = new Uint8Array(await r.arrayBuffer());
    const enc = r.headers.get("content-encoding");
    ok(r.status === 206 && body.length === 1024 && !enc, `range request ${f}`,
       `${r.status}, ${body.length} B, ${r.headers.get("content-range") ?? "no content-range"}${enc ? `, encoding ${enc}` : ""}`);
  }
  const fx = await fetch(new URL(m.fx, data));
  ok(fx.ok, "data/fx.json", String(fx.status));
  const mask = await fetch(new URL(m.coverage_mask.url, data));
  ok(mask.ok, "data/" + m.coverage_mask.url, String(mask.status));
}
console.log(failed ? `\n${failed} check(s) failed` : "\nall checks passed");
console.log(`query cost on this host: node app/scripts/measure-http.mjs ${data}`);
process.exit(failed ? 1 : 0);
