import { useEffect, useMemo, useRef, useState } from "react";

/* Katalog gatunków (przeglądanie) i „Pomóż oznaczyć”. Zdjęcie użytkownika zostaje w telefonie — nie jest wysyłane
   ani analizowane; służy tylko do porównania obok zdjęć z katalogu. Aplikacja nie ocenia jadalności. */

interface Item {
  id: string; nazwa_naukowa: string; nazwa_polska: string | null; rodzaj: string | null; rodzina: string | null;
  obserwacje_pl: number | null; obserwacje_woj: number | null; zdjecie_miniatura: string | null; zdjecie_autor: string | null;
  zdjecie_licencja: string | null; cechy: Record<string, string[]>; siedlisko: Record<string, string[]>;
}
interface Detail extends Item {
  nazwy_polskie: string[]; rzad: string | null; klasa: string | null; wiki_url: string | null; wiki_tytul: string | null;
  opis_wstep: string | null; opis_budowa: string | null; opis_wystepowanie: string | null; opis_podobne: string | null; opis_ochrona: string | null;
  zdjecie_url: string | null; zdjecie_strona: string | null; zdjecie_licencja_url: string | null; pobrano_utc: string | null;
  cechy_opis: Record<string, string[]>; ostrzezenie_rodzaj: boolean;
}
interface Src { nazwa: string; opis: string; licencja: string }
interface ListResp { uwaga: string; zrodla: Src[]; pobrano_utc: string | null; razem: number; rodziny: { rodzina: string; liczba: number }[]; gatunki: Item[] }
interface Question { id: string; pytanie: string; wiele: boolean; odpowiedzi: { id: string; etykieta: string }[] }
interface Hit extends Item { punkty: number; zgodne: string[]; niezgodne: string[]; brak_danych: string[]; ostrzezenie_rodzaj: boolean }
interface KeyResp { uwaga: string; pytania: Question[]; wyniki: Hit[]; ostrzezenia: string[] }

async function getJson<T>(path: string): Promise<T> {
  const r = await fetch(path);
  if (!r.ok) throw new Error(r.status === 404 ? "Nie znaleziono" : `Błąd ${r.status}`);
  return r.json();
}

const name = (s: Item) => s.nazwa_polska ?? s.nazwa_naukowa;

function Thumb({ s, big = false }: { s: Item; big?: boolean }) {
  return s.zdjecie_miniatura
    ? <img className={big ? "kt-img kt-img-big" : "kt-img"} src={s.zdjecie_miniatura} alt={name(s)} loading="lazy" />
    : <div className={`kt-img kt-noimg${big ? " kt-img-big" : ""}`}><span>brak zdjęcia z wolną licencją</span></div>;
}

function Warn({ text }: { text: string }) {
  return <div className="banner banner-warn" role="note" data-testid="katalog-uwaga">{text}</div>;
}

// ------------------------------------------------------------------ przeglądanie
export function KatalogView({ go }: { go: (h: string) => void }) {
  const [q, setQ] = useState("");
  const [fam, setFam] = useState("");
  const [sort, setSort] = useState("woj");
  const [d, setD] = useState<ListResp | null>(null);
  const [more, setMore] = useState<Item[]>([]);
  const [e, setE] = useState<string | null>(null);
  useEffect(() => {
    const t = setTimeout(() => {
      setE(null);
      getJson<ListResp>(`/api/katalog?${new URLSearchParams({ q, rodzina: fam, sort, limit: "60" })}`)
        .then((r) => { setD(r); setMore([]); }).catch((x) => setE(String(x.message ?? x)));
    }, 250);
    return () => clearTimeout(t);
  }, [q, fam, sort]);
  const all = [...(d?.gatunki ?? []), ...more];
  const loadMore = () => getJson<ListResp>(`/api/katalog?${new URLSearchParams({ q, rodzina: fam, sort, limit: "60", offset: String(all.length) })}`)
    .then((r) => setMore((m) => [...m, ...r.gatunki]));
  return (
    <section className="view pad" data-testid="katalog">
      <button className="link small" onClick={() => go("#/atlas")}>‹ Atlas</button>
      <h2>Grzyby Polski</h2>
      {d && <Warn text={d.uwaga} />}
      <div className="kt-tools">
        <input type="search" placeholder="Szukaj: nazwa polska lub łacińska" value={q} onChange={(x) => setQ(x.target.value)} data-testid="katalog-szukaj" aria-label="Szukaj gatunku" />
        <select value={fam} onChange={(x) => setFam(x.target.value)} aria-label="Rodzina">
          <option value="">Wszystkie rodziny</option>
          {d?.rodziny.map((f) => <option key={f.rodzina} value={f.rodzina}>{f.rodzina} ({f.liczba})</option>)}
        </select>
        <select value={sort} onChange={(x) => setSort(x.target.value)} aria-label="Kolejność">
          <option value="woj">Najczęstsze na Podkarpaciu</option>
          <option value="pl">Najczęstsze w Polsce</option>
          <option value="nazwa">Alfabetycznie</option>
        </select>
      </div>
      {e && <div className="banner banner-warn">{e === "Błąd 500" ? "Katalog nie jest jeszcze wczytany." : e}</div>}
      {d && <p className="muted small">{d.razem} gatunków</p>}
      {d && d.razem === 0 && <p className="note">Nic nie pasuje. Spróbuj innej nazwy albo usuń filtr rodziny.</p>}
      <ul className="kt-grid">
        {all.map((s) => (
          <li key={s.id}>
            <button className="kt-card" onClick={() => go(`#/atlas/katalog/${s.id}`)} data-testid="katalog-gatunek">
              <Thumb s={s} />
              <span className="kt-name">{name(s)}</span>
              <i className="kt-sci">{s.nazwa_naukowa}</i>
            </button>
          </li>
        ))}
      </ul>
      {d && all.length < d.razem && <button className="secondary kt-more" onClick={loadMore}>Pokaż więcej</button>}
      {d && <Sources d={d} />}
    </section>
  );
}

