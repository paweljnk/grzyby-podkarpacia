import { Fragment, useEffect, useState } from "react";

/* Atlas służy do nauki. Nie ma tu rozpoznawania ze zdjęcia ani oceny jadalności okazu. */

interface Photo { id: number; url: string; ujecie: string; autor: string; licencja: string; licencja_url: string | null; zrodlo_url: string; podpis: string; adnotacje: { x: number; y: number; tekst: string }[] }
interface Species { id: string; nazwa_polska: string; nazwa_naukowa: string; status: string; status_uwagi?: string | null; grupa: string; cechy: Record<string, string>; zrodla: string[]; zdjecia: Record<string, Photo[] | null>; brakujace_ujecia: string[] }
interface Feature { cecha: string; ujecie: string | null; jadalny: string; sobowtor: string; waga: string; zrodla: string[] }
interface Pair { id: string; jadalny: string; sobowtor: string; kategoria_sobowtora: string; ryzyko_pomylki: string; skutek_pomylki: string; cechy: Feature[]; uwagi: string[]; zrodla: string[] }
interface Env { komunikat: string; wersja_robocza: boolean; atlas_nie_robi: string[] }

const UJ: Record<string, string> = { mlody: "młody owocnik", dojrzaly: "dojrzały owocnik", spod: "spód kapelusza", trzon: "trzon z podstawą", przekroj: "przekrój" };
const STATUS: Record<string, string> = { jadalny: "jadalny", niejadalny: "niejadalny", trujacy: "trujący", smiertelnie_trujacy: "śmiertelnie trujący", niepewny: "niejadalny / niepewna jadalność" };
const RISK: Record<string, string> = { wysokie: "wysokie", srednie: "średnie", niskie: "niskie" };
const CECHY: Record<string, string> = { kapelusz: "Kapelusz", hymenofor: "Spód kapelusza", trzon: "Trzon", miazsz: "Miąższ", siedlisko: "Siedlisko" };

async function getJson<T>(path: string): Promise<T> {
  const r = await fetch(path);
  if (!r.ok) throw new Error(`Błąd ${r.status}`);
  return r.json();
}

function useJson<T>(path: string) {
  const [d, setD] = useState<T | null>(null);
  const [e, setE] = useState<string | null>(null);
  useEffect(() => { setD(null); setE(null); getJson<T>(path).then(setD).catch((x) => setE(String(x.message ?? x))); }, [path]);
  return { d, e };
}

export function AtlasNotice({ env }: { env: Env | null }) {
  return (
    <>
      <div className="banner atlas-notice" role="note" data-testid="atlas-notice">
        {env?.komunikat ?? "Atlas służy do nauki. Nie zjadaj grzyba, którego nie rozpoznajesz ze 100% pewnością. W razie wątpliwości oddaj zbiór do sprawdzenia grzyboznawcy."}
      </div>
      {(env?.wersja_robocza ?? true) && <div className="banner banner-warn" data-testid="atlas-draft">Wersja robocza — treści i zdjęcia czekają na zatwierdzenie przez osobę z wiedzą mykologiczną.</div>}
    </>
  );
}

function PhotoBox({ photos, label }: { photos: Photo[] | null | undefined; label: string }) {
  if (!photos || !photos.length) return <div className="ph ph-missing" data-testid="photo-missing"><span>brak zdjęcia</span><small>{label}</small></div>;
  const p = photos[0];
  return (
    <figure className="ph">
      <div className="ph-img">
        <img src={p.url} alt={label} loading="lazy" />
        {p.adnotacje.map((a, i) => <span key={i} className="mark" style={{ left: `${a.x * 100}%`, top: `${a.y * 100}%` }} title={a.tekst}>{i + 1}</span>)}
      </div>
      <figcaption>
        {label}. <a href={p.zrodlo_url} target="_blank" rel="noreferrer">{p.podpis}</a>
        {p.adnotacje.length > 0 && <ol className="tiny">{p.adnotacje.map((a, i) => <li key={i}>{a.tekst}</li>)}</ol>}
      </figcaption>
    </figure>
  );
}

