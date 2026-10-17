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

type Mode = "wynik" | "drzewostan" | "siedlisko" | "opad";
const TREE_COLORS: Record<string, string> = { SO: "#c98c3c", SW: "#3d6b4f", JD: "#2e5a6b", BK: "#9a6a3a", DB: "#7a7a2e", BRZ: "#d9cf9a", OL: "#6f8f9a", OLS: "#8fa7ad", GB: "#a59060" };

function circle(lat: number, lon: number, km: number): GeoJSON.Feature<GeoJSON.Polygon> {
  const pts: [number, number][] = [];
  for (let i = 0; i <= 64; i++) {
    const a = (i / 64) * 2 * Math.PI;
    pts.push([lon + (km / (111.32 * Math.cos((lat * Math.PI) / 180))) * Math.cos(a), lat + (km / 110.57) * Math.sin(a)]);
  }
  return { type: "Feature", properties: {}, geometry: { type: "Polygon", coordinates: [pts] } };
}

function fillColor(mode: Mode): maplibregl.ExpressionSpecification | string {
  if (mode === "wynik")
    return ["case", ["==", ["get", "wynik"], null], "#c9c4b8",
      ["interpolate", ["linear"], ["get", "wynik"], ...SCORE_STOPS.flat()]] as unknown as maplibregl.ExpressionSpecification;
  if (mode === "drzewostan")
    return ["match", ["get", "gatunek_panujacy"], ...Object.entries(TREE_COLORS).flat(), "#b9b4a6"] as unknown as maplibregl.ExpressionSpecification;
  if (mode === "siedlisko")
    return ["match", ["slice", ["coalesce", ["get", "typ_siedliskowy"], "?"], 0, 1], "B", "#d8b46a", "L", "#6e9a5a", "O", "#5f8a9a", "#b9b4a6"] as unknown as maplibregl.ExpressionSpecification;
  return ["case", ["==", ["get", "opad_7d_mm"], null], "#c9c4b8",
    ["interpolate", ["linear"], ["get", "opad_7d_mm"], 0, "#f1ede4", 10, "#bcd3e3", 30, "#6c9cc2", 60, "#2d5f8f"]] as unknown as maplibregl.ExpressionSpecification;
}

