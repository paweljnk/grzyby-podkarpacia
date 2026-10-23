import type { Dataset, MonthResp, PlaceCard, RankingResp, SpeciesItem, WeekResp, Envelope, Scored } from "./types";

async function get<T>(path: string, params: Record<string, string | number | boolean | undefined> = {}): Promise<T> {
  const q = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v !== undefined && v !== "") q.set(k, String(v));
  let r: Response;
  try {
    r = await fetch(`/api/${path}${q.toString() ? "?" + q : ""}`, { redirect: "error" });
  } catch {
    // brak odpowiedzi serwera (uśpiony codespace, wyłączony komputer, brak sieci albo przekierowanie na logowanie)
    throw new Error(navigator.onLine
      ? "Brak połączenia z serwerem aplikacji — serwer jest wyłączony, uśpiony albo wymaga ponownego zalogowania. Spróbuj za chwilę."
      : "Brak internetu — pokazuję tylko zapisane wcześniej dane.");
  }
  if (!r.ok) {
    let msg = `Błąd ${r.status}`;
    try { const j = await r.json(); if (typeof j.detail === "string") msg = j.detail; } catch { /* brak treści */ }
    throw new Error(msg);
  }
  return r.json() as Promise<T>;
}

export interface Query { species: string; lat: number; lon: number; radius_km: number; date: string; calendar: boolean; dataset: Dataset }

const base = (q: Query) => ({ species: q.species, date: q.date, calendar: q.calendar ? "on" : "off", dataset: q.dataset });

export const api = {
  species: () => get<SpeciesItem[]>("gatunki"),
  ranking: (q: Query, punkty = false) => get<RankingResp>("ranking", { ...base(q), lat: q.lat, lon: q.lon, radius_km: q.radius_km, punkty: punkty || undefined }),
  map: (q: Query) => get<Envelope & { geojson: GeoJSON.FeatureCollection }>("mapa", { ...base(q), lat: q.lat, lon: q.lon, radius_km: Math.min(q.radius_km, 30) }),
  mapBbox: (q: Query, bbox: string) => get<Envelope & { tryb: string; geojson: GeoJSON.FeatureCollection }>("mapa", { ...base(q), bbox }),
  coverage: (bbox: string) => get<GeoJSON.FeatureCollection>("pokrycie", { bbox }),
  protection: (ds: Dataset) => get<GeoJSON.FeatureCollection>("warstwy/ochrona", { dataset: ds }),
  place: (id: number, q: Query) => get<Envelope & { miejsce: PlaceCard }>(`miejsce/${id}`, { ...base(q), lat: q.lat, lon: q.lon }),
  week: (id: number, q: Query) => get<WeekResp>(`miejsce/${id}/7dni`, { species: q.species, calendar: q.calendar ? "on" : "off", dataset: q.dataset, start: q.date }),
  month: (q: Query, month: string, placeId?: number) => get<MonthResp>("kalendarz", { species: q.species, month, lat: q.lat, lon: q.lon, dataset: q.dataset, place_id: placeId }),
  compare: (ids: number[], q: Query) => get<Envelope & { miejsca: Scored[] }>("porownanie", { ...base(q), ids: ids.join(",") }),
};

/** Geokodowanie: Nominatim (OSM) — maks. 1 zapytanie/s, wyniki zawężone do Podkarpacia, wymagane oznaczenie OSM. */
let lastGeocode = 0;
export async function geocode(text: string): Promise<{ name: string; lat: number; lon: number }[]> {
  const wait = 1100 - (Date.now() - lastGeocode);
  if (wait > 0) await new Promise((r) => setTimeout(r, wait));
  lastGeocode = Date.now();
  const q = new URLSearchParams({ q: text, format: "jsonv2", countrycodes: "pl", limit: "5", "accept-language": "pl",
    viewbox: "21.1,50.85,23.6,49.0", bounded: "1" });
  const r = await fetch(`https://nominatim.openstreetmap.org/search?${q}`);
  if (!r.ok) throw new Error("Wyszukiwarka miejscowości niedostępna");
  const j = (await r.json()) as { display_name: string; lat: string; lon: string }[];
  return j.map((x) => ({ name: x.display_name, lat: +x.lat, lon: +x.lon }));
}