export function AtlasIndex({ go }: { go: (h: string) => void }) {
  const { d, e } = useJson<Env & { gatunki: { id: string; nazwa_polska: string; nazwa_naukowa: string; status: string; liczba_zdjec: number; brakujace_ujecia: string[] }[]; pary: { id: string; jadalny: string; sobowtor: string; ryzyko_pomylki: string; kategoria_sobowtora: string }[] }>("/api/atlas");
  const [saved, setSaved] = useState<string | null>(null);
  const name = (id: string) => d?.gatunki.find((g) => g.id === id)?.nazwa_polska ?? id;
  const saveOffline = async () => {
    setSaved("Zapisywanie…");
    try {
      try { await navigator.storage?.persist?.(); } catch { /* opcjonalne */ }
      const idx = await getJson<{ gatunki: { id: string }[]; pary: { id: string }[] }>("/api/atlas");
      const urls = ["/api/atlas/bezpieczenstwo", ...idx.gatunki.map((g) => `/api/atlas/gatunek/${g.id}`), ...idx.pary.map((p) => `/api/atlas/para/${p.id}`)];
      let imgs = 0;
      for (const u of urls) {
        const j = await getJson<{ gatunek?: Species; jadalny?: Species; sobowtor?: Species }>(u);
        for (const sp of [j.gatunek, j.jadalny, j.sobowtor]) {
          for (const list of Object.values(sp?.zdjecia ?? {})) for (const p of list ?? []) { await fetch(p.url); imgs++; }
        }
      }
      setSaved(`Zapisano w pamięci telefonu: ${urls.length + 1} stron atlasu, ${imgs} zdjęć.`);
    } catch (x) { setSaved(`Nie udało się zapisać: ${(x as Error).message}`); }
  };
  return (
    <section className="view pad" data-testid="atlas">
      <h2>Atlas</h2>
      <AtlasNotice env={d} />
      {e && <div className="banner banner-warn">{e}</div>}
      <button className="secondary" onClick={saveOffline} data-testid="atlas-offline">💾 Zapisz atlas offline</button>
      {saved && <p className="note small" data-testid="atlas-offline-status">{saved}</p>}
      <h3>Gatunki</h3>
      <ul className="atlas-list">
        {d?.gatunki.map((g) => (
          <li key={g.id}><button className="atlas-item" onClick={() => go(`#/atlas/gatunek/${g.id}`)} data-testid="atlas-species">
            <strong>{g.nazwa_polska}</strong> <i className="small">{g.nazwa_naukowa}</i>
            <span className={`st st-${g.status}`}>{STATUS[g.status]}</span>
            <span className="tiny muted">zdjęcia: {g.liczba_zdjec}; brak ujęć: {g.brakujace_ujecia.length}</span>
          </button></li>
        ))}
      </ul>
      <h3>Groźne sobowtóry</h3>
      <ul className="atlas-list">
        {d?.pary.map((p) => (
          <li key={p.id}><button className="atlas-item" onClick={() => go(`#/atlas/para/${p.id}`)} data-testid="atlas-pair">
            <strong>{name(p.jadalny)} ↔ {name(p.sobowtor)}</strong>
            <span className="tiny muted">sobowtór: {p.kategoria_sobowtora} · ryzyko pomyłki: {RISK[p.ryzyko_pomylki]}</span>
          </button></li>
        ))}
      </ul>
      <button className="secondary" onClick={() => go("#/atlas/bezpieczenstwo")} data-testid="atlas-safety">⚠️ Bezpieczny zbiór, mity, zatrucia, grzyboznawcy</button>
      {d && <><h3>Czego atlas nie robi</h3><ul className="reasons">{d.atlas_nie_robi.map((x, i) => <li key={i}>{x}</li>)}</ul></>}
    </section>
  );
}

