/// <reference lib="webworker" />
/**
 * Query worker. Only the latest query runs: a new query aborts the previous one, so dragging the
 * point or the radius slider never queues stale range requests.
 * The visible layer group is read first and posted as a partial result.
 */
import { layersFor, runQuery } from "./query";
import { CogSource } from "./source";
import type { FxTable, Manifest, QueryResult } from "./types";

export type WorkerIn =
  | { type: "init"; dataUrl: string }
  | { type: "query"; id: number; lat: number; lon: number; radiusKm: number; first: "population" | "gdp" };

export type WorkerOut =
  | { type: "ready"; manifest: Manifest; fx: FxTable }
  | { type: "result"; id: number; partial: boolean; result: QueryResult }
  | { type: "error"; id?: number; message: string };

declare const self: DedicatedWorkerGlobalScope;

let manifest: Manifest | undefined;
let source: CogSource | undefined;
let current: AbortController | undefined;

const post = (m: WorkerOut) => self.postMessage(m);

self.onmessage = async (ev: MessageEvent<WorkerIn>) => {
  const msg = ev.data;
  try {
    if (msg.type === "init") {
      const base = new URL(msg.dataUrl, self.location.href).toString();
      manifest = (await (await fetch(new URL("manifest.json", base))).json()) as Manifest;
      const fx = (await (await fetch(new URL(manifest.fx, base))).json()) as FxTable;
      source = new CogSource(base);
      post({ type: "ready", manifest, fx });
      return;
    }
    if (msg.type === "query") {
      if (!manifest || !source) throw new Error("worker not initialised");
      current?.abort();
      const ctl = new AbortController();
      current = ctl;
      const all = layersFor(manifest, msg.first);
      const firstGroup = all.filter((l) => l.startsWith(msg.first === "population" ? "pop_" : "gdp_"));
      const params = { lat: msg.lat, lon: msg.lon, radiusKm: msg.radiusKm };

      const partial = await runQuery(manifest, source, { ...params, layers: firstGroup }, ctl.signal);
      if (ctl.signal.aborted) return;
      post({ type: "result", id: msg.id, partial: true, result: partial });

      const rest = all.filter((l) => !firstGroup.includes(l));
      const second = await runQuery(manifest, source, { ...params, layers: rest }, ctl.signal);
      if (ctl.signal.aborted) return;
      post({
        type: "result", id: msg.id, partial: false,
        result: { ...partial, params: { ...params, layers: all }, layers: { ...partial.layers, ...second.layers },
          ms: partial.ms + second.ms },
      });
    }
  } catch (e) {
    if ((e as Error)?.name === "AbortError") return;
    post({ type: "error", id: msg.type === "query" ? msg.id : undefined, message: String((e as Error)?.message ?? e) });
  }
};
