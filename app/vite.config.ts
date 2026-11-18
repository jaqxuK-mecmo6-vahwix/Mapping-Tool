/// <reference types="vitest/config" />
import { createReadStream, existsSync, statSync } from "node:fs";
import { extname, join, normalize, resolve } from "node:path";
import { defineConfig, type Plugin } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { VitePWA } from "vite-plugin-pwa";

const DATA_DIR = resolve(__dirname, "../data/build");
const TYPES: Record<string, string> = {
  ".json": "application/json", ".geojson": "application/geo+json",
  ".tif": "image/tiff", ".pmtiles": "application/octet-stream",
};

/** Dev only: serve ../data/build at /data/ with HTTP Range support, like the production static host. */
function devData(): Plugin {
  return {
    name: "radiusstats-dev-data",
    apply: "serve",
    configureServer(server) {
      server.middlewares.use("/data", (req, res, next) => {
        const rel = normalize(decodeURIComponent((req.url ?? "/").split("?")[0])).replace(/^([/\\])+/, "");
        const file = join(DATA_DIR, rel);
        if (!file.startsWith(DATA_DIR) || !existsSync(file) || statSync(file).isDirectory()) return next();
        const size = statSync(file).size;
        res.setHeader("Accept-Ranges", "bytes");
        res.setHeader("Access-Control-Allow-Origin", "*");
        res.setHeader("Content-Type", TYPES[extname(file)] ?? "application/octet-stream");
        const m = /bytes=(\d*)-(\d*)/.exec(req.headers.range ?? "");
        if (m) {
          const start = m[1] ? Number(m[1]) : size - Number(m[2]);
          const end = m[1] && m[2] ? Math.min(Number(m[2]), size - 1) : size - 1;
          res.statusCode = 206;
          res.setHeader("Content-Range", `bytes ${start}-${end}/${size}`);
          res.setHeader("Content-Length", end - start + 1);
          createReadStream(file, { start, end }).pipe(res);
        } else {
          res.setHeader("Content-Length", size);
          createReadStream(file).pipe(res);
        }
      });
    },
  };
}

export default defineConfig({
  // relative asset URLs: the same build works at a domain root and in a subfolder
  // (GitHub Pages project sites are served from https://<user>.github.io/<repo>/)
  base: "./",
  plugins: [
    react(),
    tailwindcss(),
    devData(),
    VitePWA({
      registerType: "autoUpdate",
      // app shell only: data (COGs, PMTiles, manifest) is never precached or runtime-cached
      workbox: { globPatterns: ["**/*.{js,css,html,svg,png,webmanifest}"], navigateFallbackDenylist: [/\/data\//] },
      includeAssets: ["icon.svg"],
      manifest: {
        name: "RadiusStats Europe",
        short_name: "RadiusStats",
        description: "Population and GDP within a radius of any point in Europe",
        theme_color: "#1e293b",
        background_color: "#f8fafc",
        display: "standalone",
        start_url: ".",
        icons: [
          { src: "icon-192.png", sizes: "192x192", type: "image/png" },
          { src: "icon-512.png", sizes: "512x512", type: "image/png" },
          { src: "icon.svg", sizes: "any", type: "image/svg+xml", purpose: "any maskable" },
        ],
      },
    }),
  ],
  // The project folder name contains ':', which Vite's fs allow-list check mis-handles (403 on index.html).
  // Dev server only; it never affects the production build.
  server: { fs: { strict: false } },
  worker: { format: "es" },
  build: {
    chunkSizeWarningLimit: 1100,
    // MapLibre is most of the bundle; a separate chunk survives app updates in the browser cache
    rollupOptions: { output: { manualChunks: { maplibre: ["maplibre-gl"] } } },
  },
  test: { environment: "node", testTimeout: 30000 },
});
