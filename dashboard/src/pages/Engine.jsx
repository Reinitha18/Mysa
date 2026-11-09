import { REGIMES, ago, deviceName, sensorLabel } from "../labels";

const N_LOCAL_MIN = 40;

const STEPS = [
  ["Démarrage", "Le capteur remplit sa première fenêtre de 20 messages."],
  ["Amorçage", "Le modèle de référence de sa catégorie (jeu de données public) écarte les fenêtres suspectes de l'apprentissage."],
  ["Apprentissage", "Mysa accumule 40 fenêtres jugées normales."],
  ["Surveillé", "Le modèle propre au capteur décide, et il est ré-entraîné toutes les 20 fenêtres normales."],
];

const DETECTORS = [
  ["Valeurs", "Une mesure sort largement de la plage apprise : pic, valeur impossible.", "immédiate"],
  ["Rythme", "Le capteur envoie beaucoup plus vite ou plus lentement que d'habitude.", "immédiate"],
  ["Tendance", "Les valeurs dérivent bien plus vite qu'elles ne l'ont jamais fait (capteurs continus).", "immédiate"],
  ["Bascules", "Un capteur tout-ou-rien change d'état sans arrêt.", "immédiate"],
  ["Combinaison", "Isolation Forest : un ensemble de mesures jamais vu ensemble.", "2 fenêtres sur 3"],
  ["Silence", "Le capteur ne publie plus depuis 10 fois son intervalle habituel.", "immédiate"],
];

export default function Engine({ mysa, go }) {
  const { streams } = mysa;
  const counts = Object.fromEntries(Object.keys(REGIMES).map((r) => [r, streams.filter((s) => s.regime === r).length]));
  return (
    <div className="page">
      <header className="page-head">
        <div>
          <h1>Moteur</h1>
          <p className="muted">
            Chaque capteur de chaque appareil est un flux, comparé à son propre comportement habituel.
          </p>
        </div>
      </header>

      <ol className="steps" aria-label="Étapes d'apprentissage d'un flux">
        {STEPS.map(([name, text], i) => {
          const key = Object.keys(REGIMES)[i];
          return (
            <li key={name}>
              <span className="step-count mono">{counts[key] ?? 0}</span>
              <div><strong>{name}</strong><p className="muted small">{text}</p></div>
            </li>
          );
        })}
      </ol>

      <div className="table-wrap">
        <table className="streams">
          <thead>
            <tr>
              <th>Appareil</th><th>Capteur</th><th>Catégorie</th><th>Étape</th><th>Apprentissage</th>
              <th>Référence</th><th className="num">Cadence</th><th className="num">Messages</th><th>Dernier message</th>
            </tr>
          </thead>
          <tbody>
            {streams.map((s) => {
              const pct = s.regime === "local" ? 100 : (100 * Math.min(s.local_samples, N_LOCAL_MIN)) / N_LOCAL_MIN;
              return (
                <tr key={`${s.device_id}/${s.sensor}`} className={s.silent ? "is-silent" : ""}>
                  <td>
                    <button className="link strong" onClick={() => go(`/appareil/${encodeURIComponent(s.device_id)}`)}>
                      {deviceName(s.device_id)}
                    </button>
                  </td>
                  <td>{sensorLabel(s.sensor, s.device_id)} <span className="mono muted small">{s.sensor}</span></td>
                  <td>{s.category ?? <span className="muted">aucune</span>}</td>
                  <td><span className={`regime regime-${s.regime}`}>{REGIMES[s.regime]?.label ?? s.regime}</span></td>
                  <td>
                    <div className="progress inline" title={`${s.local_samples} échantillons`}><i style={{ width: `${pct}%` }} /></div>
                  </td>
                  <td>{s.ref_status ?? "—"}</td>
                  <td className="num mono">{s.ema_interval ? `${s.ema_interval.toFixed(1)} s` : "—"}</td>
                  <td className="num mono">{s.message_count.toLocaleString("fr-FR")}</td>
                  <td>{s.silent ? <span className="status tone-watch"><i />Silencieux</span> : ago(s.last_ts)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <section className="detectors" aria-labelledby="det-title">
        <h2 id="det-title">Ce qui déclenche une alerte</h2>
        <div className="detector-grid">
          {DETECTORS.map(([name, text, when]) => (
            <article key={name} className="panel">
              <h3>{name}</h3>
              <p>{text}</p>
              <p className="muted small">Alerte : {when}</p>
            </article>
          ))}
        </div>
        <p className="muted small">
          Une fenêtre jugée suspecte n'entre jamais dans l'apprentissage. Les alertes rapprochées d'un même capteur
          forment un épisode ; le score de risque d'un appareil additionne ses épisodes récents, qui s'estompent en 30 minutes.
        </p>
      </section>
    </div>
  );
}