function Sources({ d }: { d: { zrodla: Src[]; pobrano_utc?: string | null } }) {
  return (
    <details className="footer">
      <summary>Źródła i licencje</summary>
      <ul>{d.zrodla.map((s) => <li key={s.nazwa}><strong>{s.nazwa}</strong> — {s.opis}; {s.licencja}</li>)}</ul>
      {d.pobrano_utc && <p>Pobrano: {new Date(d.pobrano_utc).toLocaleDateString("pl-PL")}</p>}
    </details>
  );
}

// ------------------------------------------------------------------ karta gatunku
export function KatalogSpecies({ id, go }: { id: string; go: (h: string) => void }) {
  const [d, setD] = useState<{ uwaga: string; zrodla: Src[]; gatunek: Detail; ten_sam_rodzaj: Item[] } | null>(null);
  const [e, setE] = useState<string | null>(null);
  useEffect(() => { setD(null); getJson<typeof d>(`/api/katalog/${id}`).then(setD).catch((x) => setE(String(x.message ?? x))); window.scrollTo(0, 0); }, [id]);
  if (e) return <section className="view pad"><div className="banner banner-warn">{e}</div></section>;
  if (!d) return <p className="muted pad">Wczytywanie…</p>;
  const s = d.gatunek;
  const sec = (t: string, v: string | null, tid?: string) => v && (
    <section className="kt-sec" data-testid={tid}><h3>{t}</h3>{v.split("\n").filter(Boolean).map((p, i) =>
      p.length < 40 && !/[.:;]$/.test(p) ? <h4 key={i}>{p}</h4> : <p key={i}>{p}</p>)}</section>
  );
  return (
    <article className="view pad kt-detail" data-testid="katalog-karta">
      <button className="link small" onClick={() => history.length > 1 ? history.back() : go("#/atlas/katalog")}>‹ Wróć</button>
      <Thumb s={s} big />
      {s.zdjecie_miniatura && (
        <p className="tiny muted kt-credit">
          Fot. {s.zdjecie_autor}, {s.zdjecie_licencja}{" "}
          {s.zdjecie_strona && <a href={s.zdjecie_strona} target="_blank" rel="noreferrer">Wikimedia Commons</a>}
        </p>
      )}
      <h2>{name(s)}</h2>
      <p className="muted"><i>{s.nazwa_naukowa}</i>{s.rodzina && <> · rodzina {s.rodzina}</>}</p>
      {s.nazwy_polskie.length > 1 && <p className="small">Inne nazwy: {s.nazwy_polskie.filter((n) => n !== s.nazwa_polska).join(", ")}</p>}
      {s.ostrzezenie_rodzaj && (
        <div className="banner banner-danger" role="alert" data-testid="ostrzezenie-rodzaj">
          Rodzaj <i>{s.rodzaj}</i> obejmuje gatunki śmiertelnie trujące. Nie oznaczaj tych grzybów samodzielnie.
        </div>
      )}
      <Warn text={d.uwaga} />
      {Object.keys(s.cechy_opis).length > 0 && (
        <dl className="facts" data-testid="katalog-cechy">
          {Object.entries(s.cechy_opis).map(([k, v]) => <><dt key={k}>{k}</dt><dd key={k + "v"}>{v.join(", ")}</dd></>)}
        </dl>
      )}
      {(s.siedlisko.gleba || s.siedlisko.drzewa) && (
        <dl className="facts">
          {s.siedlisko.gleba && <><dt>Gleba</dt><dd>{s.siedlisko.gleba.join(", ")} <span className="tag-src">z opisu Wikipedii</span></dd></>}
          {s.siedlisko.drzewa && <><dt>Drzewa</dt><dd>{s.siedlisko.drzewa.join(", ")} <span className="tag-src">z opisu Wikipedii</span></dd></>}
        </dl>
      )}
      <p className="small muted">Obserwacje w GBIF: Polska {s.obserwacje_pl ?? 0}, rejon Podkarpacia {s.obserwacje_woj ?? 0}.</p>
      {sec("Opis", s.opis_wstep)}
      {sec("Budowa", s.opis_budowa, "katalog-budowa")}
      {sec("Występowanie i siedlisko", s.opis_wystepowanie)}
      {sec("Gatunki podobne", s.opis_podobne)}
      {sec("Ochrona", s.opis_ochrona)}
      {!s.wiki_url && <p className="note">Brak artykułu w polskiej Wikipedii — opis niedostępny.</p>}
      {s.wiki_url && (
        <p className="tiny muted">
          Tekst: <a href={s.wiki_url} target="_blank" rel="noreferrer">„{s.wiki_tytul}”, Wikipedia, wolna encyklopedia</a>{" "}
          (<a href={`${s.wiki_url.replace("/wiki/", "/w/index.php?title=")}&action=history`} target="_blank" rel="noreferrer">autorzy</a>),
          licencja CC BY-SA 4.0; fragmenty, bez sekcji o jadalności.
        </p>
      )}
      {d.ten_sam_rodzaj.length > 0 && (
        <>
          <h3>Ten sam rodzaj ({s.rodzaj})</h3>
          <ul className="kt-grid kt-grid-small">
            {d.ten_sam_rodzaj.map((x) => (
              <li key={x.id}><button className="kt-card" onClick={() => go(`#/atlas/katalog/${x.id}`)}><Thumb s={x} /><span className="kt-name">{name(x)}</span></button></li>
            ))}
          </ul>
        </>
      )}
      <Sources d={d} />
    </article>
  );
}

