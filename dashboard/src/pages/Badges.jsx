import { useCallback, useEffect, useState } from "react";
import { getActuators, getAuthorizedBadges, getLastRefusedBadge, sendCommand } from "../api";
import { ago, deviceName } from "../labels";

const SEC = "esp32-sec-01";

// "292f3a03", "29:2f:3a:03" ou "29 2F 3A 03" -> "29 2F 3A 03" ; null si ce n'est pas un UID (4 à 10 octets).
export function parseUid(text) {
  const hex = text.trim().toUpperCase().replace(/[\s:.-]+/g, "");
  if (!/^[0-9A-F]+$/.test(hex) || hex.length % 2 || hex.length < 8 || hex.length > 20) return null;
  return hex.match(/../g).join(" ");
}

// Gestion des badges autorisés. Le nœud d'entrée ne publie que leur NOMBRE : la liste est celle que le hub
// connaît (badges ajoutés ou retirés d'ici, badges déjà acceptés au lecteur). Voir api/routes/badges.py.
export default function Badges({ mysa, go }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [enabled, setEnabled] = useState(true);
  const [refused, setRefused] = useState(null);
  const [uidText, setUidText] = useState("");
  const [confirm, setConfirm] = useState(null); // UID en attente de confirmation de retrait
  const [msg, setMsg] = useState(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    getAuthorizedBadges().then((d) => { setData(d); setError(null); }, (e) => setError(e.message));
    getLastRefusedBadge().then(setRefused, () => setRefused(null));
  }, []);
  useEffect(() => {
    load();
    const t = setInterval(load, 5000);
    return () => clearInterval(t);
  }, [load, mysa.pulse]);
  useEffect(() => {
    getActuators().then((a) => setEnabled(a.enabled && !!a.actuators?.[SEC]?.badge_add), () => setEnabled(false));
  }, []);

  const run = async (actuator, uid, okText) => {
    setBusy(true);
    setMsg(null);
    try {
      await sendCommand(SEC, actuator, uid);
      setMsg({ ok: true, text: okText });
      setConfirm(null);
      setUidText("");
      load();
    } catch (err) {
      setMsg({ ok: false, text: `Échec : ${err.message}` });
    } finally {
      setBusy(false);
    }
  };

  const typed = parseUid(uidText);
  const known = new Set((data?.badges ?? []).map((b) => b.uid));
  const refusedUid = refused?.uid && !known.has(refused.uid.toUpperCase()) ? refused : null;
  const gap = data?.unknown_count > 0;
  const surplus = data && data.node_count != null && data.known_count > data.node_count;

  return (
    <div className="page">
      <header className="page-head">
        <p className="eyebrow">Contrôle d'accès</p>
        <h1>Badges autorisés</h1>
      </header>

      {error && <p className="error" role="alert">Impossible de lire les badges : {error}</p>}
      {!enabled && <p className="note note-watch">Les commandes sont désactivées sur ce hub (MYSA_ENABLE_COMMANDS=0) : la liste est en lecture seule.</p>}

      {data && (
        <div className="kpis">
          <div className="kpi"><strong>{data.node_count ?? "—"}</strong><span className="kpi-label">Badges comptés par le lecteur{data.node_ts ? ` · ${ago(data.node_ts)}` : ""}</span></div>
        </div>
      )}
      {gap && (
        <p className="note note-watch">
          Le lecteur compte {data.node_count} badge{data.node_count > 1 ? "s" : ""}, mais seuls {data.known_count} sont connus du
          tableau de bord. Les {data.unknown_count} autre{data.unknown_count > 1 ? "s" : ""} (ajoutés avant, ou sans passer par ici)
          fonctionnent, mais n'apparaissent pas dans la liste : pour en retirer un, saisissez son UID ci-dessous. Il apparaîtra
          dans la liste dès qu'il sera passé devant le lecteur.
        </p>
      )}
      {surplus && (
        <p className="note note-watch">
          Le tableau de bord connaît plus de badges que le lecteur n'en annonce : une commande n'a peut-être pas été reçue
          (nœud hors ligne ?). Vérifiez l'état du nœud d'entrée.
        </p>
      )}

      <section className="panel" aria-labelledby="add-title">
        <h2 id="add-title">Ajouter ou retirer un badge par son UID</h2>
        <div className="badge-form">
          <label className="small muted" htmlFor="uid">
            UID du badge (4 à 10 octets, par exemple 29 2F 3A 03). Il s'affiche dans le journal des passages.
          </label>
          <div className="badge-form-row">
            <input id="uid" value={uidText} onChange={(e) => { setUidText(e.target.value); setMsg(null); }}
                   placeholder="29 2F 3A 03" autoComplete="off" spellCheck="false" aria-invalid={uidText !== "" && !typed} />
            <button className="btn-primary" disabled={busy || !enabled || !typed}
                    onClick={() => run("badge_add", typed, `Badge ${typed} autorisé.`)}>Autoriser</button>
            <button className="btn-ack" disabled={busy || !enabled || !typed}
                    onClick={() => run("badge_del", typed, `Badge ${typed} retiré.`)}>Retirer</button>
          </div>
          {uidText !== "" && !typed && <p className="small error" role="alert">UID invalide : il faut 4 à 10 octets en hexadécimal.</p>}
          {msg && <p className={`small ${msg.ok ? "ack-note" : "error"}`} role="status">{msg.text}</p>}
        </div>
      </section>

      {refusedUid && (
        <section className="panel badge-refused" aria-label="Dernier badge refusé">
          <p>
            Dernier badge refusé : <span className="mono">{refusedUid.uid}</span> sur {deviceName(refusedUid.device_id)}, {ago(refusedUid.ts)}.
          </p>
          <button className="btn-ack" disabled={busy || !enabled}
                  onClick={() => run("badge_add", refusedUid.uid, `Badge ${refusedUid.uid} autorisé.`)}>Autoriser ce badge</button>
        </section>
      )}

      <h2 className="section-title">Badges connus</h2>
      {data && data.badges.length === 0 ? (
        <p className="empty">Aucun badge connu du tableau de bord. Autorisez-en un ci-dessus, ou passez un badge accepté devant le lecteur.</p>
      ) : (
        <div className="table-wrap">
          <table>
            <thead>
              <tr><th>Badge</th><th>Origine</th><th>Dernier passage</th><th className="num">Acceptés</th><th className="num">Refusés</th><th><span className="sr">Action</span></th></tr>
            </thead>
            <tbody>
              {(data?.badges ?? []).map((b) => (
                <tr key={b.uid}>
                  <td className="mono">{b.uid}</td>
                  <td>{b.source === "dashboard" ? "Ajouté depuis le tableau de bord" : "Vu au lecteur"}</td>
                  <td>{b.last_used ? ago(b.last_used) : <span className="muted">jamais utilisé</span>}</td>
                  <td className="num mono">{b.granted}</td>
                  <td className="num mono">{b.refused}</td>
                  <td className="num">
                    {confirm === b.uid ? (
                      <span className="confirm">
                        <span className="small">
                          {data.known_count === 1 ? "Dernier badge connu : l'alarme ne pourra plus être désarmée au lecteur (seulement d'ici). " : ""}Retirer ce badge ?
                        </span>
                        <button className="btn-danger" disabled={busy} onClick={() => run("badge_del", b.uid, `Badge ${b.uid} retiré.`)}>Oui, retirer</button>
                        <button className="link" onClick={() => setConfirm(null)}>Annuler</button>
                      </span>
                    ) : (
                      <button className="btn-ack" disabled={busy || !enabled} onClick={() => { setConfirm(b.uid); setMsg(null); }}>Retirer</button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <p className="small muted badges-foot">
        Chaque passage devant le lecteur, accepté ou refusé, est conservé avec sa photo dans le{" "}
        <button className="link" onClick={() => go("/alertes")}>journal des passages</button>.
      </p>
    </div>
  );
}
