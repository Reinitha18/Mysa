import { useCallback, useEffect, useState } from "react";
import {
  createDevice, createHouse, createSensor, deleteDevice, deleteHouse, deleteSensor, getSensors,
  updateDevice, updateHouse, updateSensor,
} from "../api";
import { deviceKind, deviceName, sensorLabel } from "../labels";

function useFlash() {
  const [flash, setFlash] = useState(null);
  const run = async (action, okText) => {
    setFlash(null);
    try {
      await action();
      setFlash({ ok: true, text: okText });
      return true;
    } catch (err) {
      setFlash({ ok: false, text: err.message });
      return false;
    }
  };
  return [flash, run];
}

const Flash = ({ flash }) => flash && (
  <p className={`small ${flash.ok ? "ack-note" : "error"}`} role="status">{flash.text}</p>
);

// Confirmation en ligne d'une suppression (pas de fenêtre du navigateur).
function Confirm({ text, onYes, onNo }) {
  return (
    <span className="confirm">
      <span className="small">{text}</span>
      <button className="btn-danger" onClick={onYes}>Oui, supprimer</button>
      <button className="link" onClick={onNo}>Annuler</button>
    </span>
  );
}

function HousesPanel({ houses, refresh }) {
  const [editing, setEditing] = useState(null);
  const [confirm, setConfirm] = useState(null);
  const [form, setForm] = useState({ name: "", address: "" });
  const [flash, run] = useFlash();

  const add = async (e) => {
    e.preventDefault();
    if (await run(() => createHouse(form), `Maison « ${form.name.trim()} » ajoutée.`)) { setForm({ name: "", address: "" }); refresh(); }
  };
  const save = async (e) => {
    e.preventDefault();
    if (await run(() => updateHouse(editing.id, { name: editing.name, address: editing.address }), "Maison modifiée.")) { setEditing(null); refresh(); }
  };
  const remove = async (house) => {
    if (await run(() => deleteHouse(house.id), `Maison « ${house.name} » supprimée.`)) { setConfirm(null); refresh(); }
  };

  return (
    <section className="panel" aria-labelledby="houses-title">
      <h2 id="houses-title">Maisons</h2>
      <ul className="manage-list">
        {houses.map((h) => (
          <li key={h.id} className="manage-row">
            {editing?.id === h.id ? (
              <form className="form-row" onSubmit={save}>
                <label className="field">Nom
                  <input value={editing.name} onChange={(e) => setEditing({ ...editing, name: e.target.value })} maxLength={60} required autoFocus />
                </label>
                <label className="field">Adresse
                  <input value={editing.address ?? ""} onChange={(e) => setEditing({ ...editing, address: e.target.value })} maxLength={200} />
                </label>
                <button className="btn-primary" type="submit">Enregistrer</button>
                <button className="link" type="button" onClick={() => setEditing(null)}>Annuler</button>
              </form>
            ) : (
              <>
                <span className="manage-main">
                  <strong>{h.name}</strong>
                  {h.address && <span className="muted small">{h.address}</span>}
                </span>
                <span className="pill">{h.device_count} appareil{h.device_count > 1 ? "s" : ""}</span>
                {confirm === h.id ? (
                  <Confirm text={h.device_count ? "Ses appareils passeront à la première maison. Supprimer ?" : "Supprimer cette maison ?"}
                           onYes={() => remove(h)} onNo={() => setConfirm(null)} />
                ) : (
                  <span className="row-actions">
                    <button className="btn-ack" onClick={() => setEditing({ id: h.id, name: h.name, address: h.address })}>Modifier</button>
                    <button className="btn-ack" disabled={houses.length <= 1} onClick={() => setConfirm(h.id)}
                            title={houses.length <= 1 ? "Il faut garder au moins une maison" : undefined}>Supprimer</button>
                  </span>
                )}
              </>
            )}
          </li>
        ))}
      </ul>
      <form className="form-row" onSubmit={add}>
        <label className="field">Nouvelle maison
          <input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} maxLength={60} placeholder="Maison de campagne" required />
        </label>
        <label className="field">Adresse (facultatif)
          <input value={form.address} onChange={(e) => setForm({ ...form, address: e.target.value })} maxLength={200} />
        </label>
        <button className="btn-primary" type="submit" disabled={!form.name.trim()}>Ajouter</button>
      </form>
      <Flash flash={flash} />
    </section>
  );
}

