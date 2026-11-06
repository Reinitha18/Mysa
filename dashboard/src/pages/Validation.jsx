import { useEffect, useMemo, useState } from "react";
import { getValidationRuns } from "../api";
import { SEVERITY_LABEL, clock, describeEpisode, deviceName, duration, sensorLabel } from "../labels";

// Les quatre issues possibles d'un scénario d'attaque (attack-lab/run_report.py). Le texte porte le sens ;
// la couleur ne fait que l'appuyer.
const STATUS = {
  blocked: { label: "Bloqué", tone: "calm", hint: "L'attaque n'a pas pu s'exécuter (chiffrement, authentification, ACL ou segmentation)." },
  detected: { label: "Détecté", tone: "calm", hint: "L'attaque s'est exécutée, mais le moteur a levé une alerte." },
  undetected: { label: "Exécuté, non détecté", tone: "watch", hint: "À analyser : l'attaque est passée sans alerte." },
  not_run: { label: "Non exécuté", tone: "idle", hint: "Le scénario n'a pas pu être lancé." },
};

const when = (ts) => new Date(ts).toLocaleString("fr-FR", { dateStyle: "medium", timeStyle: "short" });

function Verdict({ r }) {
  const s = STATUS[r.status] ?? { label: r.status, tone: "idle", hint: "" };
  return (
    <span className={`status tone-${s.tone}`} title={s.hint}>
      <i aria-hidden="true" />
      {s.label}
      {r.status === "detected" && r.delay_s != null && <span className="mono"> · ~{Math.round(r.delay_s)} s</span>}
    </span>
  );
}

// Journal des campagnes de validation : résultat de chaque scénario TI, et ce que Mysa a vu pendant l'attaque.
export default function Validation({ go }) {
  const [runs, setRuns] = useState(null);
  const [error, setError] = useState(null);
  const [picked, setPicked] = useState(null);

  useEffect(() => {
    const load = () => getValidationRuns(30).then((r) => { setRuns(r); setError(null); }, (e) => setError(e.message));
    load();
    const t = setInterval(load, 15000);
    return () => clearInterval(t);
  }, []);

  const run = useMemo(() => runs?.find((r) => r.id === picked) ?? runs?.[0] ?? null, [runs, picked]);
  const delays = run?.results.filter((r) => r.status === "detected" && r.delay_s != null).map((r) => r.delay_s) ?? [];
  const avg = delays.length ? `${Math.round(delays.reduce((a, b) => a + b, 0) / delays.length)} s` : "—";

  return (
    <div className="page validation">
      <header className="page-head">
        <p className="eyebrow">Campagnes de validation</p>
        <h1>Lab d'attaque</h1>
        <p className="muted">
          Résultat des scénarios d'intrusion TI-01 à TI-05, lancés depuis la VM Kali sur le prototype. Pour chaque attaque :
          ce qu'elle donnerait sur un système non durci, et ce qui se passe avec Mysa. Cadre autorisé uniquement : réseau de laboratoire isolé.
        </p>
      </header>

      {error && <p className="error" role="alert">Impossible de lire le journal : {error}</p>}

      {runs && runs.length === 0 && (
        <section className="panel">
          <h2>Aucune campagne enregistrée</h2>
          <p className="muted">
            Lancez la campagne depuis la VM Kali, le hub étant démarré. Le résultat s'affiche ici dès la fin du script :
          </p>
          <pre className="cmd-line">python3 attack-lab/run_report.py</pre>
          <p className="small muted">
            Si le tableau de bord est protégé par mot de passe, renseignez <code>DASHBOARD_PASSWORD</code> dans{" "}
            <code>attack-lab/lab.env</code>. L'option <code>--no-push</code> garde le rapport sans l'envoyer ici.
          </p>
        </section>
      )}

      {run && (
        <>
          <div className="filters">
            <label className="select">
              <span>Campagne</span>
              <select value={run.id} onChange={(e) => setPicked(Number(e.target.value))}>
                {runs.map((r) => <option key={r.id} value={r.id}>{when(r.started_ts)} · {r.results.length} scénarios</option>)}
              </select>
            </label>
            <span className="muted small">
              Durée {duration(run.started_ts, run.finished_ts)}{run.target ? ` · cible ${run.target}` : ""}
            </span>
          </div>

          <div className="kpis">
            <div className="kpi"><strong>{run.summary.blocked}</strong><span className="kpi-label">Bloqués</span></div>
            <div className="kpi"><strong>{run.summary.detected}</strong><span className="kpi-label">Détectés par le moteur</span></div>
            <div className="kpi"><strong>{run.summary.undetected}</strong><span className="kpi-label">Exécutés, non détectés</span></div>
            <div className="kpi"><strong>{avg}</strong><span className="kpi-label">Délai moyen de détection</span></div>
          </div>

          <div className="table-wrap">
            <table>
              <thead>
                <tr><th>TI</th><th>Attaque</th><th>Sans Mysa</th><th>Avec Mysa</th><th>Observations</th></tr>
              </thead>
              <tbody>
                {run.results.map((r) => (
                  <tr key={r.ti}>
                    <td className="mono">{r.ti}</td>
                    <td>{r.name}</td>
                    <td className="small">{r.before ?? <span className="muted">—</span>}</td>
                    <td><Verdict r={r} /></td>
                    <td className="small">{r.note ?? <span className="muted">—</span>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <section className="panel validation-episodes" aria-labelledby="ep-title">
            <h2 id="ep-title">Alertes de Mysa pendant la campagne</h2>
            {run.episodes.length === 0 ? (
              <p className="muted">
                Aucun épisode d'alerte pendant cette campagne. C'est normal quand les attaques sont bloquées avant d'atteindre
                le moteur : il n'a rien à signaler.
              </p>
            ) : (
              <ol className="timeline">
                {run.episodes.map((e) => (
                  <li key={e.id} className={`sev-${e.severity}`}>
                    <time dateTime={e.start_ts}>{clock(e.start_ts)}</time>
                    <p>
                      <button className="link strong" onClick={() => go(`/appareil/${encodeURIComponent(e.device_id)}`)}>
                        {deviceName(e.device_id)}
                      </button>{" "}
                      — {e.sensor ? `${sensorLabel(e.sensor).toLowerCase()} : ` : ""}{describeEpisode(e)}
                    </p>
                    <span className="muted">
                      Gravité {(SEVERITY_LABEL[e.severity] ?? e.severity).toLowerCase()} · {e.alert_count > 1 ? `${e.alert_count} alertes regroupées` : "1 alerte"}
                    </span>
                  </li>
                ))}
              </ol>
            )}
          </section>

          {runs.length > 1 && (
            <section className="detectors" aria-labelledby="hist-title">
              <h2 id="hist-title">Historique des campagnes</h2>
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr><th>Date</th><th className="num">Bloqués</th><th className="num">Détectés</th><th className="num">Non détectés</th><th><span className="sr">Voir</span></th></tr>
                  </thead>
                  <tbody>
                    {runs.map((r) => (
                      <tr key={r.id}>
                        <td>{when(r.started_ts)}{r.id === run.id && <span className="tag"> affichée</span>}</td>
                        <td className="num mono">{r.summary.blocked}</td>
                        <td className="num mono">{r.summary.detected}</td>
                        <td className="num mono">{r.summary.undetected}</td>
                        <td className="num">{r.id !== run.id && <button className="link" onClick={() => setPicked(r.id)}>Voir</button>}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          )}
        </>
      )}
    </div>
  );
}
