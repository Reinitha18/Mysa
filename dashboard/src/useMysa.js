import { useCallback, useEffect, useRef, useState } from "react";
import { alertsSocketUrl, getDevices, getEpisodes, getHistory, getHouses, getSensorMeta, getStreams } from "./api";
import { setCatalog } from "./labels";

const POLL_MS = 4000;

// État partagé du dashboard : appareils (avec risque), flux, épisodes, dernière valeur de chaque
// capteur, état de la connexion temps réel et notifications des nouveaux épisodes.
export function useMysa() {
  const [data, setData] = useState({ devices: [], streams: [], episodes: [], latest: {}, houses: [], loaded: false });
  const [apiError, setApiError] = useState(null);
  const [live, setLive] = useState(false);
  const [pulse, setPulse] = useState(0);
  const [toasts, setToasts] = useState([]);
  const lastCount = useRef(null);
  const seenEpisodes = useRef(new Set());

  const refresh = useCallback(async () => {
    try {
      const [devices, streams, episodes, houses, sensorMeta] = await Promise.all([
        getDevices(), getStreams(), getEpisodes(300), getHouses().catch(() => []), getSensorMeta().catch(() => ({})),
      ]);
      setCatalog(devices, sensorMeta); // avant setData : le rendu suivant utilise déjà les noms saisis
      const histories = await Promise.all(devices.map((d) => getHistory(d.device_id, 40).catch(() => [])));
      const latest = {};
      devices.forEach((d, i) => {
        const perSensor = {};
        for (const row of histories[i]) if (!perSensor[row.sensor]) perSensor[row.sensor] = row; // plus récent d'abord
        latest[d.device_id] = perSensor;
      });
      const count = streams.reduce((n, s) => n + (s.message_count || 0), 0);
      if (lastCount.current !== null && count > lastCount.current) setPulse((p) => p + 1);
      lastCount.current = count;
      episodes.forEach((e) => seenEpisodes.current.add(e.id));
      setData({ devices, streams, episodes, latest, houses, loaded: true });
      setApiError(null);
    } catch (err) {
      setApiError(err.message || String(err));
    }
  }, []);

  useEffect(() => {
    refresh();
    const t = setInterval(refresh, POLL_MS);
    return () => clearInterval(t);
  }, [refresh]);

  const dismiss = useCallback((id) => setToasts((all) => all.filter((t) => t.id !== id)), []);

  useEffect(() => {
    let ws;
    let retry;
    let closed = false;
    const connect = () => {
      ws = new WebSocket(alertsSocketUrl());
      ws.onopen = () => setLive(true);
      ws.onclose = () => {
        setLive(false);
        if (!closed) retry = setTimeout(connect, 3000);
      };
      ws.onmessage = (ev) => {
        const alert = JSON.parse(ev.data);
        if (alert.episode_id && !seenEpisodes.current.has(alert.episode_id)) {
          seenEpisodes.current.add(alert.episode_id);
          const toast = { id: alert.episode_id, alert };
          setToasts((all) => [toast, ...all].slice(0, 4));
          setTimeout(() => dismiss(toast.id), 12000);
        }
        refresh();
      };
    };
    connect();
    return () => {
      closed = true;
      clearTimeout(retry);
      ws && ws.close();
    };
  }, [refresh, dismiss]);

  return { ...data, apiError, live, pulse, toasts, dismiss, refresh };
}

// État global de la maison, à partir du pire appareil.
export function houseState(devices) {
  const worst = devices.reduce((w, d) => (d.risk > (w?.risk ?? -1) ? d : w), null);
  if (!worst || worst.level === "normal") return { tone: "calm", worst };
  return { tone: worst.level === "critique" ? "alert" : "watch", worst };
}
