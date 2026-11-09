import { useEffect, useState } from "react";
import {
  CartesianGrid, Line, LineChart, ReferenceArea, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import { getActuators, getEpisodes, getHistory, getRisk, sendCommand } from "../api";
import { RiskRing, Status } from "../components/Bits";
import { alreadyIn } from "../commandState";
import {
  REGIMES, ago, clock, describeEpisode, deviceKind, deviceName, formatValue, isBinary, sensorLabel,
} from "../labels";

const N_LOCAL_MIN = 40; // engine/model.py : MIN_TRAIN_SAMPLES

function SensorChart({ deviceId, sensor, rows, episodes }) {
  const binary = isBinary(sensor, rows[0]?.unit);
  const data = rows.map((r) => ({ t: new Date(r.ts).getTime(), v: r.value })).sort((a, b) => a.t - b.t);
  if (data.length < 2) return <p className="muted">Pas encore assez de mesures.</p>;
  const t0 = data[0].t;
  const t1 = data[data.length - 1].t;
  const marks = episodes
    .filter((e) => e.sensor === sensor && e.kind !== "notice")
    .map((e) => ({ id: e.id, x1: Math.max(new Date(e.start_ts).getTime(), t0), x2: Math.min(new Date(e.end_ts).getTime() + 5000, t1), sev: e.severity }))
    .filter((m) => m.x2 > t0 && m.x1 < t1);
  return (
    <ResponsiveContainer width="100%" height={binary ? 120 : 190}>
      <LineChart data={data} margin={{ top: 8, right: 12, bottom: 0, left: 0 }}>
        <CartesianGrid stroke="var(--grid)" vertical={false} />
        <XAxis dataKey="t" type="number" domain={[t0, t1]} scale="time" tickFormatter={(t) => clock(t).slice(0, 5)}
               stroke="var(--muted)" fontSize={11} tickLine={false} minTickGap={48} />
        <YAxis stroke="var(--muted)" fontSize={11} tickLine={false} axisLine={false} width={binary ? 64 : 48}
               domain={binary ? [0, 1] : ["auto", "auto"]} ticks={binary ? [0, 1] : undefined}
               tickFormatter={(v) => (binary ? formatValue(sensor, v) : v.toLocaleString("fr-FR", { maximumFractionDigits: 1 }))} />
        {marks.map((m) => (
          <ReferenceArea key={m.id} x1={m.x1} x2={m.x2} ifOverflow="hidden"
                         fill={m.sev === "high" ? "var(--alert)" : "var(--watch)"} fillOpacity={0.16} />
        ))}
        <Tooltip labelFormatter={(t) => clock(t)} formatter={(v) => [formatValue(sensor, v, rows[0]?.unit, deviceId), sensorLabel(sensor, deviceId)]}
                 contentStyle={{ borderRadius: 10, border: "1px solid var(--line)", fontFamily: "var(--font-body)" }} />
        <Line dataKey="v" type={binary ? "stepAfter" : "monotone"} stroke="var(--blue)" strokeWidth={2} dot={false}
              isAnimationActive={false} />
      </LineChart>
    </ResponsiveContainer>
  );
}

const VALUE_LABELS = { on: "Activer", off: "Désactiver", open: "Ouvrir", close: "Fermer",
  manual: "Manuel", auto: "Automatique" };

// Valeur libre : UID d'un badge (motif) ou consigne numérique (plage)
function FreeValue({ spec, onSend }) {
  const [value, setValue] = useState("");
  const ok = spec.pattern
    ? new RegExp(spec.pattern).test(value.trim())
    : value !== "" && Number(value) >= spec.range[0] && Number(value) <= spec.range[1];
  return (
    <form className="segmented small" onSubmit={(e) => { e.preventDefault(); if (ok) onSend(value.trim()); }}>
      <input value={value} onChange={(e) => setValue(e.target.value)}
        type={spec.range ? "number" : "text"} step="0.5"
        min={spec.range?.[0]} max={spec.range?.[1]}
        placeholder={spec.pattern ? "29 2F 3A 03" : `${spec.range[0]} à ${spec.range[1]}`}
        aria-label={spec.label} />
      <button type="submit" disabled={!ok}>Envoyer</button>
    </form>
  );
}

function Commands({ deviceId, actuators, latest }) {
  const [state, setState] = useState({});
  if (!actuators) return null;
  const send = async (actuator, value) => {
    setState((s) => ({ ...s, [actuator]: "Envoi…" }));
    try {
      await sendCommand(deviceId, actuator, value);
      setState((s) => ({ ...s, [actuator]: `Commande « ${value} » envoyée` }));
    } catch (err) {
      setState((s) => ({ ...s, [actuator]: `Échec : ${err.message}` }));
    }
  };
  return (
    <section className="panel">
      <h2>Commandes</h2>
      <ul className="commands">
        {Object.entries(actuators).map(([name, spec]) => (
          <li key={name}>
            <span>{spec.label}</span>
            {spec.values ? (
              <div className="segmented small">
                {spec.values.map((v) => (
                  <button key={v} disabled={state[name] === "Envoi…" || alreadyIn(name, v, latest)} onClick={() => send(name, v)}>
                    {VALUE_LABELS[v] ?? v}
                  </button>
                ))}
              </div>
            ) : (
              <FreeValue spec={spec} onSend={(v) => send(name, v)} />
            )}
            <span className="muted small" aria-live="polite">{state[name]}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}

export default function Device({ id, mysa, go }) {
  const [view, setView] = useState({ risk: null, history: {}, episodes: [], actuators: null, error: null });
  const streams = mysa.streams.filter((s) => s.device_id === id);
  const device = mysa.devices.find((d) => d.device_id === id);
  const sensorKey = streams.map((s) => s.sensor).join(",");

  useEffect(() => {
    let stop = false;
    const sensors = sensorKey ? sensorKey.split(",") : [];
    Promise.all([
      getRisk(id),
      getEpisodes(200, id),
      Promise.all(sensors.map((s) => getHistory(id, 300, s).catch(() => []))),
      getActuators().catch(() => null),
    ]).then(([risk, episodes, histories, act]) => {
      if (stop) return;
      const history = Object.fromEntries(sensors.map((s, i) => [s, histories[i]]));
      setView({ risk, episodes, history, actuators: act?.enabled ? act.actuators[id] : null, error: null });
    }, (err) => !stop && setView((v) => ({ ...v, error: err.message })));
    return () => { stop = true; };
  }, [id, sensorKey, mysa.pulse]);

  if (device?.waiting) {
    return (
      <div className="page device">
        <button className="link back" onClick={() => go("/")}>← Maison</button>
        <header className="device-head">
          <div>
            <p className="eyebrow">{deviceKind(id)} · <span className="mono">{id}</span></p>
            <h1>{deviceName(id)}</h1>
          </div>
        </header>
        <p className="empty">Cet appareil est déclaré, mais Mysa n'a reçu aucun message de sa part pour l'instant.</p>
      </div>
    );
  }
  if (view.error && !view.risk) {
    return (
      <div className="page">
        <button className="link" onClick={() => go("/")}>← Maison</button>
        <p className="error">Appareil introuvable : {id}. {view.error}</p>
      </div>
    );
  }
  const { risk } = view;
  return (
    <div className="page device">
      <button className="link back" onClick={() => go("/")}>← Maison</button>
      <header className="device-head">
        <div>
          <p className="eyebrow">{deviceKind(id)} · <span className="mono">{id}</span></p>
          <h1>{deviceName(id)} {device?.simulated && <span className="pill pill-sim">Simulé</span>}</h1>
          {device && <p className="muted">Dernier message {ago(device.last_seen)}</p>}
        </div>
        {risk && (
          <div className="device-risk">
            <RiskRing score={risk.score} level={risk.level} />
            <Status level={risk.level} label={risk.label} />
          </div>
        )}
      </header>

      <div className="device-grid">
        <div className="sensors">
          {streams.map((s) => {
            const regime = REGIMES[s.regime] ?? { label: s.regime ?? "—", text: "" };
            const learning = s.regime !== "local";
            return (
              <section key={s.sensor} className="panel sensor">
                <div className="sensor-head">
                  <h2>{sensorLabel(s.sensor, id)}</h2>
                  <span className={`regime regime-${s.regime}`} title={regime.text}>{regime.label}</span>
                  {s.silent ? <span className="status tone-watch"><i />Silencieux</span> : null}
                </div>
                <p className="muted small">
                  {regime.text}
                  {learning && s.regime !== "démarrage" && ` · ${Math.min(s.local_samples, N_LOCAL_MIN)}/${N_LOCAL_MIN} échantillons`}
                  {s.ema_interval ? ` · un message toutes les ${s.ema_interval.toLocaleString("fr-FR", { maximumFractionDigits: 1 })} s` : ""}
                </p>
                {learning && s.regime !== "démarrage" && (
                  <div className="progress" aria-hidden="true"><i style={{ width: `${(100 * Math.min(s.local_samples, N_LOCAL_MIN)) / N_LOCAL_MIN}%` }} /></div>
                )}
                <SensorChart deviceId={id} sensor={s.sensor} rows={view.history[s.sensor] || []} episodes={view.episodes} />
              </section>
            );
          })}
        </div>

        <aside className="side">
          <section className="panel">
            <h2>Pourquoi ce score</h2>
            {!risk || risk.causes.length === 0 ? (
              <p className="muted">Aucun épisode récent : le score revient à zéro en l'absence d'alerte.</p>
            ) : (
              <ul className="causes">
                {risk.causes.map((c) => (
                  <li key={c.episode_id}>
                    <span className="mono">+{Math.round(c.contribution)}</span>
                    <div>
                      <strong>{sensorLabel(c.sensor, id)}</strong> : {describeEpisode(c)}
                      <p className="muted small">{ago(c.end_ts)} · {c.alert_count} alerte{c.alert_count > 1 ? "s" : ""}</p>
                    </div>
                  </li>
                ))}
              </ul>
            )}
            {risk?.silent_sensors?.length > 0 && (
              <p className="small">Silencieux en ce moment : {risk.silent_sensors.map((s) => sensorLabel(s, id)).join(", ")}.</p>
            )}
          </section>
          <Commands deviceId={id} actuators={view.actuators} latest={mysa.latest?.[id]} />
        </aside>
      </div>
    </div>
  );
}
