import { useState } from "react";
import { getPref, setPref } from "../theme";

const ICONS = {
  light: <path d="M12 7a5 5 0 1 0 0 10 5 5 0 0 0 0-10Zm0-5v3m0 14v3M2 12h3m14 0h3M4.9 4.9 7 7m10 10 2.1 2.1M19.1 4.9 17 7M7 17l-2.1 2.1" />,
  dark: <path d="M20 14.5A8.5 8.5 0 0 1 9.5 4a8.5 8.5 0 1 0 10.5 10.5Z" />,
  auto: <path d="M12 3a9 9 0 1 0 0 18V3Zm0 0a9 9 0 0 1 0 18" />,
};
const LABELS = { light: "Thème clair", dark: "Thème sombre", auto: "Thème automatique (suit le système)" };

export default function ThemeToggle() {
  const [pref, setLocal] = useState(getPref);
  const choose = (p) => { setPref(p); setLocal(p); };
  return (
    <div className="theme-toggle" role="group" aria-label="Apparence">
      {["light", "dark", "auto"].map((p) => (
        <button key={p} type="button" aria-pressed={pref === p} aria-label={LABELS[p]} title={LABELS[p]} onClick={() => choose(p)}>
          <svg viewBox="0 0 24 24" width="16" height="16" fill={p === "auto" ? "currentColor" : "none"} stroke="currentColor"
               strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{ICONS[p]}</svg>
        </button>
      ))}
    </div>
  );
}
