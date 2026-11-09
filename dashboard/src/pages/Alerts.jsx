import { Fragment, useEffect, useMemo, useRef, useState } from "react";
import { ackEpisodes, getEpisodeAlerts } from "../api";
import AccessLog from "../components/AccessLog";
import {
  KIND_LABEL, SEVERITY_LABEL, ago, clock, describeEpisode, detectorOf, deviceName, duration, sensorLabel,
} from "../labels";

const KINDS = [["all", "Tout"], ["anomaly", "Anomalies"], ["rule", "Règles"], ["silence", "Silences"], ["notice", "Avis"]];
const STATUSES = [["open", "À traiter"], ["acked", "Acquittés"], ["all", "Tous"]];
const SEVERITIES = [["all", "Toutes"], ["high", "Forte"], ["medium", "Moyenne"], ["low", "Faible"]];
const SORTS = [["recent", "Plus récentes"], ["old", "Plus anciennes"], ["severity", "Gravité"]];
const SEV_RANK = { high: 0, medium: 1, low: 2 };
const PAGE = 25;

// Un épisode « à traiter » : pas encore acquitté et pas un simple avis.
const isOpenEpisode = (e) => !e.acknowledged && e.kind !== "notice";
const norm = (s) => s.normalize("NFD").replace(/\p{Diacritic}/gu, "").toLowerCase();

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

function Chips({ label, options, value, onChange, counts }) {
  return (
    <div className="segmented small" role="group" aria-label={label}>
      {options.map(([key, text]) => (
        <button key={key} aria-pressed={value === key} onClick={() => onChange(key)}>
          {text}
          {counts && <span className="count">{counts[key] ?? 0}</span>}
        </button>
      ))}
    </div>
  );
}

