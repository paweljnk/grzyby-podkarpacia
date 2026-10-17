import { useEffect, useRef, useState } from "react";
import maplibregl, { type StyleSpecification } from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { api, type Query } from "./api";
import type { Envelope } from "./types";
import { SCORE_STOPS, TREE_NAMES, Warnings, Footer, ErrorBox } from "./ui";

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

const bboxOf = (m: maplibregl.Map) => { const b = m.getBounds(); return [b.getWest(), b.getSouth(), b.getEast(), b.getNorth()].map((x) => x.toFixed(4)).join(","); };

export function MapView({ q, onOpen }: { q: Query; onOpen: (id: number) => void }) {
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
        for (const id of ["lasy", "ochrona", "zasieg", "pokrycie"]) m.addSource(id, { type: "geojson", data: empty });
        m.addLayer({ id: "pokrycie-fill", type: "fill", source: "pokrycie", paint: {
          "fill-color": ["match", ["get", "klasa"], ...Object.entries(COVER_COLORS).flat(), "#cccccc"] as unknown as Expr, "fill-opacity": 0.55 } });
        m.addLayer({ id: "zasieg", type: "line", source: "zasieg", paint: { "line-color": "#2f4a2c", "line-dasharray": [2, 2], "line-width": 1.5 } });
        // przezroczystość = pewność danych (warunki i pewność to osobne informacje)
        m.addLayer({ id: "lasy-fill", type: "fill", source: "lasy", paint: {
          "fill-color": fillColor("wynik"),
          "fill-opacity": ["interpolate", ["linear"], ["coalesce", ["get", "pewnosc"], 0], 0, 0.25, 1, 0.9] as unknown as Expr } });
        m.addLayer({ id: "lasy-line", type: "line", source: "lasy", paint: {
          "line-color": ["case", ["get", "rekomendowane"], "#24502a", "#7d7568"] as unknown as Expr, "line-width": 0.6 } });
        m.addLayer({ id: "ochrona-fill", type: "fill", source: "ochrona", paint: {
          "fill-color": ["match", ["get", "rodzaj"], "park_narodowy", "#b0413e", "zakaz_wstepu", "#d97a1f", "#8a6fb0"] as unknown as Expr, "fill-opacity": 0.18 } });
        m.addLayer({ id: "ochrona-line", type: "line", source: "ochrona", paint: {
          "line-color": ["match", ["get", "rodzaj"], "park_narodowy", "#b0413e", "zakaz_wstepu", "#d97a1f", "#8a6fb0"] as unknown as Expr, "line-width": 2 } });
        m.on("click", "lasy-fill", (e) => { const id = e.features?.[0]?.properties?.id; if (id != null) onOpen(Number(id)); });
        m.on("mouseenter", "lasy-fill", () => (m.getCanvas().style.cursor = "pointer"));
        m.on("mouseleave", "lasy-fill", () => (m.getCanvas().style.cursor = ""));
        let t: ReturnType<typeof setTimeout>;
        m.on("moveend", () => { clearTimeout(t); t = setTimeout(() => setView((v) => v + 1), 300); });
        setReady(true);
      });
      map.current = m;
    })();
    return () => { cancelled = true; map.current?.remove(); map.current = null; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!ready || !map.current) return;
    const m = map.current;
    (m.getSource("zasieg") as maplibregl.GeoJSONSource).setData({ type: "FeatureCollection", features: [circle(q.lat, q.lon, q.radius_km)] });
    m.easeTo({ center: [q.lon, q.lat] });
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
    if (mode === "pokrycie" || q.dataset === "real")
      api.coverage(bbox).then((g) => (m.getSource("pokrycie") as maplibregl.GeoJSONSource).setData(g)).catch(() => {});
  }, [ready, q, view, mode]);

  useEffect(() => {
    if (!ready) return;
    map.current?.setPaintProperty("lasy-fill", "fill-color", fillColor(mode));
    map.current?.setLayoutProperty("pokrycie-fill", "visibility", mode === "pokrycie" || zoomHint ? "visible" : "none");
  }, [ready, mode, zoomHint]);
  useEffect(() => {
    if (!ready) return;
    for (const id of ["ochrona-fill", "ochrona-line"]) map.current?.setLayoutProperty(id, "visibility", showProt ? "visible" : "none");
  }, [ready, showProt]);

  return (
    <section className="view view-map">
      <Warnings env={env} />
      {err && <ErrorBox error={err} />}
      {!basemapOk && <div className="banner banner-warn">Podkład mapowy niedostępny — widoczne tylko warstwy aplikacji.</div>}
      {zoomHint && <div className="banner banner-info" data-testid="zoom-hint">Przybliż mapę, aby zobaczyć ocenę wydzieleń. Teraz widać pokrycie danymi.</div>}
      <div className="map-controls">
        <label>Warstwa{" "}
          <select value={mode} onChange={(e) => setMode(e.target.value as Mode)} data-testid="map-mode">
            <option value="wynik">warunki (przezroczystość = pewność)</option>
            <option value="pokrycie">pokrycie danymi</option>
            <option value="drzewostan">drzewostany (gatunek panujący)</option>
            <option value="siedlisko">siedliska (typ siedliskowy)</option>
            <option value="opad">opady z 7 dni</option>
          </select>
        </label>
        <label className="chk"><input type="checkbox" checked={showProt} onChange={(e) => setShowProt(e.target.checked)} /> ochrona i zakazy</label>
        {loading && <span className="muted small">ładowanie…</span>}
      </div>
      <div ref={box} className="map" data-testid="map" />
      <Legend mode={mode} zoomHint={zoomHint} />
      <Footer env={env} />
    </section>
  );
}

function Legend({ mode, zoomHint }: { mode: Mode; zoomHint: boolean }) {
  const cover = (
    <div className="legend" data-testid="legend-coverage">
      <span><i style={{ background: COVER_COLORS.pelniejsze }} />dane pełniejsze</span>
      <span><i style={{ background: COVER_COLORS.czesciowe }} />dane częściowe</span>
      <span><i style={{ background: COVER_COLORS.brak_oceny }} />brak możliwości oceny</span>
      <span className="muted">siatka 1 km; las wg ESA WorldCover. „Brak oceny” ≠ brak grzybów.</span>
    </div>
  );
  if (mode === "pokrycie" || zoomHint) return cover;
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
