import { useEffect, useState } from "react";
import { getActuators, getLastRefusedBadge, sendCommand } from "../api";
import { alreadyIn } from "../commandState";
import { deviceName } from "../labels";

const SEC = "esp32-sec-01";
const CMF = "esp32-cmf-01";
const SP_MIN = 10;
const SP_MAX = 40;

// Commandes rapides de la maison, regroupées sur l'accueil : porte, alarme (et arrêt de la sirène),
// prise commandée, thermostat, et enrôlement en un clic du dernier badge refusé. Les commandes passent par
// l'API (api/routes/commands.py), qui n'accepte que les actionneurs connus du firmware. Un bouton est
// désactivé quand l'appareil est déjà dans l'état demandé (commandState.js) ou qu'un envoi est en cours.
export default function HouseControls({ mysa, go }) {
  const [actuators, setActuators] = useState(undefined); // undefined = en cours, null = désactivé
  const [refused, setRefused] = useState(null);
  const [msg, setMsg] = useState({});
  const [setpoint, setSetpoint] = useState(null);
  const [draft, setDraft] = useState("");
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
  // Un nœud n'est commandé que s'il fait partie de la maison affichée.
  const inScope = (id) => mysa.devices.some((d) => d.device_id === id);
  const hasSec = !!actuators[SEC] && inScope(SEC);
  const hasCmf = !!actuators[CMF] && inScope(CMF);
  if (!hasSec && !hasCmf) return null;

  const secNow = mysa.latest?.[SEC];
  const cmfNow = mysa.latest?.[CMF];
  const state = (latest, sensor) => {
    const row = latest?.[sensor];
    return row ? row.value >= 0.5 : null;
  };
  const armed = state(secNow, "arm");
  const lockOpen = state(secNow, "lock");
  const sirenOn = state(secNow, "alarm");
  const relayOn = state(cmfNow, "relay");
  const relayAuto = state(cmfNow, "relay_auto");
  // Lecteur bloqué : value = durée du blocage en secondes (1 avec un ancien firmware : 30 s).
  const lockout = secNow?.rfid_lockout;
  const lockLeft = lockout?.value > 0
    ? Math.ceil((new Date(lockout.ts).getTime() + (lockout.value > 1 ? lockout.value : 30) * 1000 - now) / 1000)
    : 0;

  const sending = (key) => msg[key] === "Envoi…";
  const send = async (key, device, actuator, value) => {
    setMsg((m) => ({ ...m, [key]: "Envoi…" }));
    try {
      await sendCommand(device, actuator, value);
      setMsg((m) => ({ ...m, [key]: "Commande envoyée" }));
    } catch (err) {
      setMsg((m) => ({ ...m, [key]: `Échec : ${err.message}` }));
    }
  };
  // Bouton d'un groupe : désactivé si l'état est déjà celui-là, ou pendant un envoi.
  const off = (key, latest, actuator, value) => sending(key) || alreadyIn(actuator, value, latest);

  const applySetpoint = (value) => {
    const v = Math.round(value * 10) / 10;
    if (!Number.isFinite(v) || v < SP_MIN || v > SP_MAX) {
      setMsg((m) => ({ ...m, thermostat: `Entrez une valeur entre ${SP_MIN} et ${SP_MAX} °C` }));
      return;
    }
    setSetpoint(v);
    setDraft("");
    send("thermostat", CMF, "setpoint", String(v));
  };
  const step = (delta) => applySetpoint(Math.round((sp + delta) * 2) / 2);
  const draftValue = Number(draft.replace(",", "."));

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
              <button aria-pressed={lockOpen === true} disabled={off("porte", secNow, "lock", "open")}
                      onClick={() => send("porte", SEC, "lock", "open")}>Ouvrir</button>
              <button aria-pressed={lockOpen === false} disabled={off("porte", secNow, "lock", "close")}
                      onClick={() => send("porte", SEC, "lock", "close")}>Fermer</button>
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
              <button aria-pressed={armed === true} disabled={off("alarme", secNow, "arm", "on")}
                      onClick={() => send("alarme", SEC, "arm", "on")}>Armer</button>
              <button aria-pressed={armed === false} disabled={off("alarme", secNow, "arm", "off")}
                      onClick={() => send("alarme", SEC, "arm", "off")}>Désarmer</button>
            </div>
            {sirenOn && (
              <button className="btn-ack" disabled={sending("alarme")} onClick={() => send("alarme", SEC, "alarm", "off")}>Arrêter la sirène</button>
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
                <button className="btn-ack" disabled={sending("badge")} onClick={() => send("badge", SEC, "badge_add", refused.uid)}>
                  Autoriser ce badge
                </button>
              </>
            ) : (
              <p className="muted small">Aucun badge refusé récemment.</p>
            )}
            <span className="muted small" aria-live="polite">{msg.badge}</span>
            {go && <button className="link small" onClick={() => go("/badges")}>Gérer les badges autorisés</button>}
          </div>
        )}

        {hasCmf && (
          <div className="control">
            <div className="control-head">
              <span>Prise</span>
              {relayOn !== null && (
                <span className={`pill ${relayOn ? "" : "pill-off"}`}>{relayOn ? "Allumée" : "Éteinte"}</span>
              )}
            </div>
            <div className="segmented small">
              <button aria-pressed={relayOn === true && relayAuto !== true} disabled={off("prise", cmfNow, "relay", "on")}
                      onClick={() => send("prise", CMF, "relay", "on")}>Allumer</button>
              <button aria-pressed={relayOn === false && relayAuto !== true} disabled={off("prise", cmfNow, "relay", "off")}
                      onClick={() => send("prise", CMF, "relay", "off")}>Éteindre</button>
              <button aria-pressed={relayAuto === true} disabled={off("prise", cmfNow, "mode", "auto")}
                      onClick={() => send("prise", CMF, "mode", "auto")}
                      title="Mode Auto : la prise s'allume au-dessus de la consigne et s'éteint 0,5 °C en dessous, sans le hub">Auto</button>
            </div>
            <span className="muted small" aria-live="polite">{msg.prise}</span>
          </div>
        )}

        {hasCmf && (
          <div className="control">
            <div className="control-head">
              <span>Thermostat</span>
              <span className="pill">{sp.toLocaleString("fr-FR", { minimumFractionDigits: 1, maximumFractionDigits: 1 })} °C</span>
            </div>
            <div className="segmented small">
              <button onClick={() => step(-0.5)} disabled={sending("thermostat") || sp <= SP_MIN} aria-label="Baisser la consigne">−</button>
              <button onClick={() => step(0.5)} disabled={sending("thermostat") || sp >= SP_MAX} aria-label="Monter la consigne">+</button>
            </div>
            <p className="muted small">
              En <strong>Auto</strong>, la prise suit un thermostat local (sans le hub) : elle s'allume quand la
              température dépasse la consigne, et s'éteint 0,5 °C en dessous. En <strong>Allumer/Éteindre</strong>, elle
              reste dans cet état jusqu'à la prochaine commande.
            </p>
            <form className="setpoint-form" onSubmit={(e) => { e.preventDefault(); applySetpoint(draftValue); }}>
              <label className="sr" htmlFor="setpoint">Consigne en °C</label>
              <input id="setpoint" type="number" inputMode="decimal" step="0.1" min={SP_MIN} max={SP_MAX}
                     placeholder={`${SP_MIN} à ${SP_MAX} °C`} value={draft} onChange={(e) => setDraft(e.target.value)} />
              <button className="btn-ack" type="submit" disabled={sending("thermostat") || draft.trim() === ""}>Appliquer</button>
            </form>
            <span className="muted small" aria-live="polite">{msg.thermostat}</span>
          </div>
        )}
      </div>
    </section>
  );
}
