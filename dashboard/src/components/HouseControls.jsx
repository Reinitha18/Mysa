import { useEffect, useState } from "react";
import { getActuators, getLastRefusedBadge, sendCommand } from "../api";
import { deviceName } from "../labels";

const SEC = "esp32-sec-01";
const CMF = "esp32-cmf-01";

// Commandes rapides de la maison, regroupées sur l'accueil : porte, alarme (et arrêt de la sirène),
// lampe, thermostat, et enrôlement en un clic du dernier badge refusé. Les commandes passent par
// l'API (api/routes/commands.py), qui n'accepte que les actionneurs connus du firmware.
export default function HouseControls({ mysa }) {
  const [actuators, setActuators] = useState(undefined); // undefined = en cours, null = désactivé
  const [refused, setRefused] = useState(null);
  const [msg, setMsg] = useState({});
  const [setpoint, setSetpoint] = useState(null);
  const [now, setNow] = useState(Date.now());

  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 1000); // compte à rebours du lecteur bloqué
    return () => clearInterval(t);
  }, []);

  useEffect(() => {
    getActuators().then((a) => setActuators(a.enabled ? a.actuators : null), () => setActuators(null));
  }, []);
  useEffect(() => {
    getLastRefusedBadge().then(setRefused, () => setRefused(null));
  }, [mysa.pulse]);

  // Consigne courante du thermostat : dernière valeur connue, sinon 22 °C.
  const knownSetpoint = mysa.latest?.[CMF]?.setpoint?.value;
  useEffect(() => {
    if (setpoint === null && knownSetpoint != null) setSetpoint(Number(knownSetpoint));
  }, [knownSetpoint, setpoint]);
  const sp = setpoint ?? (knownSetpoint != null ? Number(knownSetpoint) : 22);

  if (actuators === undefined || actuators === null) return null;
  const hasSec = !!actuators[SEC];
  const hasCmf = !!actuators[CMF];
  if (!hasSec && !hasCmf) return null;

  const state = (device, sensor) => {
    const row = mysa.latest?.[device]?.[sensor];
    return row ? row.value >= 0.5 : null;
  };
  const armed = state(SEC, "arm");
  const lockOpen = state(SEC, "lock");
  const sirenOn = state(SEC, "alarm");
  const relayOn = state(CMF, "relay");
  const relayAuto = state(CMF, "relay_auto");
  // Lecteur bloqué : value = durée du blocage en secondes (1 avec un ancien firmware : 30 s).
  const lockout = mysa.latest?.[SEC]?.rfid_lockout;
  const lockLeft = lockout?.value > 0
    ? Math.ceil((new Date(lockout.ts).getTime() + (lockout.value > 1 ? lockout.value : 30) * 1000 - now) / 1000)
    : 0;

  const send = async (key, device, actuator, value) => {
    setMsg((m) => ({ ...m, [key]: "Envoi…" }));
    try {
      await sendCommand(device, actuator, value);
      setMsg((m) => ({ ...m, [key]: "Commande envoyée" }));
    } catch (err) {
      setMsg((m) => ({ ...m, [key]: `Échec : ${err.message}` }));
    }
  };

  const setThermostat = (next) => {
    const v = Math.min(40, Math.max(10, Math.round(next * 2) / 2));
    setSetpoint(v);
    send("thermostat", CMF, "setpoint", String(v));
  };

  return (
    <section className="panel house-controls" aria-labelledby="controls-title">
      <h2 id="controls-title">Commandes de la maison</h2>
      <div className="controls-grid">
        {hasSec && (
          <div className="control">
            <div className="control-head">
              <span>Porte</span>
              {lockOpen !== null && (
                <span className={`pill ${lockOpen ? "pill-on" : "pill-off"}`}>{lockOpen ? "Ouverte" : "Fermée"}</span>
              )}
            </div>
            <div className="segmented small">
              <button aria-pressed={lockOpen === true} onClick={() => send("porte", SEC, "lock", "open")}>Ouvrir</button>
              <button aria-pressed={lockOpen === false} onClick={() => send("porte", SEC, "lock", "close")}>Fermer</button>
            </div>
            <span className="muted small">Se referme seule après 5 s.</span>
            <span className="muted small" aria-live="polite">{msg.porte}</span>
          </div>
        )}

        {hasSec && (
          <div className={`control ${sirenOn ? "control-alert" : ""}`}>
            <div className="control-head">
              <span>Alarme</span>
              {sirenOn ? <span className="pill pill-on">Sirène !</span> : armed !== null && (
                <span className={`pill ${armed ? "pill-on" : "pill-off"}`}>{armed ? "Armée" : "Désarmée"}</span>
              )}
            </div>
            <div className="segmented small">
              <button aria-pressed={armed === true} onClick={() => send("alarme", SEC, "arm", "on")}>Armer</button>
              <button aria-pressed={armed === false} onClick={() => send("alarme", SEC, "arm", "off")}>Désarmer</button>
            </div>
            {sirenOn && (
              <button className="btn-ack" onClick={() => send("alarme", SEC, "alarm", "off")}>Arrêter la sirène</button>
            )}
            <span className="muted small">
              {armed
                ? "Armée : un mouvement sans badge valide déclenche la sirène (30 s de délai de sortie)."
                : "Désarmée : les mouvements sont enregistrés, sans sirène. Un badge valide désarme."}
            </span>
            <span className="muted small" aria-live="polite">{msg.alarme}</span>
          </div>
        )}

        {hasSec && (
          <div className="control">
            <div className="control-head">
              <span>Badge</span>
              {lockLeft > 0 && <span className="pill pill-on">Lecteur bloqué</span>}
            </div>
            {lockLeft > 0 && (
              <p className="small" aria-live="polite">
                Trop de badges refusés : nouvel essai possible dans <strong>{lockLeft} s</strong>.
              </p>
            )}
            {refused?.uid ? (
              <>
                <p className="small">Dernier refusé : <span className="mono">{refused.uid}</span> sur {deviceName(refused.device_id)}</p>
                <button className="btn-ack" onClick={() => send("badge", SEC, "badge_add", refused.uid)}>
                  Autoriser ce badge
                </button>
              </>
            ) : (
              <p className="muted small">Aucun badge refusé récemment.</p>
            )}
            <span className="muted small" aria-live="polite">{msg.badge}</span>
          </div>
        )}

        {hasCmf && (
          <div className="control">
            <div className="control-head">
              <span>Lampe</span>
              {relayOn !== null && (
                <span className={`pill ${relayOn ? "" : "pill-off"}`}>{relayOn ? "Allumée" : "Éteinte"}</span>
              )}
            </div>
            <div className="segmented small">
              <button aria-pressed={relayOn === true && relayAuto !== true} onClick={() => send("lampe", CMF, "relay", "on")}>Allumer</button>
              <button aria-pressed={relayOn === false && relayAuto !== true} onClick={() => send("lampe", CMF, "relay", "off")}>Éteindre</button>
              <button aria-pressed={relayAuto === true} onClick={() => send("lampe", CMF, "mode", "auto")}
                      title="Thermostat local : le relais suit la consigne">Auto</button>
            </div>
            <span className="muted small" aria-live="polite">{msg.lampe}</span>
          </div>
        )}

        {hasCmf && (
          <div className="control">
            <div className="control-head">
              <span>Thermostat</span>
              <span className="pill">{sp.toLocaleString("fr-FR", { minimumFractionDigits: 1, maximumFractionDigits: 1 })} °C</span>
            </div>
            <div className="segmented small">
              <button onClick={() => setThermostat(sp - 0.5)} aria-label="Baisser la consigne">−</button>
              <button onClick={() => setThermostat(sp + 0.5)} aria-label="Monter la consigne">+</button>
            </div>
            <span className="muted small" aria-live="polite">{msg.thermostat}</span>
          </div>
        )}
      </div>
    </section>
  );
}
