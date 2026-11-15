/** Main-thread wrapper around the query worker. */
import type { WorkerIn, WorkerOut } from "./worker";
import type { FxTable, Manifest, QueryResult } from "./types";

export interface EngineCallbacks {
  onResult(result: QueryResult, partial: boolean): void;
  onError(message: string): void;
}

export class Engine {
  private worker: Worker;
  private nextId = 1;
  private latest = 0;
  readonly ready: Promise<{ manifest: Manifest; fx: FxTable }>;

  constructor(dataUrl: string, private cb: EngineCallbacks) {
    this.worker = new Worker(new URL("./worker.ts", import.meta.url), { type: "module" });
    this.ready = new Promise((resolve, reject) => {
      this.worker.onmessage = (ev: MessageEvent<WorkerOut>) => {
        const m = ev.data;
        if (m.type === "ready") resolve({ manifest: m.manifest, fx: m.fx });
        else if (m.type === "result" && m.id === this.latest) this.cb.onResult(m.result, m.partial);
        else if (m.type === "error") {
          if (m.id === undefined) reject(new Error(m.message));
          else if (m.id === this.latest) this.cb.onError(m.message);
        }
      };
    });
    this.post({ type: "init", dataUrl });
  }

  private post(m: WorkerIn) {
    this.worker.postMessage(m);
  }

  /** Starts a query; any earlier query is cancelled and its results are dropped. */
  query(lat: number, lon: number, radiusKm: number, first: "population" | "gdp"): number {
    const id = this.nextId++;
    this.latest = id;
    this.post({ type: "query", id, lat, lon, radiusKm, first });
    return id;
  }

  dispose() {
    this.worker.terminate();
  }
}
