import { useEffect, useState } from "react";
import { accessCaptureUrl, getAccessLog } from "../api";
import { ago, clock, deviceName } from "../labels";

// Journal des passages de badge (accepté ou refusé) avec la photo prise par la caméra du téléphone
// à cet instant, pour vérifier après coup qui s'est présenté (api/routes/camera.py, capture_loop).
export default function AccessLog({ pulse }) {
  const [rows, setRows] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    getAccessLog(20).then((r) => { setRows(r); setError(null); }, (err) => setError(err.message));
  }, [pulse]);

  return (
    <section className="panel access-log" aria-labelledby="access-title">
      <h2 id="access-title">Passages de badge</h2>
      <p className="muted small">
        Chaque badge présenté, accepté ou refusé, avec la photo de la caméra du téléphone à cet instant.
        Un refus isolé n'est pas une alerte ; trois refus en une minute en sont une, et au cinquième
        le lecteur se bloque.
      </p>
      {error && <p className="error">Journal indisponible : {error}</p>}
      {rows && rows.length === 0 && <p className="empty">Aucun badge présenté pour l'instant.</p>}
      {rows && rows.length > 0 && (
        <ul className="access-list">
          {rows.map((a) => (
            <li key={a.id} className={a.granted ? "" : "is-refused"}>
              {a.has_capture ? (
                <a href={accessCaptureUrl(a.id)} target="_blank" rel="noreferrer" title="Agrandir la photo">
                  <img src={accessCaptureUrl(a.id)} alt={`Photo du passage de ${clock(a.ts)}`} loading="lazy" />
                </a>
              ) : (
                <span className="no-capture">{a.has_capture === null ? "photo…" : "pas de caméra"}</span>
              )}
              <div>
                <span className={`pill ${a.granted ? "" : "pill-on"}`}>{a.granted ? "Accepté" : "Refusé"}</span>
                <p className="small"><span className="mono">{a.uid ?? "UID inconnu"}</span> · {deviceName(a.device_id)}</p>
                <p className="muted small">{clock(a.ts)} · {ago(a.ts)}</p>
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
