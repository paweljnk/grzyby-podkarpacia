import { useEffect, useState } from "react";
import { api, geocode, type Query } from "./api";
import type { Envelope, MonthResp, PlaceCard, RankingResp, Scored, SpeciesItem, WeekResp } from "./types";
import { BIO, Breakdown, Conditions, ErrorBox, Footer, Gates, Loading, QUALITY, ScoreBadge, TREE_NAMES, Warnings, scoreColor } from "./ui";

function useLoad<T>(fn: () => Promise<T>, deps: unknown[]) {
  const [data, setData] = useState<T | null>(null);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => {
    let alive = true;
    setData(null); setErr(null);
    fn().then((d) => alive && setData(d)).catch((e) => alive && setErr(String(e.message ?? e)));
    return () => { alive = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
  return { data, err };
}

const fmtDay = (iso: string) => new Date(iso + "T12:00:00").toLocaleDateString("pl-PL", { weekday: "short", day: "numeric", month: "numeric" });

// ------------------------------------------------------------------ Wyszukiwanie
export function SearchView({ q, species, setQ, go }: { q: Query; species: SpeciesItem[]; setQ: (p: Partial<Query>) => void; go: (h: string) => void }) {
  const [text, setText] = useState("");
  const [hits, setHits] = useState<{ name: string; lat: number; lon: number }[]>([]);
  const [msg, setMsg] = useState<string | null>(null);
  const search = async () => {
    setMsg(null);
    try { const h = await geocode(text); setHits(h); if (!h.length) setMsg("Nie znaleziono miejscowości na Podkarpaciu."); }
    catch (e) { setMsg(String((e as Error).message)); }
  };
  const gps = () => {
    if (!navigator.geolocation) return setMsg("Urządzenie nie udostępnia lokalizacji.");
    navigator.geolocation.getCurrentPosition(
      (p) => { setQ({ lat: +p.coords.latitude.toFixed(4), lon: +p.coords.longitude.toFixed(4) }); setMsg("Ustawiono Twoją lokalizację."); },
      () => setMsg("Brak zgody na lokalizację lub brak sygnału GPS."), { enableHighAccuracy: false, timeout: 10000 });
  };
  return (
    <section className="view pad">
      <h2>Szukaj</h2>
      <label className="field">Gatunek
        <select value={q.species} onChange={(e) => setQ({ species: e.target.value })} data-testid="species-select">
          {species.map((s) => <option key={s.id} value={s.id}>{s.nazwa_polska} ({s.nazwa_naukowa})</option>)}
        </select>
      </label>
      <label className="field">Miejscowość
        <div className="row">
          <input value={text} onChange={(e) => setText(e.target.value)} placeholder="np. Lesko" onKeyDown={(e) => e.key === "Enter" && search()} />
          <button onClick={search} disabled={text.trim().length < 3}>Szukaj</button>
        </div>
      </label>
      <p className="muted small">Wyszukiwanie: Nominatim © OpenStreetMap contributors (maks. 1 zapytanie na sekundę).</p>
      {hits.map((h) => (
        <button key={h.name} className="hit" onClick={() => { setQ({ lat: +h.lat.toFixed(4), lon: +h.lon.toFixed(4) }); setHits([]); setMsg(`Wybrano: ${h.name.split(",")[0]}`); }}>
          {h.name}
        </button>
      ))}
      <button className="secondary" onClick={gps}>📍 Użyj mojej lokalizacji</button>
      <label className="field">Promień: {q.radius_km} km
        <input type="range" min={5} max={60} step={5} value={q.radius_km} onChange={(e) => setQ({ radius_km: +e.target.value })} />
      </label>
      <label className="field">Dzień
        <input type="date" value={q.date} onChange={(e) => e.target.value && setQ({ date: e.target.value })} />
      </label>
      <p className="muted small">Punkt: {q.lat.toFixed(3)}, {q.lon.toFixed(3)}</p>
      {msg && <p className="note">{msg}</p>}
      <button onClick={() => go("#/ranking")} data-testid="show-ranking">Pokaż ranking</button>
    </section>
  );
}

// ------------------------------------------------------------------ Ranking
export function RankingView({ q, setQ, open, compareIds, toggleCompare }: {
  q: Query; setQ: (p: Partial<Query>) => void; open: (id: number) => void; compareIds: number[]; toggleCompare: (id: number) => void;
}) {
  const { data, err } = useLoad<RankingResp>(() => api.ranking(q), [q]);
  return (
    <section className="view">
      <div className="pad">
        <CalendarToggle q={q} setQ={setQ} />
        <Warnings env={data} />
        {err && <ErrorBox error={err} />}
        {!data && !err && <Loading />}
        {data && (
          <p className="muted small">
            Oceniono {data.liczba_ocenionych} miejsc w promieniu {q.radius_km} km · dzień {fmtDay(q.date)} ·
            wykluczone przez bramki (siedlisko, susza, zakaz): {data.wykluczone}
          </p>
        )}
        {data && data.miejsca.length === 0 && <p className="note">Brak miejsc spełniających warunki.</p>}
      </div>
      <ol className="rank-list" data-testid="ranking-list">
        {data?.miejsca.map((m, i) => (
          <li key={m.id} className="rank-item">
            <button className="rank-main" onClick={() => open(m.id)} data-testid="ranking-item">
              <span className="rank-pos">{i + 1}</span>
              <ScoreBadge value={m.wynik} excluded={!m.rekomendowane} />
              <span className="rank-text">
                <strong>{m.nazwa}</strong>
                <span className="muted small">
                  {m.odleglosc_km != null && <>{m.odleglosc_km} km (linia prosta) · </>}
                  {m.gatunek_panujacy ? TREE_NAMES[m.gatunek_panujacy] ?? m.gatunek_panujacy : "drzewostan: brak"}
                  {m.typ_siedliskowy && <> · {m.typ_siedliskowy}</>}{m.zarzad === "poza_LP" && <> · las poza LP{m.wlasnosc ? ` (${m.wlasnosc})` : ""}</>}
                </span>
                <Conditions v={m.warunki} lo={m.warunki_min} hi={m.warunki_max} pewnosc={m.pewnosc} opis={m.pewnosc_opis} />
                <Breakdown A={m.A} B={m.B} C={m.C} D={m.D} calendar={q.calendar} />
              </span>
            </button>
            <label className="chk small cmp"><input type="checkbox" checked={compareIds.includes(m.id)}
              disabled={!compareIds.includes(m.id) && compareIds.length >= 4} onChange={() => toggleCompare(m.id)} /> porównaj</label>
          </li>
        ))}
      </ol>
      <Footer env={data} />
    </section>
  );
}

export function CalendarToggle({ q, setQ }: { q: Query; setQ: (p: Partial<Query>) => void }) {
  return (
    <div className="toggle" role="group" aria-label="Kalendarz księżycowy i biodynamiczny">
      <button className={!q.calendar ? "on" : ""} aria-pressed={!q.calendar} onClick={() => setQ({ calendar: false })} data-testid="calendar-off">bez kalendarza</button>
      <button className={q.calendar ? "on" : ""} aria-pressed={q.calendar} onClick={() => setQ({ calendar: true })} data-testid="calendar-on">z kalendarzem</button>
      <span className="muted small">kalendarz: eksperymentalny, ±3 pkt</span>
    </div>
  );
}

// ------------------------------------------------------------------ Karta miejsca
export function PlaceView({ id, q, setQ, go, compareIds, toggleCompare, onBack }: {
  id: number; q: Query; setQ: (p: Partial<Query>) => void; go: (h: string) => void; compareIds: number[]; toggleCompare: (id: number) => void;
  onBack?: () => void;   // osadzona w panelu mapy: powrót do listy bez zmiany ekranu
}) {
  const { data, err } = useLoad<Envelope & { miejsce: PlaceCard }>(() => api.place(id, q), [id, q]);
  const m = data?.miejsce;
  return (
    <section className={onBack ? "view place-embedded" : "view pad"} data-testid="place-card">
      {onBack
        ? <button className="link back-to-list" onClick={onBack} data-testid="place-back">‹ Wróć do listy</button>
        : <button className="link" onClick={() => go("#/ranking")}>← ranking</button>}
      <Warnings env={data} />
      {err && <ErrorBox error={err} />}
      {!data && !err && <Loading />}
      {m && (
        <>
          <header className="place-head">
            <ScoreBadge value={m.wynik} excluded={!m.rekomendowane} size="lg" />
            <div>
              <h2>{m.nazwa}</h2>
              <p className="muted small">wskaźnik warunków 0–100 (nie prawdopodobieństwo)</p>
              <Conditions v={m.warunki} lo={m.warunki_min} hi={m.warunki_max} pewnosc={m.pewnosc} opis={m.pewnosc_opis} />
              {!m.rekomendowane && <p className="excluded-note">Miejsce nie trafia do rekomendacji wypraw.</p>}
            </div>
          </header>
          <CalendarToggle q={q} setQ={setQ} />
          <Breakdown A={m.A} B={m.B} C={m.C} D={m.D} calendar={q.calendar} />
          <Gates gates={m.bramki} />
          <h3>Uzasadnienie</h3>
          <ul className="reasons" data-testid="reasons">{m.uzasadnienie.map((r, i) => <li key={i}>{r}</li>)}</ul>

          <WeekPanel id={id} q={q} />

          <h3>Dostęp i ochrona</h3>
          <ul className="reasons">
            {m.dostep.zakaz_zbioru && <li className="bad">Zbiór grzybów co do zasady zakazany (park narodowy).</li>}
            {m.dostep.zakaz_wstepu && <li className="bad">Obowiązuje zakaz wstępu.</li>}
            {m.dostep.uwagi.map((u, i) => <li key={i}>{u}</li>)}
            <li>{m.dostep.las_prywatny_uwaga}</li>
          </ul>

          <h3>Dojazd</h3>
          <p>{m.dojazd.odleglosc_km != null ? `${m.dojazd.odleglosc_km} km. ` : ""}{m.dojazd.opis}</p>
          {m.dojazd.nachylenie_sr_deg != null && <p className="small">Średnie nachylenie terenu: {m.dojazd.nachylenie_sr_deg.toFixed(0)}°.</p>}

          <h3>Dane o miejscu — źródła</h3>
          <table className="attr-table" data-testid="attributes">
            <thead><tr><th>Atrybut</th><th>Wartość</th><th>Źródło / data</th></tr></thead>
            <tbody>
              {m.atrybuty.map((a) => (
                <tr key={a.atrybut} className={`attr-${a.oznaczenie === "źródłowa" ? "src" : a.oznaczenie === "model" ? "model" : "none"}`}>
                  <td>{a.atrybut}</td>
                  <td>{a.wartosc ?? "brak danych"}</td>
                  <td><span className="tag-k">{a.oznaczenie === "źródłowa" ? "informacja źródłowa" : a.oznaczenie === "model" ? "wynik modelu" : "brak danych"}</span>
                    {a.zrodlo && <><br /><span className="tiny muted">{a.zrodlo}{a.data ? `, ${a.data}` : ""}</span></>}</td>
                </tr>
              ))}
            </tbody>
          </table>

          <h3>Drzewostan i siedlisko</h3>
          <dl className="facts">
            <dt>Skład</dt><dd>{m.drzewostan.udzial_gatunkow ? Object.entries(m.drzewostan.udzial_gatunkow).map(([k, v]) => `${TREE_NAMES[k] ?? k} ${Math.round(v * 100)}%`).join(", ") : `gatunek panujący: ${m.drzewostan.gatunek_panujacy ? TREE_NAMES[m.drzewostan.gatunek_panujacy] ?? m.drzewostan.gatunek_panujacy : "brak"} (udziały: brak danych)`}</dd>
            <dt>Wiek</dt><dd>{m.drzewostan.wiek ?? "brak"} lat</dd>
            <dt>Typ siedliskowy</dt><dd>{m.drzewostan.typ_siedliskowy ?? "brak"}</dd>
            <dt>Gleba</dt><dd>{m.drzewostan.gleba ?? "brak danych"}</dd>
            <dt>Teren</dt><dd>{m.teren.wys_sr_m != null ? `${Math.round(m.teren.wys_sr_m)} m n.p.m., ekspozycja ${m.teren.ekspozycja ?? "brak"}` : "brak"}</dd>
          </dl>
          <p className="muted small">{m.teren.uwaga} Pochodzenie: {Object.entries(m.drzewostan.pochodzenie).map(([k, v]) => `${k}: ${v}`).join("; ")}.</p>

          <h3>Pogoda (komórka siatki)</h3>
          <dl className="facts">
            <dt>Opad 3/7/14/30 dni</dt><dd>{["3", "7", "14", "30"].map((k) => m.pogoda.opad_mm[k] ?? "brak").join(" / ")} mm</dd>
            <dt>Śr. temp. 7 dni</dt><dd>{m.pogoda.temp_sr_7_c ?? "brak"} °C</dd>
            <dt>Bilans 14 dni</dt><dd>{m.pogoda.bilans_14_mm ?? "brak"} mm (opad − ET₀)</dd>
            <dt>Przymrozki 7 dni</dt><dd>{m.pogoda.przymrozki_7 ?? "brak"}</dd>
            <dt>Dane</dt><dd>{Object.entries(m.pogoda.sklad_typow).map(([k, v]) => `${k}: ${v} d`).join(", ") || "brak"}</dd>
          </dl>
          <p className="muted small">{m.pogoda.uwaga}</p>

          <h3>Księżyc i biodynamika <span className="tag">tradycja · eksperymentalne</span></h3>
          <p>{m.kalendarz.faza_opis} ({Math.round(m.kalendarz.oswietlenie * 100)}% tarczy) · dzień {BIO[m.kalendarz.typ_biodynamiczny]}</p>
          <p className="muted small">{m.kalendarz.uwaga}</p>

          <div className="row gap">
            <button className="secondary" onClick={() => go(`#/kalendarz/${id}`)}>Kalendarz miesięczny</button>
            <button className="secondary" onClick={() => toggleCompare(id)}>{compareIds.includes(id) ? "Usuń z porównania" : "Dodaj do porównania"}</button>
          </div>
        </>
      )}
      <Footer env={data} />
    </section>
  );
}

function WeekPanel({ id, q }: { id: number; q: Query }) {
  const { data, err } = useLoad<WeekResp>(() => api.week(id, q), [id, q]);
  return (
    <div className="week" data-testid="week">
      <h3>Jechać dziś czy poczekać?</h3>
      {err && <ErrorBox error={err} />}
      {!data && !err && <Loading />}
      {data && (
        <>
          <p className={`verdict verdict-${data.werdykt.decyzja}`} data-testid="verdict">{data.werdykt.opis}</p>
          <div className="week-grid">
            {data.dni.map((d) => (
              <details key={d.data} className="week-day">
                <summary>
                  <span className="small">{fmtDay(d.data)}</span>
                  <span className="bar" style={{ height: `${Math.max(4, (d.wynik ?? 0) * 0.6)}px`, background: scoreColor(d.wynik), opacity: d.rekomendowane ? 1 : 0.4 }} />
                  <span className="small">{d.wynik == null ? "—" : Math.round(d.wynik)}</span>
                  {d.typy_danych.prognoza ? <span className="tiny muted">progn.</span> : null}
                </summary>
                <ul className="tiny">{[...d.bramki, ...d.powody].map((p, i) => <li key={i}>{p}</li>)}</ul>
              </details>
            ))}
          </div>
          <p className="muted small">{data.werdykt.uwaga} Dotknij dzień, aby zobaczyć powody.</p>
        </>
      )}
    </div>
  );
}

// ------------------------------------------------------------------ Kalendarz miesięczny
export function MonthView({ q, placeId, go }: { q: Query; placeId?: number; go: (h: string) => void }) {
  const [month, setMonth] = useState(q.date.slice(0, 7));
  const { data, err } = useLoad<MonthResp>(() => api.month(q, month, placeId), [q, month, placeId]);
  const shift = (k: number) => { const [y, m] = month.split("-").map(Number); const d = new Date(y, m - 1 + k, 1); setMonth(`${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`); };
  const first = data ? (new Date(data.dni[0].data + "T12:00:00").getDay() + 6) % 7 : 0;
  const moon: Record<string, string> = { now: "🌑", sierp_przybywajacy: "🌒", pierwsza_kwadra: "🌓", garb_przybywajacy: "🌔", pelnia: "🌕", garb_ubywajacy: "🌖", ostatnia_kwadra: "🌗", sierp_ubywajacy: "🌘" };
  return (
    <section className="view pad">
      {placeId && <button className="link" onClick={() => go(`#/miejsce/${placeId}`)}>← karta miejsca</button>}
      <h2>Kalendarz {placeId ? "miejsca" : "regionu"}</h2>
      <div className="row gap"><button className="secondary" onClick={() => shift(-1)}>‹</button><strong>{month}</strong><button className="secondary" onClick={() => shift(1)}>›</button></div>
      <Warnings env={data} />
      {err && <ErrorBox error={err} />}
      {!data && !err && <Loading />}
      {!placeId && <p className="note small">Wybierz miejsce w rankingu, aby zobaczyć wskaźnik i pogodę dla każdego dnia.</p>}
      {data && (
        <div className="month" data-testid="month">
          {["pn", "wt", "śr", "cz", "pt", "so", "nd"].map((d) => <div key={d} className="mh">{d}</div>)}
          {Array.from({ length: first }).map((_, i) => <div key={"e" + i} />)}
          {data.dni.map((d) => (
            <div key={d.data} className="md" style={{ borderColor: scoreColor(d.wynik) }} title={`${d.faza_opis}; dzień ${BIO[d.typ_biodynamiczny]}`}>
              <span className="md-day">{+d.data.slice(8)}</span>
              <span className="md-moon" aria-label={d.faza_opis}>{moon[d.faza]}</span>
              {d.wynik != null && <span className="md-score" style={{ background: scoreColor(d.wynik) }}>{Math.round(q.calendar && d.wynik_z_kalendarzem != null ? d.wynik_z_kalendarzem : d.wynik)}</span>}
              {d.opad_mm != null && <span className="tiny">{d.opad_mm} mm</span>}
              <span className="tiny muted">{BIO[d.typ_biodynamiczny].slice(0, 4)}</span>
            </div>
          ))}
        </div>
      )}
      {data && <p className="muted small">{data.uwaga} Wskaźnik bez danych pogodowych dla dnia nie jest liczony.</p>}
      <Footer env={data} />
    </section>
  );
}

// ------------------------------------------------------------------ Porównanie
export function CompareView({ q, ids, open, clear }: { q: Query; ids: number[]; open: (id: number) => void; clear: () => void }) {
  const enough = ids.length >= 2;
  const { data, err } = useLoad<Envelope & { miejsca: Scored[] }>(() => (enough ? api.compare(ids, q) : Promise.reject(new Error("Zaznacz 2–4 miejsca w rankingu."))), [ids, q]);
  return (
    <section className="view pad">
      <h2>Porównanie lasów</h2>
      <Warnings env={data} />
      {err && <p className="note">{err}</p>}
      {data && (
        <div className="cmp-table" role="table">
          {data.miejsca.map((m) => (
            <button key={m.id} className="cmp-col" onClick={() => open(m.id)}>
              <ScoreBadge value={m.wynik} excluded={!m.rekomendowane} />
              <strong className="small">{m.nazwa}</strong>
              <span className="small">A {m.A.wynik ?? "—"} · B {m.B.wynik ?? "—"}</span>
              <span className="small">C {m.C.toFixed(1)} · D {q.calendar ? m.D.toFixed(1) : "wył."}</span>
              <span className="small">jakość: {QUALITY[m.jakosc]}</span>
              <span className="tiny">{m.bramki.map((g) => g.opis).join(" ")}</span>
            </button>
          ))}
        </div>
      )}
      {ids.length > 0 && <button className="link" onClick={clear}>Wyczyść porównanie</button>}
      <Footer env={data} />
    </section>
  );
}
