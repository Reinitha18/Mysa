// Accès à l'API Mysa (chapitre 7.3 du mémoire). Chemins relatifs : proxy Vite en
// développement, même origine quand l'API sert le dashboard compilé.
const json = async (path, options) => {
  const r = await fetch(path, options);
  // Session expirée ou absente (MYSA_DASHBOARD_PASSWORD) : App affiche l'écran de connexion.
  if (r.status === 401 && !path.startsWith("/api/auth/")) window.dispatchEvent(new Event("mysa:unauthorized"));
  if (!r.ok) {
    const detail = await r.json().catch(() => ({}));
    throw new Error(detail.detail || `${r.status} ${r.statusText}`);
  }
  return r.json();
};

export const getDevices = () => json("/api/devices");
export const getStreams = () => json("/api/streams");
export const getEpisodes = (limit = 200, deviceId) =>
  json(`/api/episodes?limit=${limit}${deviceId ? `&device_id=${encodeURIComponent(deviceId)}` : ""}`);
export const getEpisodeAlerts = (episodeId) => json(`/api/alerts?episode_id=${episodeId}&limit=500`);
export const ackEpisode = (episodeId, acknowledged = true, note) =>
  json(`/api/episodes/${episodeId}/ack`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ acknowledged, note }),
  });
export const getHistory = (deviceId, limit = 400, sensor) =>
  json(`/api/devices/${encodeURIComponent(deviceId)}/history?limit=${limit}${sensor ? `&sensor=${encodeURIComponent(sensor)}` : ""}`);
export const getRisk = (deviceId) => json(`/api/devices/${encodeURIComponent(deviceId)}/risk`);
export const getActuators = () => json("/api/commands");
export const getLastRefusedBadge = () => json("/api/badges/last-refused");
export const getAuthorizedBadges = () => json("/api/badges/authorized");
export const getValidationRuns = (limit = 20) => json(`/api/validation/runs?limit=${limit}`);
export const getAccessLog = (limit = 20) => json(`/api/badges/access?limit=${limit}`);
export const accessCaptureUrl = (accessId) => `/api/badges/access/${accessId}/capture`;
export const sendCommand = (device_id, actuator, value) =>
  json("/api/commands", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ device_id, actuator, value }),
  });

const post = (path, body) =>
  json(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body ?? {}) });

export const getAuthStatus = () => json("/api/auth/status");
export const login = (password) => post("/api/auth/login", { password });
export const logout = () => post("/api/auth/logout");
export const getNotifications = () => json("/api/notifications");
export const testNotifications = () => post("/api/notifications/test");

export function alertsSocketUrl() {
  const proto = window.location.protocol === "https:" ? "wss" : "ws";
  return `${proto}://${window.location.host}/ws/alerts`;
}

export function cameraViewSocketUrl() {
  const proto = window.location.protocol === "https:" ? "wss" : "ws";
  return `${proto}://${window.location.host}/ws/camera/view`;
}
