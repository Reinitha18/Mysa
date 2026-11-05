import { useState } from "react";
import { login } from "../api";

// Écran de connexion (MYSA_DASHBOARD_PASSWORD, api/auth.py). Le cookie de session est posé par l'API ;
// il ouvre aussi l'accès à la page caméra du téléphone, servie par le même hub.
export default function Login({ onDone }) {
  const [password, setPassword] = useState("");
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await login(password);
      onDone();
    } catch (err) {
      setError(err.message);
      setBusy(false);
    }
  };

  return (
    <main className="login" id="main">
      <form className="panel login-card" onSubmit={submit}>
        <img src={`${import.meta.env.BASE_URL}mysa-logo.png`} alt="Mysa" />
        <h1>Connexion</h1>
        <p className="muted small">Le tableau de bord commande la serrure et l'alarme : il est réservé aux occupants.</p>
        <label>
          Mot de passe
          <input type="password" value={password} onChange={(e) => setPassword(e.target.value)}
                 autoComplete="current-password" autoFocus required />
        </label>
        {error && <p className="login-error" role="alert">{error}</p>}
        <button className="btn-primary" type="submit" disabled={busy || !password}>
          {busy ? "Connexion…" : "Se connecter"}
        </button>
      </form>
    </main>
  );
}
