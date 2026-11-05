import { useCallback, useEffect, useState } from "react";
import { useMysa } from "./useMysa";
import { getAuthStatus, logout } from "./api";
import { Toasts } from "./components/Bits";
import Login from "./components/Login";
import Home from "./pages/Home";
import Alerts from "./pages/Alerts";
import Device from "./pages/Device";
import Engine from "./pages/Engine";

const route = () => window.location.hash.replace(/^#/, "") || "/";

// Écran de connexion si le hub exige un mot de passe (MYSA_DASHBOARD_PASSWORD) ; le reste du
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
  if (auth.required && !auth.authenticated) return <Login onDone={check} />;
  const onLogout = auth.required ? () => logout().finally(check) : null;
  return <Dashboard onLogout={onLogout} />;
}

function Dashboard({ onLogout }) {
  const [path, setPath] = useState(route);
  const mysa = useMysa();

  useEffect(() => {
    const onHash = () => { setPath(route()); window.scrollTo(0, 0); };
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);
  const go = useCallback((p) => { window.location.hash = p; }, []);

  const openAlerts = mysa.episodes.filter((e) => e.kind !== "notice" && !e.acknowledged && Date.now() - new Date(e.end_ts) < 30 * 60 * 1000).length;
  const deviceMatch = /^\/appareil\/(.+)$/.exec(path);
  let page;
  if (deviceMatch) page = <Device id={decodeURIComponent(deviceMatch[1])} mysa={mysa} go={go} />;
  else if (path === "/alertes") page = <Alerts mysa={mysa} go={go} />;
  else if (path === "/moteur") page = <Engine mysa={mysa} go={go} />;
  else page = <Home mysa={mysa} go={go} />;

  const tab = deviceMatch ? "/" : path;
  return (
    <>
      <a className="skip" href="#main">Aller au contenu</a>
      <header className="topbar">
        <a href="#/" className="brand" aria-label="Mysa, accueil">
          <img src={`${import.meta.env.BASE_URL}mysa-logo.png`} alt="Mysa" />
        </a>
        <nav aria-label="Sections">
          {[["/", "Maison"], ["/alertes", "Alertes"], ["/moteur", "Moteur"]].map(([p, label]) => (
            <a key={p} href={`#${p}`} aria-current={tab === p ? "page" : undefined}>
              {label}
              {p === "/alertes" && openAlerts > 0 && <span className="badge" aria-label={`${openAlerts} récentes`}>{openAlerts}</span>}
            </a>
          ))}
        </nav>
        <span className={`live ${mysa.live ? "is-on" : ""}`} title="Flux d'alertes en temps réel">
          <i aria-hidden="true" />{mysa.live ? "En direct" : "Hors ligne"}
        </span>
        {onLogout && <button className="link logout" onClick={onLogout}>Se déconnecter</button>}
      </header>

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
