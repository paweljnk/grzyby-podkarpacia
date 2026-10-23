import { useEffect, useRef, useState } from "react";
import maplibregl, { type StyleSpecification } from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { api, type Query } from "./api";
import type { Envelope, RankingResp } from "./types";
import { icons } from "./icons";
import { PlaceView } from "./views";
import { SCORE_STOPS, TREE_NAMES, Warnings, Footer, ErrorBox, ScoreBadge, Conditions, scoreColor } from "./ui";

const PINS = 20;   // tyle pierwszych miejsc rankingu ma numerowany znacznik na mapie

const BASEMAP = "https://tiles.openfreemap.org/styles/liberty";
const FALLBACK: StyleSpecification = {
  version: 8, sources: {}, layers: [{ id: "bg", type: "background", paint: { "background-color": "#ece8dd" } }],
};

type Mode = "wynik" | "pokrycie" | "drzewostan" | "siedlisko" | "opad";
const TREE_COLORS: Record<string, string> = { SO: "#c98c3c", SW: "#3d6b4f", JD: "#2e5a6b", BK: "#9a6a3a", DB: "#7a7a2e", BRZ: "#d9cf9a", OL: "#6f8f9a", OLS: "#8fa7ad", GB: "#a59060" };
const COVER_COLORS: Record<string, string> = { pelniejsze: "#2f6f8f", czesciowe: "#8fb8cf", brak_oceny: "#c7a3c9" };
type Expr = maplibregl.ExpressionSpecification;

function circle(lat: number, lon: number, km: number): GeoJSON.Feature<GeoJSON.Polygon> {
  const pts: [number, number][] = [];
  for (let i = 0; i <= 64; i++) {
    const a = (i / 64) * 2 * Math.PI;
    pts.push([lon + (km / (111.32 * Math.cos((lat * Math.PI) / 180))) * Math.cos(a), lat + (km / 110.57) * Math.sin(a)]);
  }
  return { type: "Feature", properties: {}, geometry: { type: "Polygon", coordinates: [pts] } };
}

function fillColor(mode: Mode): Expr | string {
  if (mode === "wynik" || mode === "pokrycie")
    return ["case", ["==", ["get", "wynik"], null], "#c9c4b8",
      ["interpolate", ["linear"], ["get", "wynik"], ...SCORE_STOPS.flat()]] as unknown as Expr;
  if (mode === "drzewostan")
    return ["match", ["get", "gatunek_panujacy"], ...Object.entries(TREE_COLORS).flat(), "#b9b4a6"] as unknown as Expr;
  if (mode === "siedlisko")
    return ["match", ["slice", ["coalesce", ["get", "typ_siedliskowy"], "?"], 0, 1], "B", "#d8b46a", "L", "#6e9a5a", "O", "#5f8a9a", "#b9b4a6"] as unknown as Expr;
  return ["case", ["==", ["get", "opad_7d_mm"], null], "#c9c4b8",
    ["interpolate", ["linear"], ["get", "opad_7d_mm"], 0, "#f1ede4", 10, "#bcd3e3", 30, "#6c9cc2", 60, "#2d5f8f"]] as unknown as Expr;
}

const km = (a: [number, number], b: [number, number]) =>
  Math.hypot((a[0] - b[0]) * 111.32 * Math.cos((a[1] * Math.PI) / 180), (a[1] - b[1]) * 110.57);

const bboxOf = (m: maplibregl.Map) => { const b = m.getBounds(); return [b.getWest(), b.getSouth(), b.getEast(), b.getNorth()].map((x) => x.toFixed(4)).join(","); };

const BOUNDS = { lat: [48.9, 51.0], lon: [21.0, 23.7] };   // zakres API (województwo podkarpackie z zapasem)