export function MapView({ q, onOpen }: { q: Query; onOpen: (id: number) => void }) {
  const box = useRef<HTMLDivElement>(null);
  const map = useRef<maplibregl.Map | null>(null);
  const [ready, setReady] = useState(false);
  const [basemapOk, setBasemapOk] = useState(true);
  const [mode, setMode] = useState<Mode>("wynik");
  const [showProt, setShowProt] = useState(true);
  const [env, setEnv] = useState<Envelope | null>(null);
  const [err, setErr] = useState<string | null>(null);

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
      const m = new maplibregl.Map({ container: box.current, style, center: [q.lon, q.lat], zoom: 10, attributionControl: { compact: true } });
      m.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
      m.on("load", () => {
        m.addSource("lasy", { type: "geojson", data: { type: "FeatureCollection", features: [] } });
        m.addSource("ochrona", { type: "geojson", data: { type: "FeatureCollection", features: [] } });
        m.addSource("zasieg", { type: "geojson", data: { type: "FeatureCollection", features: [] } });
        m.addLayer({ id: "zasieg", type: "line", source: "zasieg", paint: { "line-color": "#2f4a2c", "line-dasharray": [2, 2], "line-width": 1.5 } });
        m.addLayer({ id: "lasy-fill", type: "fill", source: "lasy", paint: { "fill-color": fillColor("wynik"), "fill-opacity": 0.85 } });
        m.addLayer({ id: "lasy-line", type: "line", source: "lasy", paint: {
          "line-color": ["case", ["get", "rekomendowane"], "#24502a", "#7d7568"], "line-width": 0.8 } });
        m.addLayer({ id: "ochrona-fill", type: "fill", source: "ochrona", paint: {
          "fill-color": ["match", ["get", "rodzaj"], "park_narodowy", "#b0413e", "zakaz_wstepu", "#d97a1f", "#8a6fb0"], "fill-opacity": 0.18 } });
        m.addLayer({ id: "ochrona-line", type: "line", source: "ochrona", paint: {
          "line-color": ["match", ["get", "rodzaj"], "park_narodowy", "#b0413e", "zakaz_wstepu", "#d97a1f", "#8a6fb0"], "line-width": 2 } });
        m.on("click", "lasy-fill", (e) => { const id = e.features?.[0]?.properties?.id; if (id != null) onOpen(Number(id)); });
        m.on("mouseenter", "lasy-fill", () => (m.getCanvas().style.cursor = "pointer"));
        m.on("mouseleave", "lasy-fill", () => (m.getCanvas().style.cursor = ""));
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
    setErr(null);
    (m.getSource("zasieg") as maplibregl.GeoJSONSource).setData({ type: "FeatureCollection", features: [circle(q.lat, q.lon, q.radius_km)] });
    m.easeTo({ center: [q.lon, q.lat] });
    api.map(q).then((r) => { setEnv(r); (m.getSource("lasy") as maplibregl.GeoJSONSource).setData(r.geojson); })
      .catch((e) => setErr(String(e.message ?? e)));
    api.protection(q.dataset).then((g) => (m.getSource("ochrona") as maplibregl.GeoJSONSource).setData(g)).catch(() => {});
  }, [ready, q]);

  useEffect(() => { if (ready) map.current?.setPaintProperty("lasy-fill", "fill-color", fillColor(mode)); }, [ready, mode]);
  useEffect(() => {
    if (!ready) return;
    for (const id of ["ochrona-fill", "ochrona-line"]) map.current?.setLayoutProperty(id, "visibility", showProt ? "visible" : "none");
  }, [ready, showProt]);

  return (
    <section className="view view-map">
      <Warnings env={env} />
      {err && <ErrorBox error={err} />}
      {!basemapOk && <div className="banner banner-warn">Podkład mapowy niedostępny — widoczne tylko warstwy aplikacji.</div>}
      <div className="map-controls">
        <label>Warstwa{" "}
          <select value={mode} onChange={(e) => setMode(e.target.value as Mode)} data-testid="map-mode">
            <option value="wynik">wskaźnik rekomendacji</option>
            <option value="drzewostan">drzewostany (gatunek panujący)</option>
            <option value="siedlisko">siedliska (typ siedliskowy)</option>
            <option value="opad">opady z 7 dni</option>
          </select>
        </label>
        <label className="chk"><input type="checkbox" checked={showProt} onChange={(e) => setShowProt(e.target.checked)} /> ochrona przyrody i zakazy</label>
      </div>
      <div ref={box} className="map" data-testid="map" />
      <Legend mode={mode} />
      <Footer env={env} />
    </section>
  );
}

function Legend({ mode }: { mode: Mode }) {
  if (mode === "drzewostan")
    return <div className="legend">{Object.entries(TREE_COLORS).map(([k, c]) => <span key={k}><i style={{ background: c }} />{TREE_NAMES[k]}</span>)}</div>;
  if (mode === "siedlisko")
    return <div className="legend"><span><i style={{ background: "#d8b46a" }} />bory</span><span><i style={{ background: "#6e9a5a" }} />lasy</span><span><i style={{ background: "#5f8a9a" }} />olsy</span></div>;
  if (mode === "opad")
    return <div className="legend"><span><i style={{ background: "#f1ede4" }} />0 mm</span><span><i style={{ background: "#6c9cc2" }} />30</span><span><i style={{ background: "#2d5f8f" }} />60+ mm</span><span className="muted">komórka siatki ~10 km</span></div>;
  return (
    <div className="legend">
      {SCORE_STOPS.map(([v, c]) => <span key={v}><i style={{ background: c }} />{v}</span>)}
      <span><i style={{ background: "#c9c4b8" }} />brak danych</span>
      <span className="muted">wskaźnik rekomendacji 0–100</span>
    </div>
  );
}
