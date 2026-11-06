// Choix du thème : "light", "dark" ou "auto" (suit le système). Mémorisé dans le navigateur.
// Le thème sombre est une feuille de style injectée à la demande : en clair, elle est retirée
// et le dashboard retrouve exactement son apparence d'origine.
import darkCss from "./theme-dark.css?inline";

const KEY = "mysa-theme";
const STYLE_ID = "mysa-theme-dark";
const mq = window.matchMedia("(prefers-color-scheme: dark)");

export function getPref() {
  try {
    const v = localStorage.getItem(KEY);
    return v === "light" || v === "dark" || v === "auto" ? v : "dark";
  } catch { return "dark"; }
}

export function applyTheme(pref) {
  const theme = pref === "auto" ? (mq.matches ? "dark" : "light") : pref;
  const el = document.getElementById(STYLE_ID);
  if (theme === "dark" && !el) {
    const style = document.createElement("style");
    style.id = STYLE_ID;
    style.textContent = darkCss;
    document.head.appendChild(style);
  } else if (theme === "light" && el) {
    el.remove();
  }
  document.documentElement.dataset.theme = theme;
  document.querySelector('meta[name="theme-color"]')?.setAttribute("content", theme === "dark" ? "#050b1f" : "#0369B1");
}

export function setPref(pref) {
  try { localStorage.setItem(KEY, pref); } catch { /* navigation privée : le choix vaut pour la session */ }
  applyTheme(pref);
}

mq.addEventListener("change", () => { if (getPref() === "auto") applyTheme("auto"); });
applyTheme(getPref()); // appliqué avant le premier rendu : pas de flash de la mauvaise couleur