function statusOf(d) {
  if (d.waiting) return "En attente";
  if (d.online === false) return "Hors ligne";
  if (d.online === true) return "En ligne";
  return "—";
}

function DevicesPanel({ devices, houses, refresh, selected, onSelect }) {
  const [houseFilter, setHouseFilter] = useState("");
  const [editing, setEditing] = useState(null);
  const [confirm, setConfirm] = useState(null);
  const [form, setForm] = useState({ device_id: "", name: "", kind: "", house_id: "" });
  const [flash, run] = useFlash();
  const houseName = (id) => houses.find((h) => h.id === id)?.name ?? "—";
  const rows = devices.filter((d) => !houseFilter || d.house_id === Number(houseFilter));

  const add = async (e) => {
    e.preventDefault();
    const body = { device_id: form.device_id.trim(), name: form.name, kind: form.kind || null, house_id: form.house_id ? Number(form.house_id) : null };
    if (await run(() => createDevice(body), `Appareil « ${form.name.trim()} » ajouté.`)) {
      setForm({ device_id: "", name: "", kind: "", house_id: form.house_id });
      refresh();
    }
  };
  const save = async (e) => {
    e.preventDefault();
    if (await run(() => updateDevice(editing.id, { name: editing.name, kind: editing.kind }), "Appareil modifié.")) { setEditing(null); refresh(); }
  };
  const move = async (d, houseId) => {
    if (await run(() => updateDevice(d.device_id, { house_id: Number(houseId) }), `${deviceName(d.device_id)} déplacé vers « ${houseName(Number(houseId))} ».`)) refresh();
  };
  const remove = async (d) => {
    if (await run(() => deleteDevice(d.device_id), `Appareil ${deviceName(d.device_id)} supprimé.`)) {
      setConfirm(null);
      if (selected === d.device_id) onSelect(null);
      refresh();
    }
  };

  return (
    <section className="panel" aria-labelledby="devices-title">
      <div className="control-head">
        <h2 id="devices-title">Appareils</h2>
        {houses.length > 1 && (
          <label className="select">
            <span>Maison</span>
            <select value={houseFilter} onChange={(e) => setHouseFilter(e.target.value)}>
              <option value="">Toutes</option>
              {houses.map((h) => <option key={h.id} value={h.id}>{h.name}</option>)}
            </select>
          </label>
        )}
      </div>
      {rows.length === 0 ? <p className="empty">Aucun appareil.</p> : (
        <div className="table-wrap">
          <table className="manage-table">
            <thead>
              <tr><th>Appareil</th><th>Type</th><th>Maison</th><th>État</th><th><span className="sr">Actions</span></th></tr>
            </thead>
            <tbody>
              {rows.map((d) => (
                <tr key={d.device_id} className={selected === d.device_id ? "is-open" : ""}>
                  {editing?.id === d.device_id ? (
                    <td colSpan={5}>
                      <form className="form-row" onSubmit={save}>
                        <label className="field">Nom
                          <input value={editing.name} onChange={(e) => setEditing({ ...editing, name: e.target.value })} maxLength={60} required autoFocus />
                        </label>
                        <label className="field">Type
                          <input value={editing.kind} onChange={(e) => setEditing({ ...editing, kind: e.target.value })} maxLength={60} />
                        </label>
                        <button className="btn-primary" type="submit">Enregistrer</button>
                        <button className="link" type="button" onClick={() => setEditing(null)}>Annuler</button>
                      </form>
                    </td>
                  ) : (
                    <>
                      <td><strong>{deviceName(d.device_id)}</strong><br /><span className="mono muted small">{d.device_id}</span></td>
                      <td>{deviceKind(d.device_id)}</td>
                      <td>
                        <select aria-label={`Maison de ${deviceName(d.device_id)}`} value={d.house_id ?? ""} onChange={(e) => move(d, e.target.value)}>
                          {houses.map((h) => <option key={h.id} value={h.id}>{h.name}</option>)}
                        </select>
                      </td>
                      <td>{statusOf(d)}{d.simulated && <span className="pill pill-sim"> Simulé</span>}</td>
                      <td className="num">
                        {confirm === d.device_id ? (
                          <Confirm text="Efface aussi tout son historique. Supprimer ?" onYes={() => remove(d)} onNo={() => setConfirm(null)} />
                        ) : (
                          <span className="row-actions">
                            <button className="btn-ack" aria-pressed={selected === d.device_id}
                                    onClick={() => onSelect(selected === d.device_id ? null : d.device_id)}>Capteurs</button>
                            <button className="btn-ack" onClick={() => setEditing({ id: d.device_id, name: deviceName(d.device_id), kind: d.kind ?? "" })}>Modifier</button>
                            <button className="btn-ack" onClick={() => setConfirm(d.device_id)}>Supprimer</button>
                          </span>
                        )}
                      </td>
                    </>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <h3>Ajouter un appareil</h3>
      <form className="form-row" onSubmit={add}>
        <label className="field">Nom
          <input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} maxLength={60} placeholder="Prise du salon" required />
        </label>
        <label className="field">Identifiant MQTT
          <input value={form.device_id} onChange={(e) => setForm({ ...form, device_id: e.target.value })} maxLength={40}
                 placeholder="esp32-cmf-02" pattern="[A-Za-z0-9][A-Za-z0-9_\-]{1,39}" title="Lettres, chiffres, - et _ (2 à 40 caractères)" required />
        </label>
        <label className="field">Type (facultatif)
          <input value={form.kind} onChange={(e) => setForm({ ...form, kind: e.target.value })} maxLength={60} placeholder="Prise commandée" />
        </label>
        {houses.length > 1 && (
          <label className="field">Maison
            <select value={form.house_id} onChange={(e) => setForm({ ...form, house_id: e.target.value })}>
              <option value="">{houses[0]?.name}</option>
              {houses.slice(1).map((h) => <option key={h.id} value={h.id}>{h.name}</option>)}
            </select>
          </label>
        )}
        <button className="btn-primary" type="submit" disabled={!form.name.trim() || !form.device_id.trim()}>Ajouter</button>
      </form>
      <Flash flash={flash} />
    </section>
  );
}

function SensorsPanel({ deviceId, refresh }) {
  const [sensors, setSensors] = useState(null);
  const [editing, setEditing] = useState(null);
  const [confirm, setConfirm] = useState(null);
  const [form, setForm] = useState({ sensor: "", label: "", unit: "" });
  const [flash, run] = useFlash();
  const load = useCallback(() => getSensors(deviceId).then(setSensors, () => setSensors([])), [deviceId]);
  useEffect(() => { setSensors(null); setEditing(null); setConfirm(null); load(); }, [load]);
  const done = () => { load(); refresh(); };

  const add = async (e) => {
    e.preventDefault();
    if (await run(() => createSensor(deviceId, { sensor: form.sensor.trim(), label: form.label, unit: form.unit }), "Capteur ajouté.")) {
      setForm({ sensor: "", label: "", unit: "" });
      done();
    }
  };
  const save = async (e) => {
    e.preventDefault();
    if (await run(() => updateSensor(deviceId, editing.sensor, { label: editing.label, unit: editing.unit }), "Capteur modifié.")) { setEditing(null); done(); }
  };
  const remove = async (s) => {
    if (await run(() => deleteSensor(deviceId, s.sensor), `Capteur ${sensorLabel(s.sensor, deviceId)} supprimé.`)) { setConfirm(null); done(); }
  };

  return (
    <section className="panel" aria-labelledby="sensors-title">
      <h2 id="sensors-title">Capteurs de {deviceName(deviceId)}</h2>
      {sensors === null ? <p className="muted">Chargement…</p> : sensors.length === 0 ? <p className="empty">Aucun capteur.</p> : (
        <div className="table-wrap">
          <table className="manage-table">
            <thead>
              <tr><th>Clé</th><th>Nom</th><th>Unité</th><th>État</th><th><span className="sr">Actions</span></th></tr>
            </thead>
            <tbody>
              {sensors.map((s) => (
                <tr key={s.sensor}>
                  <td className="mono">{s.sensor}</td>
                  {editing?.sensor === s.sensor ? (
                    <td colSpan={4}>
                      <form className="form-row" onSubmit={save}>
                        <label className="field">Nom
                          <input value={editing.label} onChange={(e) => setEditing({ ...editing, label: e.target.value })} maxLength={60} autoFocus />
                        </label>
                        <label className="field">Unité
                          <input value={editing.unit} onChange={(e) => setEditing({ ...editing, unit: e.target.value })} maxLength={16} />
                        </label>
                        <button className="btn-primary" type="submit">Enregistrer</button>
                        <button className="link" type="button" onClick={() => setEditing(null)}>Annuler</button>
                      </form>
                    </td>
                  ) : (
                    <>
                      <td>{sensorLabel(s.sensor, deviceId)}</td>
                      <td>{s.unit ?? <span className="muted">—</span>}</td>
                      <td>{s.discovered ? (s.silent ? "Silencieux" : "Actif") : "Déclaré, sans mesure"}</td>
                      <td className="num">
                        {confirm === s.sensor ? (
                          <Confirm text={s.discovered ? "Efface aussi ses mesures et alertes. Supprimer ?" : "Supprimer ce capteur ?"}
                                   onYes={() => remove(s)} onNo={() => setConfirm(null)} />
                        ) : (
                          <span className="row-actions">
                            <button className="btn-ack" onClick={() => setEditing({ sensor: s.sensor, label: s.label ?? "", unit: s.unit ?? "" })}>Modifier</button>
                            <button className="btn-ack" onClick={() => setConfirm(s.sensor)}>Supprimer</button>
                          </span>
                        )}
                      </td>
                    </>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <h3>Ajouter un capteur</h3>
      <form className="form-row" onSubmit={add}>
        <label className="field">Clé MQTT
          <input value={form.sensor} onChange={(e) => setForm({ ...form, sensor: e.target.value })} maxLength={40} placeholder="co2"
                 pattern="[A-Za-z0-9][A-Za-z0-9_\-]{0,39}" title="Lettres, chiffres, - et _" required />
        </label>
        <label className="field">Nom
          <input value={form.label} onChange={(e) => setForm({ ...form, label: e.target.value })} maxLength={60} placeholder="Taux de CO2" />
        </label>
        <label className="field">Unité
          <input value={form.unit} onChange={(e) => setForm({ ...form, unit: e.target.value })} maxLength={16} placeholder="ppm" />
        </label>
        <button className="btn-primary" type="submit" disabled={!form.sensor.trim()}>Ajouter</button>
      </form>
      <Flash flash={flash} />
    </section>
  );
}

// Gestion : maisons, appareils et capteurs (créer, modifier, supprimer). Reçoit toutes les maisons,
// pas seulement celle affichée sur l'accueil.
export default function Manage({ mysa }) {
  const { devices, houses, refresh } = mysa;
  const [selected, setSelected] = useState(null);
  return (
    <div className="page manage">
      <header className="page-head"><h1>Gestion</h1></header>
      <HousesPanel houses={houses} refresh={refresh} />
      <DevicesPanel devices={devices} houses={houses} refresh={refresh} selected={selected} onSelect={setSelected} />
      {selected && <SensorsPanel deviceId={selected} refresh={refresh} />}
    </div>
  );
}
