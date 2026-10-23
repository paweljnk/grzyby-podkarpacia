/** Ikony liniowe (24×24, kolor z currentColor). */
const P = { fill: "none", stroke: "currentColor", strokeWidth: 1.8, strokeLinecap: "round" as const, strokeLinejoin: "round" as const };

export const icons: Record<string, JSX.Element> = {
  mapa: <svg viewBox="0 0 24 24" {...P}><path d="M9 4 3 6v14l6-2 6 2 6-2V4l-6 2-6-2Z" /><path d="M9 4v14M15 6v14" /></svg>,
  szukaj: <svg viewBox="0 0 24 24" {...P}><circle cx="11" cy="11" r="6.5" /><path d="m20 20-4.2-4.2" /></svg>,
  ranking: <svg viewBox="0 0 24 24" {...P}><path d="M9 6h11M9 12h11M9 18h11" /><path d="M4 6h.01M4 12h.01M4 18h.01" strokeWidth={2.6} /></svg>,
  kalendarz: <svg viewBox="0 0 24 24" {...P}><rect x="3.5" y="5" width="17" height="15" rx="3" /><path d="M3.5 10h17M8 3v4M16 3v4" /></svg>,
  porownanie: <svg viewBox="0 0 24 24" {...P}><path d="M12 4v16M5 20h14M6 8h12" /><path d="m6 8-3 6a3 3 0 0 0 6 0L6 8ZM18 8l-3 6a3 3 0 0 0 6 0l-3-6Z" /></svg>,
  atlas: <svg viewBox="0 0 24 24" {...P}><path d="M4 5.5A2.5 2.5 0 0 1 6.5 3H20v15H6.5A2.5 2.5 0 0 0 4 20.5v-15Z" /><path d="M4 20.5A2.5 2.5 0 0 1 6.5 18H20v3H6.5" /></svg>,
  warstwy: <svg viewBox="0 0 24 24" {...P}><path d="m12 3 9 5-9 5-9-5 9-5Z" /><path d="m3 13 9 5 9-5" /></svg>,
  tarcza: <svg viewBox="0 0 24 24" {...P}><path d="M12 3 5 6v5c0 4.5 3 8 7 10 4-2 7-5.5 7-10V6l-7-3Z" /></svg>,
  lokalizacja: <svg viewBox="0 0 24 24" {...P}><circle cx="12" cy="12" r="3.5" /><path d="M12 2v3M12 19v3M2 12h3M19 12h3" /><circle cx="12" cy="12" r="7.5" /></svg>,
  grzyb: <svg viewBox="0 0 24 24" {...P}><path d="M3.5 12a8.5 7 0 0 1 17 0H3.5Z" /><path d="M9.5 12v5.5a2.5 2.5 0 0 0 5 0V12" /></svg>,
};
