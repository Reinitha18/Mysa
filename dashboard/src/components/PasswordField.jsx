import { useState } from "react";

// Champ mot de passe avec bouton « afficher/masquer » (œil). Mêmes props qu'un <input>.
export default function PasswordField({ id, value, onChange, autoComplete, required, autoFocus, ariaInvalid }) {
  const [shown, setShown] = useState(false);
  return (
    <span className="password-field">
      <input id={id} type={shown ? "text" : "password"} value={value} onChange={onChange}
             autoComplete={autoComplete} required={required} autoFocus={autoFocus} aria-invalid={ariaInvalid} />
      <button type="button" className="password-toggle" onClick={() => setShown((v) => !v)}
              aria-label={shown ? "Masquer le mot de passe" : "Afficher le mot de passe"} aria-pressed={shown}>
        {shown ? (
          <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <path d="M3 3l18 18M10.6 10.6a2 2 0 0 0 2.8 2.8M9.4 5.5A10.6 10.6 0 0 1 12 5c5 0 9 4 10 7a11.7 11.7 0 0 1-2.9 4.1M6.6 6.6C4.3 8.2 2.7 10.3 2 12c.7 1.8 2.2 3.8 4.3 5.3A10.7 10.7 0 0 0 12 19c1 0 2-.1 2.9-.4" />
          </svg>
        ) : (
          <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <path d="M2 12c1-3 5-7 10-7s9 4 10 7c-1 3-5 7-10 7s-9-4-10-7Z" />
            <circle cx="12" cy="12" r="3" />
          </svg>
        )}
      </button>
    </span>
  );
}