export function MapView({ q, setQ, go, visible = true, compareIds, toggleCompare }: {
  q: Query; setQ: (p: Partial<Query>) => void; go: (h: string) => void; visible?: boolean;
  compareIds: number[]; toggleCompare: (id: number) => void;
}) {
  const box = useRef<HTMLDivElement>(null);
  const map = useRef<maplibregl.Map | null>(null);
  const [ready, setReady] = useState(false);
  const [basemapOk, setBasemapOk] = useState(true);
  const [mode, setMode] = useState<Mode>("wynik");
  const [showProt, setShowProt] = useState(true);
  const [env, setEnv] = useState<Envelope | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [zoomHint, setZoomHint] = useState(false);
  const [loading, setLoading] = useState(false);
  const [view, setView] = useState(0);   // licznik ruchów mapy — przeładowanie warstw
  const [rank, setRank] = useState<RankingResp | null>(null);
  const [rankErr, setRankErr] = useState<string | null>(null);
  const [sel, setSel] = useState<number | null>(null);
  const [moved, setMoved] = useState(false);
  const [sheet, setSheet] = useState<"peek" | "half" | "full">("half");   // panel rankingu na telefonie
  const [detail, setDetail] = useState<number | null>(null);             // karta miejsca w panelu (bez opuszczania mapy)
  const [geoMsg, setGeoMsg] = useState<string | null>(null);
  const [locating, setLocating] = useState(false);
  const me = useRef<maplibregl.Marker | null>(null);
  const pins = useRef<maplibregl.Marker[]>([]);
  const rankIds = useRef<Set<number>>(new Set());
  const qRef = useRef(q);
  qRef.current = q;

  useEffect(() => {
    let cancelled = false;
    (async () => {
      let style: StyleSpecification | string = FALLBACK;
      try {
        const ctl = new AbortController();
        const t = setTimeout(() => ctl.abort(), 4000);
        const r = await fetch(BASEMAP, { signal: ctl.signal });
        clearTimeout(t);
        if (r.ok) style = BASEMAP; else setBasemapOk(false);
      } catch { setBasemapOk(false); }
      if (cancelled || !box.current) return;
      const m = new maplibregl.Map({ container: box.current, style, center: [q.lon, q.lat], zoom: 11, attributionControl: { compact: true } });
      m.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
      m.on("load", () => {
        const empty: GeoJSON.FeatureCollection = { type: "FeatureCollection", features: [] };
        for (const id of ["lasy", "ochrona", "zasieg", "pokrycie", "punkty"]) m.addSource(id, { type: "geojson", data: empty });
        // warstwy aplikacji pod nazwami miejscowości i dróg podkładu — mapa pozostaje czytelna
        const labels = m.getStyle().layers.find((l) => l.type === "symbol")?.id;
        const addLayer = (l: maplibregl.AddLayerObject) => m.addLayer(l, l.type === "fill" ? labels : undefined);
        addLayer({ id: "pokrycie-fill", type: "fill", source: "pokrycie", paint: {
          "fill-color": ["match", ["get", "klasa"], ...Object.entries(COVER_COLORS).flat(), "#cccccc"] as unknown as Expr, "fill-opacity": 0.55 } });
        m.addLayer({ id: "zasieg", type: "line", source: "zasieg", paint: { "line-color": "#2f4a2c", "line-dasharray": [2, 2], "line-width": 1.5 } });
        // przezroczystość = pewność danych (warunki i pewność to osobne informacje)
        addLayer({ id: "lasy-fill", type: "fill", source: "lasy", paint: {
          "fill-color": fillColor("wynik"),
          "fill-opacity": ["interpolate", ["linear"], ["coalesce", ["get", "pewnosc"], 0], 0, 0.2, 1, 0.75] as unknown as Expr } });
        addLayer({ id: "lasy-line", type: "line", source: "lasy", minzoom: 12, paint: {
          "line-color": "#24502a", "line-opacity": 0.35, "line-width": 0.5 } });
        addLayer({ id: "lasy-sel", type: "line", source: "lasy", filter: ["==", ["get", "id"], -1], paint: {
          "line-color": "#d9480f", "line-width": 3 } });
        // wszystkie ocenione wydzielenia w promieniu (kropki) — widoczne, gdy mapa jest oddalona i nie ma kształtów
        m.addLayer({ id: "punkty", type: "circle", source: "punkty", paint: {
          "circle-color": ["case", ["==", ["get", "r"], 0], "#9aa19c", ["==", ["get", "w"], null], "#c9c4b8",
            ["interpolate", ["linear"], ["get", "w"], ...SCORE_STOPS.flat()]] as unknown as Expr,
          "circle-radius": ["interpolate", ["linear"], ["zoom"], 7, 1.6, 10, 3, 13, 5] as unknown as Expr,
          "circle-opacity": ["case", ["==", ["get", "r"], 0], 0.55, 0.9] as unknown as Expr,
          "circle-stroke-color": "#ffffff", "circle-stroke-width": ["interpolate", ["linear"], ["zoom"], 8, 0, 11, 0.6] as unknown as Expr } });
        addLayer({ id: "ochrona-fill", type: "fill", source: "ochrona", paint: {
          "fill-color": ["match", ["get", "rodzaj"], "park_narodowy", "#b0413e", "zakaz_wstepu", "#d97a1f", "#8a6fb0"] as unknown as Expr, "fill-opacity": 0.18 } });
        m.addLayer({ id: "ochrona-line", type: "line", source: "ochrona", paint: {
          "line-color": ["match", ["get", "rodzaj"], "park_narodowy", "#b0413e", "zakaz_wstepu", "#d97a1f", "#8a6fb0"] as unknown as Expr, "line-width": 2 } });
        for (const layer of ["lasy-fill", "punkty"]) {
          m.on("click", layer, (e) => {
            const id = e.features?.[0]?.properties?.id;
            if (id == null) return;
            if (rankIds.current.has(Number(id))) { setSel(Number(id)); setSheet((x) => (x === "peek" ? "half" : x)); }
            else openDetail(Number(id));
          });
          m.on("mouseenter", layer, () => (m.getCanvas().style.cursor = "pointer"));
          m.on("mouseleave", layer, () => (m.getCanvas().style.cursor = ""));
        }
        m.on("mouseenter", "lasy-fill", () => (m.getCanvas().style.cursor = "pointer"));
        m.on("mouseleave", "lasy-fill", () => (m.getCanvas().style.cursor = ""));
        let t: ReturnType<typeof setTimeout>;
        m.on("moveend", (e) => {
          clearTimeout(t); t = setTimeout(() => setView((v) => v + 1), 300);
          // „Szukaj w tym obszarze” tylko po ruchu wykonanym przez użytkownika (nie po dopasowaniu do rankingu)
          if ((e as { originalEvent?: unknown }).originalEvent) {
            const c = m.getCenter(), qq = qRef.current;
            setMoved(km([c.lng, c.lat], [qq.lon, qq.lat]) > Math.max(2, qq.radius_km / 3));
          }
        });
        setReady(true);
      });
      map.current = m;
    })();
    return () => { cancelled = true; map.current?.remove(); map.current = null; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    setRank(null); setRankErr(null); setSel(null); setMoved(false);
    api.ranking(q, true).then((r) => { setRank(r); rankIds.current = new Set(r.miejsca.map((x) => x.id)); })
      .catch((e) => setRankErr(String(e.message ?? e)));
  }, [q]);

  // kropki: wszystkie ocenione wydzielenia (także poza pierwszą pięćdziesiątką i wykluczone — szare)
  useEffect(() => {
    if (!ready || !map.current) return;
    const feats = (rank?.punkty ?? []).map(([lon, lat, w, r, p, id]) => ({
      type: "Feature" as const, geometry: { type: "Point" as const, coordinates: [lon, lat] }, properties: { w, r, p, id } }));
    (map.current.getSource("punkty") as maplibregl.GeoJSONSource).setData({ type: "FeatureCollection", features: feats });
  }, [ready, rank]);

  useEffect(() => {
    if (!ready || !map.current) return;
    map.current.setLayoutProperty("punkty", "visibility", zoomHint ? "visible" : "none");
  }, [ready, zoomHint]);

  // mapa ukryta (inna zakładka) zachowuje stan; po powrocie przeliczamy jej rozmiar
  useEffect(() => { if (visible) setTimeout(() => map.current?.resize(), 0); }, [visible]);

  // numerowane znaczniki = pozycje w rankingu (ten sam numer na mapie i na liście)
  useEffect(() => {
    if (!ready || !map.current) return;
    pins.current.forEach((p) => p.remove());
    pins.current = (rank?.miejsca ?? []).slice(0, PINS).map((m, i) => {
      const el = document.createElement("button");
      el.className = "map-pin";
      el.innerHTML = `<span>${i + 1}</span>`;
      el.style.setProperty("--score-c", scoreColor(m.wynik));
      el.style.setProperty("--score-fg", (m.wynik ?? 0) > 55 ? "#fff" : "#1d2a1b");
      el.title = `${i + 1}. ${m.nazwa} — wskaźnik ${m.wynik == null ? "—" : Math.round(m.wynik)}/100`;
      el.dataset.testid = "map-pin";
      el.dataset.id = String(m.id);
      el.addEventListener("click", (ev) => { ev.stopPropagation(); setSel(m.id); setSheet((x) => (x === "peek" ? "half" : x)); });
      return new maplibregl.Marker({ element: el }).setLngLat([m.lon, m.lat]).addTo(map.current!);
    });
    // mapa pokazuje punkt wyszukiwania i wszystkie numerowane miejsca
    const top = (rank?.miejsca ?? []).slice(0, PINS);
    if (!top.length) map.current.easeTo({ center: [q.lon, q.lat] });
    else {
      const b = new maplibregl.LngLatBounds([q.lon, q.lat], [q.lon, q.lat]);
      top.forEach((m) => b.extend([m.lon, m.lat]));
      const wide = window.innerWidth >= 900;
      const panel = document.querySelector<HTMLElement>(".sheet");
      const pad = wide ? { top: 70, bottom: 40, left: (panel?.offsetWidth ?? 0) + 50, right: 50 }
                       : { top: 110, bottom: (panel?.offsetHeight ?? 0) + 30, left: 30, right: 30 };
      map.current.fitBounds(b, { padding: pad, maxZoom: 13, duration: 600 });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ready, rank]);

  useEffect(() => {
    if (!ready || !map.current) return;
    map.current.setFilter("lasy-sel", ["==", ["get", "id"], sel ?? -1]);
    for (const p of pins.current) p.getElement().classList.toggle("sel", p.getElement().dataset.id === String(sel));
    // przewijamy tylko listę rankingu (nie całą stronę — mapa ma zostać na ekranie)
    const row = sel != null ? document.querySelector<HTMLElement>(`[data-rank-id="${sel}"]`) : null;
    const list = row?.closest<HTMLElement>(".sheet-body");
    if (row && list) {
      const top = row.getBoundingClientRect().top - list.getBoundingClientRect().top + list.scrollTop - 8;
      list.scrollTo({ top, behavior: "smooth" });
    }
  }, [ready, sel]);

  function openDetail(id: number) {
    setDetail(id);
    setSel(id);
    setSheet("full");
  }
  const closeDetail = () => { setDetail(null); setSheet("half"); };

  const locate = () => {
    if (!("geolocation" in navigator)) { setGeoMsg("Ta przeglądarka nie udostępnia lokalizacji."); return; }
    setLocating(true); setGeoMsg(null);
    navigator.geolocation.getCurrentPosition((pos) => {
      setLocating(false);
      const { latitude: lat, longitude: lon } = pos.coords;
      const m = map.current;
      if (m) {
        if (!me.current) {
          const el = document.createElement("div");
          el.className = "me-dot";
          el.title = "Twoja lokalizacja";
          me.current = new maplibregl.Marker({ element: el });
        }
        me.current.setLngLat([lon, lat]).addTo(m);
      }
      if (lat < BOUNDS.lat[0] || lat > BOUNDS.lat[1] || lon < BOUNDS.lon[0] || lon > BOUNDS.lon[1]) {
        setGeoMsg("Jesteś poza województwem podkarpackim — ranking działa tylko dla Podkarpacia.");
        m?.flyTo({ center: [lon, lat], zoom: 9 });
        return;
      }
      setDetail(null);
      setQ({ lat: +lat.toFixed(4), lon: +lon.toFixed(4) });
    }, (e) => {
      setLocating(false);
      setGeoMsg(e.code === e.PERMISSION_DENIED
        ? "Brak zgody na lokalizację. Włącz ją w ustawieniach przeglądarki (Safari: Ustawienia → Prywatność → Usługi lokalizacji)."
        : "Nie udało się ustalić lokalizacji. Spróbuj ponownie na zewnątrz albo wyszukaj miejscowość w zakładce Szukaj.");
    }, { enableHighAccuracy: true, timeout: 15000, maximumAge: 0 });
  };

  const focus = (id: number, lon: number, lat: number) => {
    setSel(id);
    const m = map.current;
    if (m) m.flyTo({ center: [lon, lat], zoom: Math.max(m.getZoom(), 13.5) });
  };

  useEffect(() => {
    if (!ready || !map.current) return;
    const m = map.current;
    (m.getSource("zasieg") as maplibregl.GeoJSONSource).setData({ type: "FeatureCollection", features: [circle(q.lat, q.lon, q.radius_km)] });
    api.protection(q.dataset).then((g) => (m.getSource("ochrona") as maplibregl.GeoJSONSource).setData(g)).catch(() => {});
  }, [ready, q]);

  useEffect(() => {
    if (!ready || !map.current) return;
    const m = map.current;
    const bbox = bboxOf(m);
    setErr(null);
    setLoading(true);
    api.mapBbox(q, bbox).then((r) => {
      setEnv(r);
      setZoomHint(r.tryb === "przybliz");
      (m.getSource("lasy") as maplibregl.GeoJSONSource).setData(r.geojson);
    }).catch((e) => setErr(String(e.message ?? e))).finally(() => setLoading(false));
    if (mode === "pokrycie")
      api.coverage(bbox).then((g) => (m.getSource("pokrycie") as maplibregl.GeoJSONSource).setData(g)).catch(() => {});
  }, [ready, q, view, mode]);

  useEffect(() => {
    if (!ready) return;
    map.current?.setPaintProperty("lasy-fill", "fill-color", fillColor(mode));
    map.current?.setLayoutProperty("pokrycie-fill", "visibility", mode === "pokrycie" ? "visible" : "none");
  }, [ready, mode, zoomHint]);
  useEffect(() => {
    if (!ready) return;
    for (const id of ["ochrona-fill", "ochrona-line"]) map.current?.setLayoutProperty(id, "visibility", showProt ? "visible" : "none");
  }, [ready, showProt]);

  return (
    <section className="view view-map">
      <div className="map-stage">
        <div ref={box} className="map" data-testid="map" />

        {visible && <>
        <div className="map-float">
          <div className="chips">
            <label className="chip">
              {icons.warstwy}
              <select value={mode} onChange={(e) => setMode(e.target.value as Mode)} data-testid="map-mode" aria-label="Warstwa mapy">
                <option value="wynik">Warunki</option>
                <option value="pokrycie">Pokrycie danymi</option>
                <option value="drzewostan">Drzewostany</option>
                <option value="siedlisko">Siedliska</option>
                <option value="opad">Opady 7 dni</option>
              </select>
            </label>
            <label className={`chip${showProt ? " chip-on" : ""}`}>
              {icons.tarcza}
              <input type="checkbox" checked={showProt} onChange={(e) => setShowProt(e.target.checked)} />
              Ochrona i zakazy
            </label>
            <button className="chip" onClick={locate} disabled={locating} data-testid="my-location">
              {icons.lokalizacja}{locating ? "Ustalanie…" : "Moja lokalizacja"}
            </button>
            {loading && <span className="chip chip-quiet" aria-live="polite"><span className="spin" />Wczytywanie</span>}
          </div>
          <div className="toasts">
            <Warnings env={env} />
            {err && <ErrorBox error={err} />}
            {!basemapOk && <div className="banner banner-warn">Podkład mapowy niedostępny — widać tylko warstwy aplikacji.</div>}
            {geoMsg && <div className="banner banner-warn" role="status" data-testid="geo-msg">{geoMsg}</div>}
            {zoomHint && <div className="banner banner-info" data-testid="zoom-hint">Kropki to wszystkie ocenione wydzielenia w promieniu (szare — wykluczone). Przybliż, aby zobaczyć ich kształty.</div>}
          </div>
          {moved && (
            <button className="map-here" data-testid="search-here"
              onClick={() => { const c = map.current!.getCenter(); setQ({ lat: +c.lat.toFixed(4), lon: +c.lng.toFixed(4) }); }}>
              {icons.szukaj} Szukaj w tym obszarze
            </button>
          )}
        </div>

        <aside className={`sheet sheet-${sheet}`} aria-label="Ranking miejsc">
          <button className="sheet-handle" onClick={() => setSheet(sheet === "peek" ? "half" : sheet === "half" ? "full" : "peek")}
            aria-label={sheet === "full" ? "Zwiń listę" : "Rozwiń listę"} data-testid="sheet-handle"><span /></button>
          {detail != null && (
            <div className="sheet-body sheet-detail">
              <PlaceView id={detail} q={q} setQ={setQ} go={go} compareIds={compareIds} toggleCompare={toggleCompare} onBack={closeDetail} />
            </div>
          )}
          <div className="sheet-head" hidden={detail != null}>
            <div>
              <h2>Najlepsze miejsca</h2>
              <p className="muted small">
                {rank ? `${rank.miejsca.length} z ${rank.liczba_ocenionych.toLocaleString("pl-PL")} wydzieleń w promieniu ${q.radius_km} km` : "Wczytywanie rankingu…"}
              </p>
            </div>
            <label className="radius small">
              <span>Promień <strong>{q.radius_km} km</strong></span>
              <input type="range" min={5} max={60} step={5} value={q.radius_km} onChange={(e) => setQ({ radius_km: +e.target.value })} />
            </label>
          </div>
          <div className="sheet-body" hidden={detail != null}>
            {rankErr && <ErrorBox error={rankErr} />}
            {rank && rank.miejsca.length === 0 && <p className="note">Brak miejsc spełniających warunki w tym promieniu. Zwiększ promień albo zmień dzień.</p>}
            <ol className="mrank" data-testid="map-ranking">
              {rank?.miejsca.map((m, i) => (
                <li key={m.id} data-rank-id={m.id} className={sel === m.id ? "sel" : ""}>
                  <button className="mrank-main" onClick={() => focus(m.id, m.lon, m.lat)} data-testid="map-ranking-item">
                    <span className="mrank-pos">{i + 1}</span>
                    <ScoreBadge value={m.wynik} excluded={!m.rekomendowane} />
                    <span className="rank-text">
                      <strong>{m.nazwa}</strong>
                      <span className="muted small">
                        {m.gatunek_panujacy ? TREE_NAMES[m.gatunek_panujacy] ?? m.gatunek_panujacy : "drzewostan: brak"}
                        {m.odleglosc_km != null && <> · {m.odleglosc_km} km w linii prostej</>}
                      </span>
                      <Conditions v={m.warunki} lo={m.warunki_min} hi={m.warunki_max} pewnosc={m.pewnosc} opis={m.pewnosc_opis} />
                    </span>
                  </button>
                  <button className="mrank-open" onClick={() => openDetail(m.id)} data-testid="map-ranking-open" aria-label={`Szczegóły: ${m.nazwa}`}>
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><path d="m9 6 6 6-6 6" /></svg>
                  </button>
                </li>
              ))}
            </ol>
            <p className="muted tiny explain">Liczba to wskaźnik rekomendacji 0–100 — nie procent ani prawdopodobieństwo.
              Numer na mapie odpowiada pozycji na liście.</p>
            <Legend mode={mode} />
            <Footer env={env} />
          </div>
        </aside>
        </>}
      </div>
    </section>
  );
}

function Legend({ mode }: { mode: Mode }) {
  const cover = (
    <div className="legend" data-testid="legend-coverage">
      <span><i style={{ background: COVER_COLORS.pelniejsze }} />dane pełniejsze</span>
      <span><i style={{ background: COVER_COLORS.czesciowe }} />dane częściowe</span>
      <span><i style={{ background: COVER_COLORS.brak_oceny }} />brak możliwości oceny</span>
      <span className="muted">siatka 1 km; las wg ESA WorldCover. „Brak oceny” ≠ brak grzybów.</span>
    </div>
  );
  if (mode === "pokrycie") return cover;
  if (mode === "drzewostan")
    return <div className="legend">{Object.entries(TREE_COLORS).map(([k, c]) => <span key={k}><i style={{ background: c }} />{TREE_NAMES[k]}</span>)}</div>;
  if (mode === "siedlisko")
    return <div className="legend"><span><i style={{ background: "#d8b46a" }} />bory</span><span><i style={{ background: "#6e9a5a" }} />lasy</span><span><i style={{ background: "#5f8a9a" }} />olsy</span></div>;
  if (mode === "opad")
    return <div className="legend"><span><i style={{ background: "#f1ede4" }} />0 mm</span><span><i style={{ background: "#6c9cc2" }} />30</span><span><i style={{ background: "#2d5f8f" }} />60+ mm</span><span className="muted">komórka siatki ~10 km</span></div>;
  return (
    <div className="legend">
      {SCORE_STOPS.map(([v, c]) => <span key={v}><i style={{ background: c }} />{v}</span>)}
      <span><i style={{ background: "#c9c4b8" }} />brak oceny</span>
      <span className="muted">warunki 0–100; bledszy kolor = niższa pewność danych</span>
    </div>
  );
}
