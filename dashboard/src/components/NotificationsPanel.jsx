import { useEffect, useState } from "react";
import { getNotificationSettings, getNotifications, saveNotificationSettings, testNotifications } from "../api";

const HIDDEN = "Déjà enregistré — laisser vide pour conserver";

const EMAIL_FIELDS = [
  ["smtp_host", "Serveur SMTP", "text", "smtp.gmail.com"],
  ["smtp_port", "Port", "text", "587"],
  ["smtp_user", "Utilisateur", "text", "votre compte"],
  ["smtp_password", "Mot de passe", "password", "mot de passe d'application"],
  ["smtp_from", "Expéditeur (facultatif)", "text", "identique à l'utilisateur si vide"],
  ["smtp_to", "Destinataire(s)", "text", "vous@exemple.com"],
];
const SMS_FIELDS = [
  ["sms_url", "URL de la passerelle", "text", "http://192.168.x.x:8080/message"],
  ["sms_user", "Utilisateur (facultatif)", "text", ""],
  ["sms_password", "Mot de passe (facultatif)", "password", ""],
  ["sms_to", "Numéro(s)", "text", "+33600000000"],
];
const SECRET_FIELDS = new Set(["smtp_password", "sms_password"]);
const EMPTY_FORM = Object.fromEntries([...EMAIL_FIELDS, ...SMS_FIELDS].map(([k]) => [k, ""]));

// Configuration des canaux de notification (e-mail SMTP, SMS par passerelle Android), avec repli sur
// le .env du hub quand un champ n'est pas renseigné ici (engine/notify.py). Les mots de passe ne
// quittent jamais le serveur une fois enregistrés : un champ secret, affiché vide, garde sa valeur
// tant qu'on ne tape rien dedans (voir le texte indicatif à la place d'un astérisque).
export default function NotificationsPanel() {
  const [state, setState] = useState(null);
  const [settings, setSettings] = useState(null); // dernière réponse de l'API : {champ texte: string, champ secret: bool}
  const [form, setForm] = useState(EMPTY_FORM);   // ce que la personne tape ; les secrets partent toujours vides
  const [results, setResults] = useState(null);
  const [busy, setBusy] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    getNotifications().then(setState, (err) => setError(err.message));
    getNotificationSettings().then((s) => {
      setSettings(s);
      setForm({ ...EMPTY_FORM, ...s, smtp_password: "", sms_password: "" });
    }, (err) => setError(err.message));
  }, []);

  const change = (key) => (e) => setForm((f) => ({ ...f, [key]: e.target.value }));

  const save = async () => {
    setSaving(true);
    setSaved(null);
    try {
      const fresh = await saveNotificationSettings(form);
      setSettings(fresh);
      setForm({ ...EMPTY_FORM, ...fresh, smtp_password: "", sms_password: "" });
      setSaved({ ok: true, text: "Réglages enregistrés." });
      getNotifications().then(setState, () => {});
    } catch (err) {
      setSaved({ ok: false, text: err.message });
    } finally {
      setSaving(false);
    }
  };

  const runTest = async () => {
    setBusy(true);
    setError(null);
    try {
      setResults((await testNotifications()).results);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  const channels = state ? Object.entries(state.channels) : [];

  const Field = ([key, label, type, placeholder]) => (
    <label className="field" key={key}>
      {label}
      <input type={type} value={form[key]} onChange={change(key)} autoComplete="off"
             placeholder={SECRET_FIELDS.has(key) && settings?.[key] ? HIDDEN : placeholder}
             maxLength={type === "password" ? 200 : 300} />
    </label>
  );

  return (
    <section className="panel notifications" aria-labelledby="notif-title">
      <div className="control-head">
        <h2 id="notif-title">Notifications</h2>
        {state && <span className={`pill ${state.enabled ? "" : "pill-off"}`}>{state.enabled ? "Activées" : "Coupées (MYSA_NOTIFY=0)"}</span>}
      </div>
      <p className="muted small">
        Alertes critiques seulement, une par épisode : alarme, intrusion, lecteur de badges bloqué, surchauffe, nœud
        hors ligne. Un champ laissé vide ici garde la valeur du <span className="mono">.env</span> du hub, s'il y en a une.
      </p>

      <div className="notif-form">
        <fieldset>
          <legend>E-mail (SMTP)</legend>
          <div className="form-row">{EMAIL_FIELDS.map(Field)}</div>
        </fieldset>
        <fieldset>
          <legend>SMS (passerelle sur un téléphone Android)</legend>
          <div className="form-row">{SMS_FIELDS.map(Field)}</div>
        </fieldset>
        <div className="notif-save">
          <button className="btn-primary" disabled={saving || !settings} onClick={save}>{saving ? "Enregistrement…" : "Enregistrer"}</button>
          {saved && <span className={`small ${saved.ok ? "ack-note" : "error"}`} role="status">{saved.text}</span>}
        </div>
      </div>

      <h3>État des canaux</h3>
      <ul className="channels">
        {channels.map(([name, on]) => (
          <li key={name}>
            <span>{name}</span>
            <span className={`pill ${on ? "" : "pill-off"}`}>{on ? "configuré" : "non configuré"}</span>
            {results?.[name] && <span className={`small ${results[name] === "envoyé" ? "" : "muted"}`}>{results[name]}</span>}
          </li>
        ))}
      </ul>
      <button className="btn-ack" onClick={runTest} disabled={busy || !channels.some(([, on]) => on)}>
        {busy ? "Envoi…" : "Envoyer une notification de test"}
      </button>
      {error && <p className="small login-error" role="alert">{error}</p>}
    </section>
  );
}
