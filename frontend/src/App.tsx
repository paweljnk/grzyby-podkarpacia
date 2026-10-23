import { useCallback, useEffect, useState } from "react";
import { api, type Query } from "./api";
import { MapView } from "./MapView";
import type { Dataset, SpeciesItem } from "./types";
import { icons } from "./icons";
import { KatalogSpecies, KatalogView, KluczView } from "./katalog";
import { AtlasIndex, AtlasPair, AtlasSafety, AtlasSpecies } from "./atlas";
import { CompareView, MonthView, PlaceView, RankingView, SearchView } from "./views";

const store = {
  get<T>(k: string, d: T): T { try { const v = localStorage.getItem(k); return v ? (JSON.parse(v) as T) : d; } catch { return d; } },
  set(k: string, v: unknown) { try { localStorage.setItem(k, JSON.stringify(v)); } catch { /* tryb prywatny */ } },
};

function todayWarsaw(): string {
  return new Intl.DateTimeFormat("sv-SE", { timeZone: "Europe/Warsaw" }).format(new Date());
}

const DEFAULT: Query = { species: "boletus_edulis", lat: 49.33, lon: 22.28, radius_km: 25, date: todayWarsaw(), calendar: false, dataset: "real" };

function useHash() {
  const [h, setH] = useState(location.hash || "#/mapa");
  useEffect(() => { const f = () => setH(location.hash || "#/mapa"); addEventListener("hashchange", f); return () => removeEventListener("hashchange", f); }, []);
  return h;
}

export default function App() {
  const hash = useHash();
  const [q, setQState] = useState<Query>(() => ({ ...DEFAULT, ...store.get<Partial<Query>>("query", {}), date: todayWarsaw() }));
  const [species, setSpecies] = useState<SpeciesItem[]>([]);
  const [compareIds, setCompare] = useState<number[]>(() => store.get("compare", []));
  const [realEmpty, setRealEmpty] = useState(false);

  const setQ = useCallback((p: Partial<Query>) => setQState((old) => { const n = { ...old, ...p }; store.set("query", { ...n, date: undefined }); return n; }), []);
  const go = (h: string) => { location.hash = h; };
  const open = (id: number) => go(`#/miejsce/${id}`);
  const toggleCompare = (id: number) => setCompare((c) => { const n = c.includes(id) ? c.filter((x) => x !== id) : [...c, id].slice(-4); store.set("compare", n); return n; });

  useEffect(() => { api.species().then(setSpecies).catch(() => setSpecies([])); }, []);
  useEffect(() => {
    api.ranking({ ...q, dataset: "real", radius_km: 1 }).then((r) => setRealEmpty(r.dane.wydzielen === 0)).catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  useEffect(() => { setCompare([]); store.set("compare", []); }, [q.dataset]);

  const [, route, arg, arg2] = hash.split("/");
  let view;
  if (route === "atlas") {
    view = arg === "katalog" && arg2 ? <KatalogSpecies id={arg2} go={go} />
      : arg === "katalog" ? <KatalogView go={go} />
      : arg === "oznacz" ? <KluczView go={go} />
      : arg === "gatunek" && arg2 ? <AtlasSpecies id={arg2} go={go} />
      : arg === "para" && arg2 ? <AtlasPair id={arg2} go={go} />
      : arg === "bezpieczenstwo" ? <AtlasSafety go={go} />
      : <AtlasIndex go={go} />;
  } else if (route === "miejsce" && arg) view = <PlaceView id={+arg} q={q} setQ={setQ} go={go} compareIds={compareIds} toggleCompare={toggleCompare} />;
  else if (route === "ranking") view = <RankingView q={q} setQ={setQ} open={open} compareIds={compareIds} toggleCompare={toggleCompare} />;
  else if (route === "szukaj") view = <SearchView q={q} species={species} setQ={setQ} go={go} />;
  else if (route === "kalendarz") view = <MonthView q={q} placeId={arg ? +arg : undefined} go={go} />;
  else if (route === "porownanie") view = <CompareView q={q} ids={compareIds} open={open} clear={() => { setCompare([]); store.set("compare", []); }} />;
  else view = null;          // mapa jest zawsze zamontowana (niżej) — zachowuje widok i dane między zakładkami
  const isMap = view === null;

  const sp = species.find((s) => s.id === q.species);
  return (
    <div className={`app${!route || route === "mapa" ? " app-map" : ""}`}>
      <header className="top">
        <h1><span className="logo" aria-hidden>{icons.grzyb}</span>Grzyby Podkarpacia</h1>
        <div className="top-row">
          <select aria-label="Gatunek" value={q.species} onChange={(e) => setQ({ species: e.target.value })} data-testid="species-top">
            {species.map((s) => <option key={s.id} value={s.id}>{s.nazwa_polska}</option>)}
          </select>
          <input aria-label="Dzień" type="date" value={q.date} onChange={(e) => e.target.value && setQ({ date: e.target.value })} />
          <select aria-label="Zbiór danych" value={q.dataset} onChange={(e) => setQ({ dataset: e.target.value as Dataset })} data-testid="dataset">
            <option value="real">dane rzeczywiste</option>
            <option value="demo">dane demo</option>
          </select>
        </div>
        {sp && <p className="tiny sp-sci"><i>{sp.nazwa_naukowa}</i>{sp.weryfikacja === "wersja_robocza" && " · reguły gatunku: wersja robocza (niezatwierdzona przez mykologa)"}</p>}
        {realEmpty && q.dataset === "real" && route !== "atlas" && (
          <div className="banner banner-warn" role="status">
            Brak rzeczywistych danych o drzewostanach w tym wdrożeniu.{" "}
            <button className="link" onClick={() => setQ({ dataset: "demo" })} data-testid="use-demo">Pokaż dane demonstracyjne</button>
          </div>
        )}
      </header>
      <main>
        <div className="map-keep" style={{ display: isMap ? "flex" : "none" }}>
          <MapView q={q} setQ={setQ} go={go} visible={isMap} compareIds={compareIds} toggleCompare={toggleCompare} />
        </div>
        {view}
      </main>
      <nav className="tabs" aria-label="Nawigacja">
        {[["#/mapa", "Mapa", "mapa"], ["#/szukaj", "Szukaj", "szukaj"], ["#/ranking", "Ranking", "ranking"], ["#/kalendarz", "Kalendarz", "kalendarz"], ["#/porownanie", "Porównaj", "porownanie"], ["#/atlas", "Atlas", "atlas"]].map(([h, label, ic]) => (
          <a key={h} href={h} className={hash.startsWith(h) ? "active" : ""} data-testid={`tab-${h.slice(2)}`}>
            <span className="tab-ic" aria-hidden>{icons[ic]}{ic === "porownanie" && compareIds.length > 0 && <b className="badge">{compareIds.length}</b>}</span>{label}
          </a>
        ))}
      </nav>
    </div>
  );
}
