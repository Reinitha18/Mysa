import { useEffect, useRef, useState } from "react";
import { cameraViewSocketUrl } from "../api";

// Caméra en direct : reçoit les images relayées par le hub (WebSocket /ws/camera/view) et affiche
// la dernière. Aucune image n'est enregistrée. Le flux vient du téléphone via camera/index.html.
const STALE_MS = 8000; // au-delà, on considère le flux interrompu

export default function CameraLive() {
  const [frame, setFrame] = useState(null); // { jpeg, ts }
  const [online, setOnline] = useState(false);
  const lastRef = useRef(0);

  useEffect(() => {
    let ws, retry, closed = false;
    const connect = () => {
      ws = new WebSocket(cameraViewSocketUrl());
      ws.onmessage = (ev) => {
        try {
          const f = JSON.parse(ev.data);
          if (f.jpeg) { setFrame(f); lastRef.current = Date.now(); setOnline(true); }
        } catch { /* image ignorée */ }
      };
      ws.onclose = () => { if (!closed) retry = setTimeout(connect, 3000); };
      ws.onerror = () => ws.close();
    };
    connect();
    const t = setInterval(() => {
      if (lastRef.current && Date.now() - lastRef.current > STALE_MS) setOnline(false);
    }, 2000);
    return () => { closed = true; clearTimeout(retry); clearInterval(t); ws && ws.close(); };
  }, []);

  return (
    <section className="panel camera-live" aria-labelledby="camera-title">
      <div className="control-head">
        <h2 id="camera-title">Caméra en direct</h2>
        <span className={`pill ${online ? "pill-live" : "pill-off"}`}>{online ? "En direct" : "Hors ligne"}</span>
      </div>
      <div className="camera-frame">
        {frame?.jpeg ? (
          <img src={frame.jpeg} alt="Image en direct de la caméra du téléphone" />
        ) : (
          <p className="muted">Aucun flux. Ouvrez <span className="mono">/camera/</span> sur le téléphone (HTTPS) et appuyez sur « Démarrer ».</p>
        )}
      </div>
    </section>
  );
}
