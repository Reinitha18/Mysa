import { useCallback, useEffect, useMemo, useState } from "react";
import { useMysa } from "./useMysa";
import { getAuthStatus, logout } from "./api";
import { Toasts } from "./components/Bits";
import Logo from "./components/Logo";
import ThemeToggle from "./components/ThemeToggle";
import Login from "./components/Login";
import Home from "./pages/Home";
import Alerts from "./pages/Alerts";
import Device from "./pages/Device";
import Engine from "./pages/Engine";
import Badges from "./pages/Badges";
import Manage from "./pages/Manage";
import Settings from "./pages/Settings";
import Validation from "./pages/Validation";

const route = () => window.location.hash.replace(/^#/, "") || "/";
const NAV = [["/", "Maison"], ["/alertes", "Alertes"], ["/badges", "Badges"], ["/gestion", "Gestion"], ["/moteur", "Moteur"], ["/validation", "Validation"]];
const HOUSE_KEY = "mysa-house";

// Écran de connexion si le hub est protégé (comptes e-mail, ou MYSA_DASHBOARD_PASSWORD) ; le reste du
// dashboard ne démarre (requêtes, WebSockets) qu'une fois la session ouverte.
export default function App() {
  const [auth, setAuth] = useState(null); // null = vérification en cours
  const check = useCallback(() => {
    getAuthStatus().then(setAuth, () => setAuth({ required: false, authenticated: true }));
  }, []);
  useEffect(() => {
    check();
    const onUnauthorized = () => setAuth((a) => (a?.required ? { ...a, authenticated: false } : a));
    window.addEventListener("mysa:unauthorized", onUnauthorized);
    return () => window.removeEventListener("mysa:unauthorized", onUnauthorized);
  }, [check]);

  if (auth === null) return <p className="loading">Connexion à Mysa…</p>;
  if (auth.required && !auth.authenticated) return <Login auth={auth} onDone={check} />;
  const onLogout = auth.required ? () => logout().finally(check) : null;
  return <Dashboard auth={auth} onLogout={onLogout} onAuthChange={check} />;
}

// Avec plusieurs maisons, chaque page ne montre que celle choisie en haut ; la page Gestion les voit toutes.
function scopeToHouse(raw, houseId) {
  if (raw.houses.length <= 1 || !houseId) return raw;
  const devices = raw.devices.filter((d) => d.house_id === houseId);
  const ids = new Set(devices.map((d) => d.device_id));
  return {
    ...raw,
    devices,
    streams: raw.streams.filter((s) => ids.has(s.device_id)),
    episodes: raw.episodes.filter((e) => ids.has(e.device_id)),
    latest: Object.fromEntries(Object.entries(raw.latest).filter(([id]) => ids.has(id))),
  };
}

function Dashboard({ auth, onLogout, onAuthChange }) {
  const [path, setPath] = useState(route);
  const raw = useMysa();
  const [houseId, setHouseId] = useState(() => {
    try { return Number(localStorage.getItem(HOUSE_KEY)) || null; } catch { return null; }
  });
  const house = raw.houses.find((h) => h.id === houseId) ?? raw.houses[0] ?? null;
  const mysa = useMemo(() => scopeToHouse(raw, house?.id), [raw, house?.id]);
  const pickHouse = (id) => {
    setHouseId(id);
    try { localStorage.setItem(HOUSE_KEY, String(id)); } catch { /* navigation privée : valable pour la session */ }
  };

  useEffect(() => {
    const onHash = () => { setPath(route()); window.scrollTo(0, 0); };
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);
  const go = useCallback((p) => { window.location.hash = p; }, []);

  // Le badge des alertes compte toutes les maisons : une alerte ailleurs reste une alerte.
  const openAlerts = raw.episodes.filter((e) => e.kind !== "notice" && !e.acknowledged && Date.now() - new Date(e.end_ts) < 30 * 60 * 1000).length;
  const deviceMatch = /^\/appareil\/(.+)$/.exec(path);
  let page;
  if (deviceMatch) page = <Device id={decodeURIComponent(deviceMatch[1])} mysa={raw} go={go} />;
  else if (path === "/alertes") page = <Alerts mysa={mysa} go={go} />;
  else if (path === "/moteur") page = <Engine mysa={mysa} go={go} />;
  else if (path === "/badges") page = <Badges mysa={mysa} go={go} />;
  else if (path === "/gestion") page = <Manage mysa={raw} />;
  else if (path === "/parametres") page = <Settings auth={auth} onAuthChange={onAuthChange} onLogout={onLogout} />;
  else if (path === "/validation") page = <Validation go={go} />;
  else page = <Home mysa={mysa} go={go} />;

  const tab = deviceMatch ? "/" : path;
  return (
    <>
      <a className="skip" href="#main">Aller au contenu</a>
      <header className="topbar">
        <a href="#/" className="brand" aria-label="Mysa, accueil">
          <Logo height={42} />
        </a>
        <nav aria-label="Sections">
          {NAV.map(([p, label]) => (
            <a key={p} href={`#${p}`} aria-current={tab === p ? "page" : undefined}>
              {label}
              {p === "/alertes" && openAlerts > 0 && <span className="badge" aria-label={`${openAlerts} récentes`}>{openAlerts}</span>}
            </a>
          ))}
        </nav>
        {raw.houses.length > 1 && (
          <label className="house-picker">
            <span className="sr">Maison affichée</span>
            <select value={house?.id ?? ""} onChange={(e) => pickHouse(Number(e.target.value))}>
              {raw.houses.map((h) => <option key={h.id} value={h.id}>{h.name}</option>)}
            </select>
          </label>
        )}
        <ThemeToggle />
        <span className={`live ${mysa.live ? "is-on" : ""}`} title="Flux d'alertes en temps réel">
          <i aria-hidden="true" />{mysa.live ? "En direct" : "Hors ligne"}
        </span>
        <a className="settings-link" href="#/parametres" aria-label="Paramètres" title="Paramètres"
           aria-current={tab === "/parametres" ? "page" : undefined}>
          <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <circle cx="12" cy="12" r="3" />
            <path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1Z" />
          </svg>
        </a>
        {onLogout && <button className="link logout" onClick={onLogout}>Se déconnecter</button>}
      </header>

      {!auth.required && path !== "/parametres" && (
        <div className="banner banner-watch" role="status">
          Le tableau de bord n'est pas protégé : tout appareil du réseau peut commander la porte.{" "}
          <a href="#/parametres">Créer un compte</a>
        </div>
      )}

      {mysa.apiError && (
        <div className="banner" role="alert">
          Le hub Mysa ne répond pas ({mysa.apiError}). Vérifiez qu'il est démarré (<code>deploy\mysa-start.ps1</code>,
          ou <code>docker compose ps</code>) ; le tableau de bord se reconnecte tout seul.
        </div>
      )}

      <main id="main">{mysa.loaded || mysa.apiError ? page : <p className="loading">Connexion à Mysa…</p>}</main>
      <Toasts toasts={mysa.toasts} dismiss={mysa.dismiss} go={go} />
    </>
  );
}
