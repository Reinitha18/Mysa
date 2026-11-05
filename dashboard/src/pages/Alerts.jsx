import { Fragment, useEffect, useMemo, useState } from "react";
import { ackEpisode, getEpisodeAlerts } from "../api";
import AccessLog from "../components/AccessLog";
import {
  KIND_LABEL, SEVERITY_LABEL, ago, clock, describeEpisode, detectorOf, deviceName, duration, sensorLabel,
} from "../labels";

const FILTERS = [
  ["all", "Tout"],
  ["anomaly", "Anomalies"],
  ["rule", "Règles"],
  ["silence", "Silences"],
  ["notice", "Avis"],
];

// Un épisode « à traiter » : pas encore acquitté et pas un simple avis.
const isOpenEpisode = (e) => !e.acknowledged && e.kind !== "notice";

const STATUS = [
  ["open", "À traiter"],
  ["acked", "Acquittés"],
  ["all", "Tous"],
];

function EpisodeDetail({ episode }) {
  const [alerts, setAlerts] = useState(null);
  const [error, setError] = useState(null);
  useEffect(() => {
    getEpisodeAlerts(episode.id).then(setAlerts, (e) => setError(e.message));
  }, [episode.id]);
  if (error) return <p className="error">Impossible de charger les alertes : {error}</p>;
  if (!alerts) return <p className="muted">Chargement des alertes…</p>;
  return (
    <div className="episode-detail">
      <p className="mono small">{alerts[0]?.message}</p>
      {episode.acknowledged ? (
        <p className="small ack-note">
          Acquitté {ago(episode.ack_ts)}{episode.ack_note ? ` — « ${episode.ack_note} »` : ""}.
        </p>
      ) : null}
      <table className="mini">
        <thead><tr><th>Heure</th><th>Score</th><th>Source de la décision</th></tr></thead>
        <tbody>
          {alerts.slice(0, 50).map((a) => (
            <tr key={a.id}>
              <td className="mono">{clock(a.ts)}</td>
              <td className="mono">{a.score == null ? "—" : a.score.toFixed(3)}</td>
              <td>{a.source}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {alerts.length > 50 && <p className="muted small">… et {alerts.length - 50} autres alertes de cet épisode.</p>}
    </div>
  );
}

export default function Alerts({ mysa, go }) {
  const [kind, setKind] = useState("all");
  const [status, setStatus] = useState("open");
  const [device, setDevice] = useState("");
  const [open, setOpen] = useState(null);
  const [busy, setBusy] = useState(null);
  const [error, setError] = useState(null);
  const { episodes, devices, refresh } = mysa;

  const rows = useMemo(
    () => episodes.filter((e) =>
      (kind === "all" || e.kind === kind) &&
      (!device || e.device_id === device) &&
      (status === "all" || (status === "acked" ? e.acknowledged : isOpenEpisode(e)))),
    [episodes, kind, device, status],
  );

  const openCount = useMemo(() => episodes.filter(isOpenEpisode).length, [episodes]);

  const setAck = async (episode, acknowledged) => {
    setBusy(episode.id);
    setError(null);
    try {
      await ackEpisode(episode.id, acknowledged);
      await refresh();
    } catch (err) {
      setError(err.message || String(err));
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="page">
      <header className="page-head">
        <div>
          <h1>Alertes</h1>
          <p className="muted">
            Les alertes d'un même capteur rapprochées dans le temps sont regroupées en épisodes.
            <strong> Acquitter</strong> = indiquer que vous avez vu l'épisode et fait le nécessaire : il quitte
            « À traiter » (rien n'est effacé, il reste dans « Acquittés » et peut être rouvert). Une nouvelle
            alerte sur le même capteur ouvrira un nouvel épisode.
          </p>
        </div>
        <p className="page-head-stat">
          <strong>{openCount}</strong> épisode{openCount > 1 ? "s" : ""} à traiter
        </p>
      </header>

      <div className="filters" role="group" aria-label="Filtrer les épisodes">
        <div className="segmented">
          {FILTERS.map(([key, label]) => (
            <button key={key} aria-pressed={kind === key} onClick={() => setKind(key)}>
              {label}
              <span className="count">{key === "all" ? episodes.length : episodes.filter((e) => e.kind === key).length}</span>
            </button>
          ))}
        </div>
        <div className="segmented small" role="group" aria-label="Statut de traitement">
          {STATUS.map(([key, label]) => (
            <button key={key} aria-pressed={status === key} onClick={() => setStatus(key)}>{label}</button>
          ))}
        </div>
        <label className="select">
          <span>Appareil</span>
          <select value={device} onChange={(e) => setDevice(e.target.value)}>
            <option value="">Tous</option>
            {devices.map((d) => <option key={d.device_id} value={d.device_id}>{deviceName(d.device_id)}</option>)}
          </select>
        </label>
      </div>

      {error && <p className="error">Acquittement impossible : {error}</p>}

      {rows.length === 0 ? (
        <p className="empty">Aucun épisode pour ces filtres.</p>
      ) : (
        <div className="table-wrap">
          <table className="episodes">
            <thead>
              <tr>
                <th>Début</th><th>Appareil</th><th>Capteur</th><th>Ce qui a été vu</th>
                <th>Détecteur</th><th>Gravité</th><th>Durée</th><th className="num">Alertes</th>
                <th>Statut</th><th />
              </tr>
            </thead>
            <tbody>
              {rows.map((e) => (
                <Fragment key={e.id}>
                  <tr className={`sev-${e.severity} ${open === e.id ? "is-open" : ""} ${e.acknowledged ? "is-acked" : ""}`}>
                    <td className="mono">{clock(e.start_ts)}</td>
                    <td>
                      <button className="link strong" onClick={() => go(`/appareil/${encodeURIComponent(e.device_id)}`)}>
                        {deviceName(e.device_id)}
                      </button>
                    </td>
                    <td>{sensorLabel(e.sensor)}</td>
                    <td>{describeEpisode(e)}</td>
                    <td><span className="tag">{e.kind === "anomaly" || e.kind === "rule" ? detectorOf(e) : (KIND_LABEL[e.kind] ?? e.kind)}</span></td>
                    <td><span className={`sev sev-${e.severity}`}>{SEVERITY_LABEL[e.severity] ?? e.severity}</span></td>
                    <td>{duration(e.start_ts, e.end_ts)}</td>
                    <td className="num mono">{e.alert_count}</td>
                    <td>
                      {e.acknowledged ? (
                        <button className="link" disabled={busy === e.id} onClick={() => setAck(e, false)}
                                title={`Acquitté ${ago(e.ack_ts)}`}>Rouvrir</button>
                      ) : (
                        <button className="btn-ack" disabled={busy === e.id} onClick={() => setAck(e, true)}
                                title="Marquer comme traité : vu et vérifié">
                          {busy === e.id ? "…" : "Acquitter"}
                        </button>
                      )}
                    </td>
                    <td>
                      <button className="icon" aria-expanded={open === e.id}
                              aria-label={open === e.id ? "Masquer le détail" : "Afficher le détail"}
                              onClick={() => setOpen(open === e.id ? null : e.id)}>
                        {open === e.id ? "−" : "+"}
                      </button>
                    </td>
                  </tr>
                  {open === e.id && (
                    <tr className="detail-row"><td colSpan={10}><EpisodeDetail episode={e} /></td></tr>
                  )}
                </Fragment>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <AccessLog pulse={mysa.pulse} />
    </div>
  );
}
