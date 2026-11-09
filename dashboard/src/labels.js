// Vocabulaire de l'occupant : des pièces et des mesures, pas des identifiants techniques.
// Un appareil absent de cette liste est affiché sous son identifiant.

export const DEVICES = {
  "esp32-sec-01": { name: "Entrée", kind: "Nœud sécurité · ESP32" },
  "esp32-cmf-01": { name: "Salon", kind: "Nœud confort et accès · ESP32" },
  "cam-01": { name: "Caméra", kind: "Caméra du téléphone" },
  "virt-hall-01": { name: "Couloir", kind: "Détecteur de mouvement · virtuel" },
  "virt-door-01": { name: "Garage", kind: "Contact de porte · virtuel" },
  "virt-climate-01": { name: "Chambre", kind: "Thermomètre · virtuel" },
  "virt-bulb-01": { name: "Prise du séjour", kind: "Prise connectée · virtuelle" },
  "virt-plug-01": { name: "Cuisine", kind: "Prise connectée · virtuelle" },
  "virt-cam-01": { name: "Jardin", kind: "Caméra · virtuelle" },
};

const bool = (on, off) => (v) => (v >= 0.5 ? on : off);

export const SENSORS = {
  pir: { label: "Mouvement", fmt: bool("détecté", "calme"), binary: true },
  motion: { label: "Mouvement caméra", fmt: bool("détecté", "calme"), binary: true },
  door: { label: "Porte", fmt: bool("ouverte", "fermée"), binary: true },
  magnet: { label: "Porte", fmt: bool("ouverte", "fermée"), binary: true },
  temperature: { label: "Température", unit: "°C", digits: 1 },
  humidity: { label: "Humidité", unit: "%", digits: 0 },
  bulb_state: { label: "Prise", fmt: bool("allumée", "éteinte"), binary: true },
  plug_power: { label: "Consommation", unit: "W", digits: 0 },
  cam_bitrate: { label: "Débit vidéo", unit: "kbit/s", digits: 0 },
  rfid: { label: "Badge", fmt: bool("autorisé", "refusé"), binary: true },
  rfid_lockout: { label: "Lecteur de badges", fmt: (v) => (v > 0 ? "bloqué" : "actif") },
  arm: { label: "Alarme", fmt: bool("armée", "désarmée"), binary: true },
  alarm: { label: "Sirène", fmt: bool("en marche", "arrêtée"), binary: true },
  lock: { label: "Serrure", fmt: bool("ouverte", "fermée"), binary: true },
  relay: { label: "Prise commandée", fmt: bool("allumée", "éteinte"), binary: true },
};

// Noms, types, libellés et unités saisis dans la page Gestion : ils passent avant les valeurs écrites en dur.
// Rechargés à chaque rafraîchissement des données (useMysa.js).
let CATALOG = { devices: {}, sensors: {} };
export function setCatalog(devices, sensorMeta) {
  CATALOG = { devices: Object.fromEntries(devices.map((d) => [d.device_id, d])), sensors: sensorMeta || {} };
}

export const deviceName = (id) => CATALOG.devices[id]?.name || DEVICES[id]?.name || id;
export const deviceKind = (id) => CATALOG.devices[id]?.kind || DEVICES[id]?.kind || "Appareil connecté";
export const sensorLabel = (s, deviceId) => CATALOG.sensors[deviceId]?.[s]?.label || SENSORS[s]?.label || s;

export function formatValue(sensor, value, unit, deviceId) {
  if (value === null || value === undefined) return "—";
  const spec = SENSORS[sensor];
  if (spec?.fmt) return spec.fmt(value);
  if (unit === "bool") return value >= 0.5 ? "actif" : "inactif";
  const digits = spec?.digits ?? 2;
  const n = Number(value).toLocaleString("fr-FR", { maximumFractionDigits: digits, minimumFractionDigits: digits });
  return `${n} ${CATALOG.sensors[deviceId]?.[sensor]?.unit || spec?.unit || unit || ""}`.trim();
}

export const isBinary = (sensor, unit) => SENSORS[sensor]?.binary ?? unit === "bool";

// Ce que signifie chaque détecteur, dans les mots de l'occupant.
export const DETECTORS = {
  enveloppe: { name: "Valeurs", text: "valeurs hors de la plage habituelle" },
  rythme: { name: "Rythme", text: "rythme d'envoi inhabituel" },
  tendance: { name: "Tendance", text: "dérive progressive des valeurs" },
  bascules: { name: "Bascules", text: "changements d'état incessants" },
  forêt: { name: "Combinaison", text: "combinaison inhabituelle de mesures" },
};

export function describeEpisode(e) {
  if (e.kind === "silence") return "ne donne plus de nouvelles";
  if (e.kind === "notice") return "ne ressemble pas au modèle de sa catégorie";
  if (e.kind === "rule") {
    const m = /^(?:règle|corrélation)\s*:\s*(.+)$/i.exec(e.source || "");
    return m ? m[1] : "règle de sécurité déclenchée";
  }
  const reason = /\(([^)]+)\)\s*$/.exec(e.source || "")?.[1];
  return DETECTORS[reason]?.text ?? "comportement inhabituel";
}

export function detectorOf(e) {
  if (e.kind === "silence") return "Silence";
  if (e.kind === "notice") return "Référence";
  if (e.kind === "rule") return /^corrélation/i.test(e.source || "") ? "Corrélation" : "Règle";
  const reason = /\(([^)]+)\)\s*$/.exec(e.source || "")?.[1];
  return DETECTORS[reason]?.name ?? "Référence";
}

export const REGIMES = {
  démarrage: { label: "Démarrage", text: "remplit sa première fenêtre de 20 messages" },
  référence: { label: "Amorçage", text: "protégé par le modèle de sa catégorie en attendant son modèle propre" },
  apprentissage: { label: "Apprentissage", text: "apprend son comportement habituel" },
  local: { label: "Surveillé", text: "comparé à son propre comportement habituel" },
};

export const KIND_LABEL = { anomaly: "Anomalie", rule: "Règle", silence: "Silence", notice: "Avis" };
export const SEVERITY_LABEL = { high: "Forte", medium: "Moyenne", low: "Faible" };

const rtf = new Intl.RelativeTimeFormat("fr", { numeric: "auto" });
export function ago(ts, now = Date.now()) {
  if (!ts) return "jamais";
  const s = (new Date(ts).getTime() - now) / 1000;
  const a = Math.abs(s);
  if (a < 45) return "à l'instant";
  if (a < 3600) return rtf.format(Math.round(s / 60), "minute");
  if (a < 86400) return rtf.format(Math.round(s / 3600), "hour");
  return rtf.format(Math.round(s / 86400), "day");
}

export const clock = (ts) =>
  new Date(ts).toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit", second: "2-digit" });

export function duration(start, end) {
  const s = Math.max(0, (new Date(end) - new Date(start)) / 1000);
  if (s < 1) return "instantané";
  if (s < 90) return `${Math.round(s)} s`;
  if (s < 5400) return `${Math.round(s / 60)} min`;
  return `${(s / 3600).toFixed(1).replace(".", ",")} h`;
}