export default function Alerts({ mysa, go }) {
  const [kind, setKind] = useState("all");
  const [status, setStatus] = useState("open");
  const [severity, setSeverity] = useState("all");
  const [device, setDevice] = useState("");
  const [query, setQuery] = useState("");
  const [sort, setSort] = useState("recent");
  const [limit, setLimit] = useState(PAGE);
  const [open, setOpen] = useState(null);
  const [selected, setSelected] = useState(() => new Set());
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const lastClicked = useRef(null);
  const allBox = useRef(null);
  const { episodes, devices, refresh } = mysa;

  // Filtres combinés. `skip` neutralise un filtre : les compteurs de chaque groupe tiennent compte des autres.
  const matching = useMemo(() => {
    const q = norm(query.trim());
    return (skip) => episodes.filter((e) =>
      (skip === "kind" || kind === "all" || e.kind === kind) &&
      (skip === "severity" || severity === "all" || e.severity === severity) &&
      (skip === "status" || status === "all" || (status === "acked" ? e.acknowledged : isOpenEpisode(e))) &&
      (!device || e.device_id === device) &&
      (!q || norm(`${deviceName(e.device_id)} ${sensorLabel(e.sensor, e.device_id)} ${describeEpisode(e)} ${detectorOf(e)}`).includes(q)));
  }, [episodes, kind, severity, status, device, query]);

  const countBy = (skip, field, keys) => {
    const base = matching(skip);
    return Object.fromEntries(keys.map((k) => [k, k === "all" ? base.length : base.filter((e) => field(e) === k).length]));
  };
  const kindCounts = countBy("kind", (e) => e.kind, KINDS.map(([k]) => k));
  const severityCounts = countBy("severity", (e) => e.severity, SEVERITIES.map(([k]) => k));
  const base = matching("status");
  const statusCounts = { open: base.filter(isOpenEpisode).length, acked: base.filter((e) => e.acknowledged).length, all: base.length };

  const rows = useMemo(() => {
    const list = matching(null).slice();
    const byTime = (a, b) => new Date(b.start_ts) - new Date(a.start_ts);
    if (sort === "old") list.sort((a, b) => -byTime(a, b));
    else if (sort === "severity") list.sort((a, b) => (SEV_RANK[a.severity] ?? 3) - (SEV_RANK[b.severity] ?? 3) || byTime(a, b));
    else list.sort(byTime);
    return list;
  }, [matching, sort]);
  const shown = rows.slice(0, limit);

  // Un changement de filtre repart de la première page, sans garder une sélection devenue invisible.
  useEffect(() => { setLimit(PAGE); setSelected(new Set()); lastClicked.current = null; }, [kind, status, severity, device, query, sort]);

  const selectedRows = rows.filter((e) => selected.has(e.id));
  const toClose = selectedRows.filter((e) => !e.acknowledged);
  const toReopen = selectedRows.filter((e) => e.acknowledged);
  useEffect(() => {
    if (allBox.current) allBox.current.indeterminate = selectedRows.length > 0 && selectedRows.length < rows.length;
  }, [selectedRows.length, rows.length]);

  const toggle = (episode, index, shift) => {
    setSelected((prev) => {
      const next = new Set(prev);
      const on = !prev.has(episode.id);
      const from = shift && lastClicked.current !== null ? Math.min(lastClicked.current, index) : index;
      const to = shift && lastClicked.current !== null ? Math.max(lastClicked.current, index) : index;
      for (const e of shown.slice(from, to + 1)) (on ? next.add(e.id) : next.delete(e.id));
      return next;
    });
    lastClicked.current = index;
  };
  const toggleAll = () => setSelected(selectedRows.length === rows.length ? new Set() : new Set(rows.map((e) => e.id)));

  const apply = async (list, acknowledged) => {
    if (!list.length) return;
    setBusy(true);
    setError(null);
    try {
      await ackEpisodes(list.map((e) => e.id), acknowledged);
      setSelected(new Set());
      await refresh();
    } catch (err) {
      setError(err.message || String(err));
    } finally {
      setBusy(false);
    }
  };

  const reset = () => { setKind("all"); setStatus("open"); setSeverity("all"); setDevice(""); setQuery(""); };
  const filtered = kind !== "all" || status !== "open" || severity !== "all" || device || query;

  return (
    <div className="page alerts-page">
      <header className="page-head"><h1>Alertes</h1></header>

      <div className="alerts-toolbar">
        <div className="filters" role="search">
          <input className="search" type="search" value={query} onChange={(e) => setQuery(e.target.value)}
                 placeholder="Rechercher un appareil, un capteur…" aria-label="Rechercher dans les alertes" />
          <label className="select">
            <span>Appareil</span>
            <select value={device} onChange={(e) => setDevice(e.target.value)}>
              <option value="">Tous</option>
              {devices.map((d) => <option key={d.device_id} value={d.device_id}>{deviceName(d.device_id)}</option>)}
            </select>
          </label>
          <label className="select">
            <span>Trier</span>
            <select value={sort} onChange={(e) => setSort(e.target.value)}>
              {SORTS.map(([k, t]) => <option key={k} value={k}>{t}</option>)}
            </select>
          </label>
        </div>
        <div className="filters">
          <Chips label="Statut de traitement" options={STATUSES} value={status} onChange={setStatus} counts={statusCounts} />
          <Chips label="Gravité" options={SEVERITIES} value={severity} onChange={setSeverity} counts={severityCounts} />
          <Chips label="Type d'épisode" options={KINDS} value={kind} onChange={setKind} counts={kindCounts} />
          {filtered && <button className="link" onClick={reset}>Réinitialiser</button>}
        </div>
        {selectedRows.length > 0 && (
          <div className="bulk-bar" role="region" aria-label="Actions sur la sélection" aria-live="polite">
            <strong>{selectedRows.length} sélectionné{selectedRows.length > 1 ? "s" : ""}</strong>
            {toClose.length > 0 && (
              <button className="btn-primary" disabled={busy} onClick={() => apply(toClose, true)}>
                {busy ? "…" : `Acquitter (${toClose.length})`}
              </button>
            )}
            {toReopen.length > 0 && (
              <button className="btn-ack" disabled={busy} onClick={() => apply(toReopen, false)}>Rouvrir ({toReopen.length})</button>
            )}
            <button className="link" onClick={() => setSelected(new Set())}>Tout désélectionner</button>
          </div>
        )}
      </div>

      {error && <p className="error" role="alert">Action impossible : {error}</p>}

      {rows.length === 0 ? (
        <p className="empty">Aucun épisode pour ces filtres.{filtered && <> <button className="link" onClick={reset}>Réinitialiser</button></>}</p>
      ) : (
        <>
          <div className="table-wrap">
            <table className="episodes">
              <thead>
                <tr>
                  <th className="check">
                    <input ref={allBox} type="checkbox" checked={selectedRows.length === rows.length} onChange={toggleAll}
                           aria-label={`Sélectionner les ${rows.length} épisodes`} />
                  </th>
                  <th>Début</th><th>Appareil</th><th>Capteur</th><th>Ce qui a été vu</th>
                  <th>Détecteur</th><th>Gravité</th><th>Durée</th><th className="num">Alertes</th>
                  <th>Statut</th><th />
                </tr>
              </thead>
              <tbody>
                {shown.map((e, i) => (
                  <Fragment key={e.id}>
                    <tr className={`sev-${e.severity} ${open === e.id ? "is-open" : ""} ${e.acknowledged ? "is-acked" : ""} ${selected.has(e.id) ? "is-selected" : ""}`}>
                      <td className="check">
                        <input type="checkbox" checked={selected.has(e.id)} onChange={() => {}}
                               onClick={(ev) => toggle(e, i, ev.shiftKey)}
                               aria-label={`Sélectionner : ${deviceName(e.device_id)}, ${describeEpisode(e)}`} />
                      </td>
                      <td className="mono">{clock(e.start_ts)}</td>
                      <td>
                        <button className="link strong" onClick={() => go(`/appareil/${encodeURIComponent(e.device_id)}`)}>
                          {deviceName(e.device_id)}
                        </button>
                      </td>
                      <td>{sensorLabel(e.sensor, e.device_id)}</td>
                      <td>{describeEpisode(e)}</td>
                      <td><span className="tag">{e.kind === "anomaly" || e.kind === "rule" ? detectorOf(e) : (KIND_LABEL[e.kind] ?? e.kind)}</span></td>
                      <td><span className={`sev sev-${e.severity}`}>{SEVERITY_LABEL[e.severity] ?? e.severity}</span></td>
                      <td>{duration(e.start_ts, e.end_ts)}</td>
                      <td className="num mono">{e.alert_count}</td>
                      <td>
                        {e.acknowledged ? (
                          <button className="link" disabled={busy} onClick={() => apply([e], false)}
                                  title={`Acquitté ${ago(e.ack_ts)}`}>Rouvrir</button>
                        ) : (
                          <button className="btn-ack" disabled={busy} onClick={() => apply([e], true)}>Acquitter</button>
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
                      <tr className="detail-row"><td colSpan={11}><EpisodeDetail episode={e} /></td></tr>
                    )}
                  </Fragment>
                ))}
              </tbody>
            </table>
          </div>
          {rows.length > shown.length && (
            <div className="load-more">
              <button className="btn-ack" onClick={() => setLimit((l) => l + PAGE)}>Afficher {Math.min(PAGE, rows.length - shown.length)} de plus</button>
              <button className="link" onClick={() => setLimit(rows.length)}>Tout afficher ({rows.length})</button>
            </div>
          )}
        </>
      )}

      <AccessLog pulse={mysa.pulse} />
    </div>
  );
}