export function AtlasSpecies({ id, go }: { id: string; go: (h: string) => void }) {
  const { d, e } = useJson<Env & { gatunek: Species; pary: Pair[] }>(`/api/atlas/gatunek/${id}`);
  const g = d?.gatunek;
  return (
    <section className="view pad">
      <button className="link" onClick={() => go("#/atlas")}>← atlas</button>
      <AtlasNotice env={d} />
      {e && <div className="banner banner-warn">{e}</div>}
      {g && (
        <>
          <h2>{g.nazwa_polska}</h2>
          <p><i>{g.nazwa_naukowa}</i> · <span className={`st st-${g.status}`}>{STATUS[g.status]}</span></p>
          {g.status_uwagi && <p className="note small">{g.status_uwagi}</p>}
          <div className="ph-grid">{Object.keys(UJ).map((u) => <PhotoBox key={u} photos={g.zdjecia[u]} label={UJ[u]} />)}</div>
          <dl className="facts">{Object.entries(g.cechy).map(([k, v]) => <Fragment key={k}><dt>{CECHY[k] ?? k}</dt><dd>{v}</dd></Fragment>)}</dl>
          <p className="muted tiny">Źródła: {g.zrodla.join(", ")} (do potwierdzenia przez mykologa).</p>
          {d!.pary.length > 0 && <h3>Z czym można pomylić</h3>}
          {d!.pary.map((p) => <button key={p.id} className="secondary" onClick={() => go(`#/atlas/para/${p.id}`)}>{p.id.replace("_", " ↔ ")}</button>)}
        </>
      )}
    </section>
  );
}

