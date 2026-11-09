import { useCallback, useEffect, useState } from "react";
import { changePassword, deleteUser, getUsers, register } from "../api";
import NotificationsPanel from "../components/NotificationsPanel";
import PasswordField from "../components/PasswordField";

const MIN_PASSWORD = 8;
const EMAIL_RE = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;

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

// Message d'aide affiché sous un champ, seulement une fois que la personne a commencé à taper.
const Hint = ({ show, text }) => show && <p className="small field-hint" role="alert">{text}</p>;

// Création d'un compte : e-mail, mot de passe et confirmation. Le mot de passe est haché côté API (PBKDF2).
function AccountForm({ onCreate, submitLabel }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [flash, run] = useFlash();
  const emailInvalid = email !== "" && !EMAIL_RE.test(email);
  const tooShort = password !== "" && password.length < MIN_PASSWORD;
  const mismatch = confirm !== "" && confirm !== password;
  const valid = EMAIL_RE.test(email) && password.length >= MIN_PASSWORD && password === confirm;
  const submit = async (e) => {
    e.preventDefault();
    if (await run(() => onCreate(email, password), "Compte créé.")) { setEmail(""); setPassword(""); setConfirm(""); }
  };
  return (
    <form className="account-form" onSubmit={submit}>
      <label className="field">Adresse e-mail
        <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="off"
               aria-invalid={emailInvalid} required />
      </label>
      <Hint show={emailInvalid} text="Adresse e-mail invalide." />
      <label className="field">Mot de passe ({MIN_PASSWORD} caractères minimum)
        <PasswordField value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="new-password"
                       ariaInvalid={tooShort} required />
      </label>
      <Hint show={tooShort} text={`Le mot de passe doit contenir au moins ${MIN_PASSWORD} caractères.`} />
      <label className="field">Confirmation
        <PasswordField value={confirm} onChange={(e) => setConfirm(e.target.value)} autoComplete="new-password"
                       ariaInvalid={mismatch} required />
      </label>
      <Hint show={mismatch} text="Les deux mots de passe sont différents." />
      <div><button className="btn-primary" type="submit" disabled={!valid}>{submitLabel}</button></div>
      <Flash flash={flash} />
    </form>
  );
}

function PasswordForm() {
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [flash, run] = useFlash();
  const tooShort = next !== "" && next.length < MIN_PASSWORD;
  const mismatch = confirm !== "" && confirm !== next;
  const submit = async (e) => {
    e.preventDefault();
    if (await run(() => changePassword(current, next), "Mot de passe modifié. Vos autres appareils devront se reconnecter.")) {
      setCurrent(""); setNext(""); setConfirm("");
    }
  };
  return (
    <form className="account-form" onSubmit={submit}>
      <label className="field">Mot de passe actuel
        <PasswordField value={current} onChange={(e) => setCurrent(e.target.value)} autoComplete="current-password" required />
      </label>
      <label className="field">Nouveau mot de passe ({MIN_PASSWORD} caractères minimum)
        <PasswordField value={next} onChange={(e) => setNext(e.target.value)} autoComplete="new-password" ariaInvalid={tooShort} required />
      </label>
      <Hint show={tooShort} text={`Le mot de passe doit contenir au moins ${MIN_PASSWORD} caractères.`} />
      <label className="field">Confirmation
        <PasswordField value={confirm} onChange={(e) => setConfirm(e.target.value)} autoComplete="new-password" ariaInvalid={mismatch} required />
      </label>
      <Hint show={mismatch} text="Les deux mots de passe sont différents." />
      <div>
        <button className="btn-primary" type="submit" disabled={!current || next.length < MIN_PASSWORD || next !== confirm}>
          Changer le mot de passe
        </button>
      </div>
      <Flash flash={flash} />
    </form>
  );
}

function Occupants({ onAuthChange }) {
  const [users, setUsers] = useState([]);
  const [confirm, setConfirm] = useState(null);
  const [flash, run] = useFlash();
  const load = useCallback(() => getUsers().then(setUsers, () => setUsers([])), []);
  useEffect(() => { load(); }, [load]);
  const remove = async (user) => {
    if (await run(() => deleteUser(user.id), `Compte ${user.email} supprimé.`)) {
      setConfirm(null);
      if (user.current) onAuthChange(); else load();
    }
  };
  return (
    <section className="panel" aria-labelledby="occ-title">
      <h2 id="occ-title">Occupants</h2>
      <ul className="manage-list">
        {users.map((u) => (
          <li key={u.id} className="manage-row">
            <span><strong>{u.email}</strong>{u.current && <span className="pill"> vous</span>}</span>
            {confirm === u.id ? (
              <span className="confirm">
                <span className="small">Supprimer ce compte ?</span>
                <button className="btn-danger" onClick={() => remove(u)}>Oui, supprimer</button>
                <button className="link" onClick={() => setConfirm(null)}>Annuler</button>
              </span>
            ) : (
              <button className="btn-ack" disabled={users.length <= 1} onClick={() => setConfirm(u.id)}
                      title={users.length <= 1 ? "Dernier compte : il protège le tableau de bord" : undefined}>Supprimer</button>
            )}
          </li>
        ))}
      </ul>
      <Flash flash={flash} />
      <h3>Ajouter un occupant</h3>
      <AccountForm submitLabel="Créer le compte" onCreate={async (email, pw) => { await register(email, pw); load(); }} />
    </section>
  );
}

// Le thème (clair / sombre / auto) se règle depuis la barre du haut, pas ici, pour éviter un double réglage.
export default function Settings({ auth, onAuthChange, onLogout }) {
  const loggedWithAccount = !!auth.user;
  return (
    <div className="page settings">
      <header className="page-head"><h1>Paramètres</h1></header>

      <section className="panel" aria-labelledby="account-title">
        <h2 id="account-title">Compte</h2>
        {loggedWithAccount ? (
          <>
            <p>Connecté en tant que <strong>{auth.user.email}</strong></p>
            <h3>Changer le mot de passe</h3>
            <PasswordForm />
          </>
        ) : (
          <>
            {!auth.required && (
              <p className="note note-watch">
                Accès libre : n'importe quel appareil du réseau peut commander la porte et l'alarme. Créez un compte pour protéger le tableau de bord.
              </p>
            )}
            <h3>{auth.required ? "Passer à un compte avec adresse e-mail" : "Créer le premier compte"}</h3>
            <AccountForm submitLabel="Créer le compte" onCreate={async (email, pw) => { await register(email, pw); onAuthChange(); }} />
          </>
        )}
        {onLogout && <div className="settings-logout"><button className="btn-ack" onClick={onLogout}>Se déconnecter</button></div>}
      </section>

      {auth.has_accounts && <Occupants onAuthChange={onAuthChange} />}

      <NotificationsPanel />
    </div>
  );
}
