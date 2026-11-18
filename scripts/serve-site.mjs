// Serve the assembled site/ folder like GitHub Pages serves a project site: under a subfolder, with
// HTTP Range requests. Node built-ins only.
//   node scripts/serve-site.mjs [prefix] [port]   (defaults: /radiusstats-europe/ and 4173)
import { createReadStream, existsSync, statSync } from "node:fs";
import { createServer } from "node:http";
import { extname, join, normalize, sep } from "node:path";
import { fileURLToPath } from "node:url";

const SITE = fileURLToPath(new URL("../site", import.meta.url));
const PREFIX = (process.argv[2] ?? "/radiusstats-europe/").replace(/\/?$/, "/");
const PORT = Number(process.argv[3] ?? 4173);
const TYPES = {
  ".html": "text/html; charset=utf-8", ".js": "text/javascript", ".css": "text/css", ".json": "application/json",
  ".webmanifest": "application/manifest+json", ".svg": "image/svg+xml", ".png": "image/png",
  ".geojson": "application/geo+json", ".tif": "image/tiff", ".pmtiles": "application/octet-stream",
};

if (!existsSync(SITE)) {
  console.error("no site/ folder: run scripts/deploy-gh-pages.sh --dry-run first");
  process.exit(1);
}

createServer((req, res) => {
  const path = decodeURIComponent((req.url ?? "/").split("?")[0]);
  if (path === PREFIX.slice(0, -1)) { res.writeHead(301, { Location: PREFIX }).end(); return; }  // like Pages
  if (!path.startsWith(PREFIX)) { res.writeHead(404).end("not found"); return; }
  let file = join(SITE, normalize(path.slice(PREFIX.length)).replace(/^([/\\])+/, ""));
  if (file !== SITE && !file.startsWith(SITE + sep)) { res.writeHead(403).end(); return; }
  if (existsSync(file) && statSync(file).isDirectory()) file = join(file, "index.html");
  if (!existsSync(file)) { res.writeHead(404).end("not found"); return; }
  const size = statSync(file).size;
  const headers = { "Content-Type": TYPES[extname(file)] ?? "application/octet-stream", "Accept-Ranges": "bytes",
                    "Access-Control-Allow-Origin": "*" };
  const m = /bytes=(\d*)-(\d*)/.exec(req.headers.range ?? "");
  if (m) {
    const start = m[1] ? Number(m[1]) : size - Number(m[2]);
    const end = m[1] && m[2] ? Math.min(Number(m[2]), size - 1) : size - 1;
    res.writeHead(206, { ...headers, "Content-Range": `bytes ${start}-${end}/${size}`, "Content-Length": end - start + 1 });
    createReadStream(file, { start, end }).pipe(res);
  } else {
    res.writeHead(200, { ...headers, "Content-Length": size });
    createReadStream(file).pipe(res);
  }
}).listen(PORT, () => console.log(`site/ at http://localhost:${PORT}${PREFIX}`));