export function AtlasPair({ id, go }: { id: string; go: (h: string) => void }) {
  const { d, e } = useJson<Env & { para: Pair; jadalny: Species; sobowtor: Species; ostrzezenie: string }>(`/api/atlas/para/${id}`);
  return (
    <section className="view pad" data-testid="atlas-pair-view">
      <button className="link" onClick={() => go("#/atlas")}>← atlas</button>
      <AtlasNotice env={d} />
      {e && <div className="banner banner-warn">{e}</div>}
      {d && (
        <>
          <h2>{d.jadalny.nazwa_polska} ↔ {d.sobowtor.nazwa_polska}</h2>
          <p className="small">Sobowtór: <strong>{d.para.kategoria_sobowtora}</strong>. Ryzyko pomyłki: <strong>{RISK[d.para.ryzyko_pomylki]}</strong>. Skutek: {d.para.skutek_pomylki}</p>
          <div className="banner banner-warn" data-testid="single-feature-warning">{d.ostrzezenie}</div>
          <table className="pair-table" data-testid="pair-table">
            <thead><tr><th>Cecha</th><th>{d.jadalny.nazwa_polska}</th><th>{d.sobowtor.nazwa_polska}</th></tr></thead>
            <tbody>
              {d.para.cechy.map((c) => (
                <tr key={c.cecha} className={`w-${c.waga}`}>
                  <th>{c.cecha}<br /><span className="tiny muted">{c.waga === "kluczowa" ? "cecha kluczowa" : c.waga === "pomocnicza" ? "pomocnicza" : "słaba"}</span></th>
                  <td>{c.jadalny}</td><td>{c.sobowtor}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <h3>Zdjęcia obok siebie</h3>
          {d.para.cechy.filter((c) => c.ujecie).map((c) => (
            <div key={c.cecha} className="side">
              <p className="small"><strong>{c.cecha}</strong></p>
              <div className="side-grid">
                <PhotoBox photos={d.jadalny.zdjecia[c.ujecie!]} label={`${d.jadalny.nazwa_polska}: ${UJ[c.ujecie!]}`} />
                <PhotoBox photos={d.sobowtor.zdjecia[c.ujecie!]} label={`${d.sobowtor.nazwa_polska}: ${UJ[c.ujecie!]}`} />
              </div>
            </div>
          ))}
          {d.para.uwagi.length > 0 && <ul className="reasons">{d.para.uwagi.map((u, i) => <li key={i}>{u}</li>)}</ul>}
          <p className="muted tiny">Źródła cech: {d.para.zrodla.join(", ")} (do potwierdzenia przez mykologa).</p>
        </>
      )}
    </section>
  );
}

interface Safety extends Env {
  zasady_zbioru: { tekst: string; zrodla: string[] }[];
  mity: { mit: string; prawda: string; zrodla: string[]; uwaga_zrodla?: string }[];
  zatrucie: { kroki: string[]; telefony: { nazwa: string; numer: string; status_numeru: string }[]; uwaga: string };
  punkty_grzyboznawcze: { data_listy: string; kompletnosc: string; uwaga: string; punkty: { nazwa: string; adres: string | null; telefon: string | null; uwagi: string }[] };
  zrodla: Record<string, { opis: string; url: string; sprawdzono: string }>;
}

export function AtlasSafety({ go }: { go: (h: string) => void }) {
  const { d, e } = useJson<Safety>("/api/atlas/bezpieczenstwo");
  const src = (keys: string[]) => keys.map((k) => d?.zrodla[k]).filter(Boolean).map((s, i) => <a key={i} href={s!.url} target="_blank" rel="noreferrer" className="tiny"> [{s!.opis}]</a>);
  return (
    <section className="view pad" data-testid="atlas-safety-view">
      <button className="link" onClick={() => go("#/atlas")}>← atlas</button>
      <AtlasNotice env={d} />
      {e && <div className="banner banner-warn">{e}</div>}
      {d && (
        <>
          <h2>Podejrzenie zatrucia</h2>
          <div className="poison">
            {d.zatrucie.telefony.map((t) => (
              <a key={t.numer} className={`call ${t.numer === "112" ? "call-112" : ""}`} href={`tel:${t.numer.replace(/\s/g, "")}`}>
                📞 {t.numer} <span className="small">{t.nazwa}{t.status_numeru !== "urzędowy" ? " (numer do potwierdzenia)" : ""}</span>
              </a>
            ))}
            <ul className="reasons">{d.zatrucie.kroki.map((k, i) => <li key={i}>{k}</li>)}</ul>
            <p className="muted tiny">{d.zatrucie.uwaga}</p>
          </div>
          <h3>Bezpłatne sprawdzenie grzybów (sanepid)</h3>
          <p className="note small">{d.punkty_grzyboznawcze.uwaga} Lista z dnia {d.punkty_grzyboznawcze.data_listy} — {d.punkty_grzyboznawcze.kompletnosc === "niepelna" ? "NIEPEŁNA" : "pełna"}.</p>
          <ul className="reasons">
            {d.punkty_grzyboznawcze.punkty.map((p) => <li key={p.nazwa}><strong>{p.nazwa}</strong>{p.adres && `, ${p.adres}`}{p.telefon && <>, tel. <a href={`tel:${p.telefon.split(" wew")[0].replace(/\s/g, "")}`}>{p.telefon}</a></>}. {p.uwagi}</li>)}
          </ul>
          <h3>Zasady bezpiecznego zbioru</h3>
          <ul className="reasons">{d.zasady_zbioru.map((z, i) => <li key={i}>{z.tekst}{src(z.zrodla)}</li>)}</ul>
          <h3>Mity — nie wierz w nie</h3>
          <ul className="myths" data-testid="myths">
            {d.mity.map((m, i) => <li key={i}><strong>Mit:</strong> {m.mit}<br /><strong>Prawda:</strong> {m.prawda}{src(m.zrodla)}{m.uwaga_zrodla && <span className="tiny muted"> ({m.uwaga_zrodla})</span>}</li>)}
          </ul>
        </>
      )}
    </section>
  );
}
