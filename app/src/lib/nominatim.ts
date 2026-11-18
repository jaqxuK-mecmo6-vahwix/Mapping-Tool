/**
 * Place search with OpenStreetMap Nominatim.
 * Usage policy (https://operations.osmfoundation.org/policies/nominatim/): at most 1 request per
 * second and no autocomplete, so the app searches only when the user submits the form.
 */
export interface Place {
  name: string;
  lat: number;
  lon: number;
  type: string;
}

// ISO 3166-1 alpha-2 for coverage (Eurostat uses EL and UK; OSM uses gr and gb)
const COUNTRIES = "at,be,bg,hr,cy,cz,dk,ee,fi,fr,de,gr,hu,ie,it,lv,lt,lu,mt,nl,pl,pt,ro,sk,si,es,se,gb,ch,no";
const ENDPOINT = "https://nominatim.openstreetmap.org/search";
let last = 0;

export async function searchPlaces(q: string, signal?: AbortSignal): Promise<Place[]> {
  const wait = 1000 - (Date.now() - last);
  if (wait > 0) await new Promise((r) => setTimeout(r, wait));
  last = Date.now();
  const url = new URL(ENDPOINT);
  url.searchParams.set("q", q);
  url.searchParams.set("format", "jsonv2");
  url.searchParams.set("limit", "6");
  url.searchParams.set("countrycodes", COUNTRIES);
  const res = await fetch(url, { signal, headers: { "Accept-Language": navigator.language || "en" } });
  if (!res.ok) throw new Error(`Search failed (${res.status})`);
  const data = (await res.json()) as { display_name: string; lat: string; lon: string; type: string }[];
  return data.map((d) => ({ name: d.display_name, lat: Number(d.lat), lon: Number(d.lon), type: d.type }));
}
