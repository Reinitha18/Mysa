import { useEffect, useRef, useState } from "react";
import { describeEpisode, deviceName, sensorLabel } from "../labels";

// Pastille d'état : la couleur est toujours doublée d'un libellé (lisible sans distinguer les couleurs).
export function Status({ level, label }) {
  const tone = level === "critique" ? "alert" : level === "à surveiller" ? "watch" : "calm";
  return (
    <span className={`status tone-${label === "Silencieux" ? "watch" : tone}`}>
      <i aria-hidden="true" />
      {label}
    </span>
  );
}

export function RiskRing({ score, level, size = 112 }) {
  const r = 44;
  const c = 2 * Math.PI * r;
  const tone = level === "critique" ? "alert" : level === "à surveiller" ? "watch" : "calm";
  return (
    <svg className={`ring tone-${tone}`} width={size} height={size} viewBox="0 0 100 100" role="img"
         aria-label={`Score de risque : ${score} sur 100`}>
      <circle cx="50" cy="50" r={r} className="ring-track" />
      <circle cx="50" cy="50" r={r} className="ring-value" strokeDasharray={`${(c * score) / 100} ${c}`}
              transform="rotate(-90 50 50)" />
      <text x="50" y="50" className="ring-score">{score}</text>
      <text x="50" y="68" className="ring-max">/ 100</text>
    </svg>
  );
}

export function Toasts({ toasts, dismiss, go }) {
  return (
    <div className="toasts" role="status" aria-live="polite">
      {toasts.map(({ id, alert }) => (
        <Toast key={id} alert={alert} onClose={() => dismiss(id)} go={go} />
      ))}
    </div>
  );
}

function Toast({ alert, onClose, go }) {
  useEffect(() => {
    const onKey = (e) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);
  const tone = alert.kind === "notice" ? "calm" : alert.severity === "high" ? "alert" : "watch";
  const title = alert.kind === "notice" ? "Avis" : alert.kind === "silence" ? "Appareil silencieux" : "Nouvelle alerte";
  return (
    <div className={`toast tone-${tone}`}>
      <div>
        <strong>{title} · {deviceName(alert.device_id)}</strong>
        <p>{sensorLabel(alert.sensor)} : {describeEpisode(alert)}</p>
      </div>
      <div className="toast-actions">
        <button className="link" onClick={() => { go(`/appareil/${encodeURIComponent(alert.device_id)}`); onClose(); }}>
          Voir
        </button>
        <button className="icon" onClick={onClose} aria-label="Fermer la notification">×</button>
      </div>
    </div>
  );
}

// Compteur qui monte jusqu'à sa valeur (désactivé si l'utilisateur réduit les animations).
export function CountUp({ value, duration = 900 }) {
  const [shown, setShown] = useState(0);
  const from = useRef(0);
  useEffect(() => {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) { setShown(value); return; }
    const start = performance.now(), a = from.current;
    let raf;
    const tick = (t) => {
      const p = Math.min(1, (t - start) / duration);
      setShown(Math.round(a + (value - a) * (1 - Math.pow(1 - p, 3))));
      if (p < 1) raf = requestAnimationFrame(tick); else from.current = value;
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [value, duration]);
  return <>{shown}</>;
}