// ------------------------------------------------------------------ pomóż oznaczyć
const QNAME: Record<string, string> = { hymenium: "spód kapelusza", trzon: "trzon", kapelusz: "kapelusz", wysyp: "wysyp", ekologia: "miejsce", gleba: "gleba", drzewa: "drzewa" };

export function KluczView({ go }: { go: (h: string) => void }) {
  const [photo, setPhoto] = useState<string | null>(null);
  const [ans, setAns] = useState<Record<string, string[]>>({});
  const [d, setD] = useState<KeyResp | null>(null);
  const [e, setE] = useState<string | null>(null);
  const [cmp, setCmp] = useState<Hit | null>(null);
  const file = useRef<HTMLInputElement>(null);
  const qs = useMemo(() => {
    const p = new URLSearchParams();
    Object.entries(ans).forEach(([k, vs]) => vs.forEach((v) => p.append(k, v)));
    return p.toString();
  }, [ans]);
  useEffect(() => { getJson<KeyResp>(`/api/katalog/klucz?${qs}`).then(setD).catch((x) => setE(String(x.message ?? x))); }, [qs]);
  useEffect(() => () => { if (photo) URL.revokeObjectURL(photo); }, [photo]);
  const toggle = (q: Question, a: string) => setAns((o) => {
    const cur = o[q.id] ?? [];
    const next = cur.includes(a) ? cur.filter((x) => x !== a) : q.wiele ? [...cur, a] : [a];
    return { ...o, [q.id]: next };
  });
  const answered = Object.values(ans).some((v) => v.length);
  return (
    <section className="view pad" data-testid="klucz">
      <button className="link small" onClick={() => go("#/atlas")}>‹ Atlas</button>
      <h2>Pomóż oznaczyć</h2>
      <div className="banner banner-danger" role="alert" data-testid="klucz-ostrzezenie">
        To tylko podpowiedź z katalogu, nie oznaczenie. Nie jedz grzyba na podstawie aplikacji — pokaż go grzyboznawcy
        (punkty Państwowej Inspekcji Sanitarnej).
      </div>

      <div className="kl-photo">
        {photo ? <img src={photo} alt="Twoje zdjęcie" data-testid="klucz-zdjecie" /> : <div className="kl-photo-empty">Zrób zdjęcie grzyba: kapelusz z góry, spód i cały trzon z podstawą.</div>}
        <input ref={file} type="file" accept="image/*" capture="environment" hidden data-testid="klucz-plik"
          onChange={(x) => { const f = x.target.files?.[0]; if (f) setPhoto(URL.createObjectURL(f)); }} />
        <button onClick={() => file.current?.click()}>{photo ? "Zrób inne zdjęcie" : "Zrób zdjęcie"}</button>
        <p className="tiny muted">Zdjęcie zostaje w telefonie i służy tylko do porównania. Aplikacja go nie analizuje.</p>
      </div>

      {d?.pytania.map((q) => (
        <fieldset key={q.id} className="kl-q">
          <legend>{q.pytanie}{q.wiele && <span className="muted small"> (można kilka)</span>}</legend>
          <div className="kl-opts">
            {q.odpowiedzi.map((a) => (
              <button key={a.id} className={`kl-opt${ans[q.id]?.includes(a.id) ? " on" : ""}`} aria-pressed={ans[q.id]?.includes(a.id) ?? false}
                onClick={() => toggle(q, a.id)} data-testid={`klucz-${q.id}-${a.id}`}>{a.etykieta}</button>
            ))}
          </div>
        </fieldset>
      ))}
      {answered && <button className="secondary" onClick={() => setAns({})}>Wyczyść odpowiedzi</button>}

      {e && <div className="banner banner-warn">{e}</div>}
      {answered && d && (
        <>
          <h3>Pasujące gatunki z katalogu</h3>
          {d.ostrzezenia.map((w, i) => <div key={i} className="banner banner-danger" role="alert">{w}</div>)}
          <ol className="kl-hits" data-testid="klucz-wyniki">
            {d.wyniki.map((h) => (
              <li key={h.id} className={h.ostrzezenie_rodzaj ? "danger" : ""}>
                <button className="kl-hit" onClick={() => setCmp(h)} data-testid="klucz-wynik">
                  <Thumb s={h} />
                  <span className="rank-text">
                    <strong>{name(h)}</strong>
                    <i className="small muted">{h.nazwa_naukowa}</i>
                    <span className="small">
                      {h.zgodne.length > 0 && <span className="ok">zgodne: {h.zgodne.map((x) => QNAME[x] ?? x).join(", ")}</span>}
                      {h.niezgodne.length > 0 && <span className="bad"> · inne: {h.niezgodne.map((x) => QNAME[x] ?? x).join(", ")}</span>}
                      {h.brak_danych.length > 0 && <span className="muted"> · brak danych: {h.brak_danych.map((x) => QNAME[x] ?? x).join(", ")}</span>}
                    </span>
                    {h.ostrzezenie_rodzaj && <span className="bad small">Rodzaj z gatunkami śmiertelnie trującymi</span>}
                  </span>
                </button>
              </li>
            ))}
          </ol>
          <p className="tiny muted">Dopasowanie opiera się na cechach z Wikidata i opisach z Wikipedii. Dla wielu gatunków danych brakuje,
            więc brak gatunku na liście nic nie znaczy.</p>
        </>
      )}

      {cmp && (
        <div className="kl-cmp" role="dialog" aria-label="Porównanie zdjęć" data-testid="klucz-porownanie">
          <div className="kl-cmp-box">
            <div className="kl-cmp-grid">
              <figure>{photo ? <img src={photo} alt="Twoje zdjęcie" /> : <div className="kt-img kt-noimg"><span>brak Twojego zdjęcia</span></div>}<figcaption>Twoje zdjęcie</figcaption></figure>
              <figure><Thumb s={cmp} /><figcaption>{name(cmp)}{cmp.zdjecie_autor && <span className="tiny muted"> · fot. {cmp.zdjecie_autor}, {cmp.zdjecie_licencja}</span>}</figcaption></figure>
            </div>
            {cmp.ostrzezenie_rodzaj && <div className="banner banner-danger">Rodzaj z gatunkami śmiertelnie trującymi.</div>}
            <div className="row gap">
              <button onClick={() => go(`#/atlas/katalog/${cmp.id}`)}>Opis gatunku</button>
              <button className="secondary" onClick={() => setCmp(null)}>Zamknij</button>
            </div>
          </div>
        </div>
      )}
    </section>
  );
}
