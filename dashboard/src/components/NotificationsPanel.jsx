import { useEffect, useState } from "react";
import { getNotifications, testNotifications } from "../api";

// Canaux de notification renseignés dans .env (engine/notify.py) et envoi d'un test avant la démonstration.
export default function NotificationsPanel() {
  const [state, setState] = useState(null);
  const [results, setResults] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => { getNotifications().then(setState, (err) => setError(err.message)); }, []);

  const runTest = async () => {
    setBusy(true);
    setError(null);
    try {
      setResults((await testNotifications()).results);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  const channels = state ? Object.entries(state.channels) : [];
  return (
    <section className="panel notifications" aria-labelledby="notif-title">
      <div className="control-head">
        <h2 id="notif-title">Notifications</h2>
        {state && <span className={`pill ${state.enabled ? "" : "pill-off"}`}>{state.enabled ? "Activées" : "Coupées (MYSA_NOTIFY=0)"}</span>}
      </div>
      <p className="muted small">
        Alertes critiques seulement, une notification par épisode : alarme, intrusion, lecteur de badges
        bloqué, surchauffe, nœud hors ligne. Canaux : e-mail et SMS, à renseigner dans{" "}
        <span className="mono">.env</span> (docs/notifications.md).
      </p>
      <ul className="channels">
        {channels.map(([name, on]) => (
          <li key={name}>
            <span>{name}</span>
            <span className={`pill ${on ? "" : "pill-off"}`}>{on ? "configuré" : "non configuré"}</span>
            {results?.[name] && <span className={`small ${results[name] === "envoyé" ? "" : "muted"}`}>{results[name]}</span>}
          </li>
        ))}
      </ul>
      <button className="btn-ack" onClick={runTest} disabled={busy || !channels.some(([, on]) => on)}>
        {busy ? "Envoi…" : "Envoyer une notification de test"}
      </button>
      {error && <p className="small login-error" role="alert">{error}</p>}
    </section>
  );
}
