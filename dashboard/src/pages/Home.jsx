import Roof from "../components/Roof";
import { Status, CountUp } from "../components/Bits";
import HouseControls from "../components/HouseControls";
import CameraLive from "../components/CameraLive";
import { houseState } from "../useMysa";
import { ago, describeEpisode, deviceKind, deviceName, formatValue, sensorLabel } from "../labels";

function headline(devices, tone, worst) {
  if (!devices.length) return { title: "En attente des appareils", sub: "Aucun message reçu pour l'instant." };
  const flagged = devices.filter((d) => d.level !== "normal");
  if (tone === "calm") return { title: "Tout va bien à la maison", sub: null };
  if (flagged.length === 1)
    return { title: tone === "alert" ? `Alerte : ${deviceName(worst.device_id)}` : `${deviceName(worst.device_id)} est à surveiller`, sub: null };
  return { title: `${flagged.length} appareils demandent votre attention`, sub: null };
}

function Room({ device, latest, streams, onOpen }) {
  const readings = Object.values(latest || {});
  const silent = streams.filter((s) => s.device_id === device.device_id && s.silent).map((s) => s.sensor);
  return (
    <button className={`room tone-${device.level === "critique" ? "alert" : device.level === "à surveiller" ? "watch" : "calm"}`}
            onClick={onOpen}
            onMouseMove={(e) => {
              const r = e.currentTarget.getBoundingClientRect();
              e.currentTarget.style.setProperty("--mx", `${e.clientX - r.left}px`);
              e.currentTarget.style.setProperty("--my", `${e.clientY - r.top}px`);
            }}>
      <div className="room-head">
        <Status level={device.level} label={silent.length ? "Silencieux" : device.label} />
        {device.simulated && <span className="pill pill-sim">Simulé</span>}
        <h3>{deviceName(device.device_id)}</h3>
        <p className="room-kind">{deviceKind(device.device_id)}</p>
      </div>
      {device.waiting ? (
        <p className="muted small room-wait">Déclaré : en attente de son premier message.</p>
      ) : (
        <dl className="readings">
          {readings.map((r) => (
            <div key={r.sensor} className={silent.includes(r.sensor) ? "is-silent" : ""}>
              <dt>{sensorLabel(r.sensor, device.device_id)}</dt>
              <dd>{formatValue(r.sensor, r.value, r.unit, device.device_id)}</dd>
            </div>
          ))}
        </dl>
      )}
      {!device.waiting && (
        <div className="room-foot">
          <span>
            {device.online === false ? <span className="offline">hors ligne · </span> : null}
            Vu {ago(device.last_seen)}
          </span>
          <span className="risk" title="Score de risque sur 100">
            risque <span className="mono">{device.risk}</span>
            <span className="risk-bar"><i style={{ width: `${device.risk}%` }} /></span>
          </span>
        </div>
      )}
    </button>
  );
}

export default function Home({ mysa, go }) {
  const { devices, streams, episodes, latest, pulse, live } = mysa;
  const { tone, worst } = houseState(devices);
  const { title, sub } = headline(devices, tone, worst);
  const active = streams.filter((s) => !s.silent).length;
  const recent = episodes.filter((e) => e.kind !== "notice").slice(0, 8);

  return (
    <div className="home">
      <section className={`house tone-${tone}`} aria-labelledby="house-title">
        <Roof tone={tone} pulse={pulse} live={live} />
        <div className="house-body">
          <div className="house-intro">
            <h1 id="house-title">{title}</h1>
            {sub && <p className="house-sub">{sub}</p>}
          </div>
          <div className="kpis">
            {[
              ["Appareils", devices.length, ""],
              ["Capteurs actifs", active, `/ ${streams.length}`],
              ["Risque max", Math.max(0, ...devices.map((d) => d.risk)), "/ 100"],
              ["Alertes récentes", recent.length, ""],
            ].map(([label, n, unit]) => (
              <div className="kpi" key={label}>
                <strong><CountUp value={n} /></strong>{unit && <span className="kpi-unit">{unit}</span>}
                <span className="kpi-label">{label}</span>
              </div>
            ))}
          </div>
          <div className="rooms">
            {[...devices].sort((a, b) => b.risk - a.risk || deviceName(a.device_id).localeCompare(deviceName(b.device_id), "fr")).map((d) => (
              <Room key={d.device_id} device={d} latest={latest[d.device_id]} streams={streams}
                    onOpen={() => go(`/appareil/${encodeURIComponent(d.device_id)}`)} />
            ))}
          </div>
        </div>
      </section>

      <HouseControls mysa={mysa} go={go} />

      <CameraLive />

      <section className="journal" aria-labelledby="journal-title">
        <div className="section-head">
          <h2 id="journal-title">Ce qui s'est passé</h2>
          <button className="link" onClick={() => go("/alertes")}>Voir toutes les alertes</button>
        </div>
        {recent.length === 0 ? (
          <p className="empty">Aucune alerte. Mysa continue d'apprendre le comportement habituel de chaque appareil.</p>
        ) : (
          <ol className="timeline">
            {recent.map((e) => (
              <li key={e.id} className={`sev-${e.severity}`}>
                <time dateTime={e.end_ts}>{ago(e.end_ts)}</time>
                <p>
                  <button className="link strong" onClick={() => go(`/appareil/${encodeURIComponent(e.device_id)}`)}>
                    {deviceName(e.device_id)}
                  </button>{" "}
                  — {sensorLabel(e.sensor, e.device_id).toLowerCase()} : {describeEpisode(e)}
                </p>
                <span className="muted">
                  {e.alert_count > 1 ? `${e.alert_count} alertes regroupées` : "1 alerte"}
                </span>
              </li>
            ))}
          </ol>
        )}
      </section>
    </div>
  );
}
