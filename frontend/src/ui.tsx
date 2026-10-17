import type { Component, Envelope, Gate } from "./types";

export const TREE_NAMES: Record<string, string> = {
  SO: "sosna", SW: "świerk", JD: "jodła", MD: "modrzew", BK: "buk", DB: "dąb", GB: "grab", BRZ: "brzoza",
  OS: "osika", TP: "topola", OL: "olsza czarna", OLS: "olsza szara", JW: "jawor", LP: "lipa", KL: "klon", JS: "jesion",
};
export const QUALITY: Record<string, string> = { wysoka: "wysoka", srednia: "średnia", niska: "niska" };
export const BIO: Record<string, string> = { owoc: "owocu", korzen: "korzenia", lisc: "liścia", kwiat: "kwiatu", nieprzypisany: "nieprzypisany" };

/** Skala sekwencyjna (jeden odcień) dla wskaźnika 0–100. */
export const SCORE_STOPS: [number, string][] = [[0, "#efe9dc"], [25, "#d4dcb4"], [50, "#9fbd7f"], [75, "#5a8f4e"], [100, "#24502a"]];
export function scoreColor(v: number | null): string {
  if (v == null) return "#c9c4b8";
  for (let i = 1; i < SCORE_STOPS.length; i++) if (v <= SCORE_STOPS[i][0]) return SCORE_STOPS[i][1];
  return SCORE_STOPS[SCORE_STOPS.length - 1][1];
}

export function ScoreBadge({ value, excluded, size = "md" }: { value: number | null; excluded?: boolean; size?: "md" | "lg" }) {
  const bg = scoreColor(value);
  const dark = value != null && value > 55;
  return (
    <div className={`score score-${size}${excluded ? " score-excluded" : ""}`} style={{ background: bg, color: dark ? "#fff" : "#1d2a1b" }}
      aria-label={value == null ? "wskaźnik niedostępny" : `wskaźnik rekomendacji ${Math.round(value)} na 100`} data-testid="score">
      {value == null ? "—" : Math.round(value)}
    </div>
  );
}

export function Breakdown({ A, B, C, D, calendar }: { A: Component; B: Component; C: number; D: number; calendar: boolean }) {
  const cell = (label: string, title: string, v: number | null, mod = false) => (
    <div className="bd-cell" title={title}>
      <span className="bd-label">{label}</span>
      <span className="bd-val">{v == null ? "brak" : mod ? (v > 0 ? "+" : "") + v.toFixed(1) : Math.round(v)}</span>
    </div>
  );
  return (
    <div className="breakdown" data-testid="breakdown">
      {cell("A", "Siedlisko (0–100)", A.wynik)}
      {cell("B", "Pogoda i sezon (0–100)", B.wynik)}
      {cell("C", "Obserwacje (modyfikator)", C, true)}
      {cell("D", "Kalendarz (modyfikator eksperymentalny)", calendar ? D : null, true)}
    </div>
  );
}

export function Gates({ gates }: { gates: Gate[] }) {
  if (!gates.length) return null;
  return <ul className="gates">{gates.map((g, i) => <li key={i}>⛔ {g.opis}</li>)}</ul>;
}

export function Warnings({ env }: { env: Envelope | null }) {
  if (!env) return null;
  return (
    <>
      {env.zbior_danych === "demo" && (
        <div className="banner banner-demo" role="alert" data-testid="demo-banner">
          <strong>DANE DEMONSTRACYJNE</strong> — fikcyjne drzewostany, pogoda i obserwacje. Nie planuj na ich podstawie wypraw.
        </div>
      )}
      {env.ostrzezenia.filter((w) => !w.startsWith("DANE DEMONSTRACYJNE")).map((w, i) => (
        <div key={i} className="banner banner-warn" role="status">{w}</div>
      ))}
    </>
  );
}

const fmt = (iso: string | null) => (iso ? new Date(iso).toLocaleString("pl-PL", { timeZone: "Europe/Warsaw", dateStyle: "short", timeStyle: "short" }) : "brak");

export function Footer({ env }: { env: Envelope | null }) {
  return (
    <footer className="footer" data-testid="footer">
      {env && (
        <>
          <p className="disclaimer">{env.zastrzezenie}</p>
          <details>
            <summary>Źródła danych, licencje i daty</summary>
            <ul>
              {env.zrodla.map((s) => (
                <li key={s.id}>
                  <strong>{s.nazwa}</strong>
                  {s.licencja && <> — {s.licencja}</>}
                  {s.atrybucja && <><br /><span className="muted">{s.atrybucja}</span></>}
                  <br /><span className="muted">ostatni import: {fmt(s.ostatni_import)}{s.status && s.status !== "ok" ? ` · status: ${s.status}` : ""}</span>
                </li>
              ))}
              <li><strong>Podkład mapy</strong> — © OpenMapTiles, © OpenStreetMap contributors (ODbL), OpenFreeMap</li>
            </ul>
            <p className="muted">Pogoda: dane do {env.dane.pogoda_do ?? "brak"}, pobrano {fmt(env.dane.pogoda_pobrano_utc)}.</p>
          </details>
        </>
      )}
    </footer>
  );
}

export function Loading() { return <p className="muted pad">Ładowanie…</p>; }
export function ErrorBox({ error }: { error: string }) { return <div className="banner banner-warn" role="alert">{error}</div>; }
