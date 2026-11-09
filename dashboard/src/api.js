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
export const ackEpisodes = (ids, acknowledged = true, note) =>
  json("/api/episodes/ack", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ids, acknowledged, note }),
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

const send = (method) => (path, body) =>
  json(path, { method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body ?? {}) });
const put = send("PUT");
const del = (path) => json(path, { method: "DELETE" });
const enc = encodeURIComponent;

// Comptes : e-mail + mot de passe (sans e-mail : ancien mot de passe unique du hub).
export const getAuthStatus = () => json("/api/auth/status");
export const login = (password, email) => post("/api/auth/login", { email: email || undefined, password });
export const logout = () => post("/api/auth/logout");
export const register = (email, password) => post("/api/auth/register", { email, password });
export const changePassword = (current, next) => post("/api/auth/password", { current, new: next });
export const getUsers = () => json("/api/auth/users");
export const deleteUser = (id) => del(`/api/auth/users/${id}`);

// Gestion : maisons, appareils, capteurs.
export const getHouses = () => json("/api/houses");
export const createHouse = (body) => post("/api/houses", body);
export const updateHouse = (id, body) => put(`/api/houses/${id}`, body);
export const deleteHouse = (id) => del(`/api/houses/${id}`);
export const createDevice = (body) => post("/api/devices", body);
export const updateDevice = (id, body) => put(`/api/devices/${enc(id)}`, body);
export const deleteDevice = (id) => del(`/api/devices/${enc(id)}`);
export const getSensorMeta = () => json("/api/devices/sensor-meta");
export const getSensors = (deviceId) => json(`/api/devices/${enc(deviceId)}/sensors`);
export const createSensor = (deviceId, body) => post(`/api/devices/${enc(deviceId)}/sensors`, body);
export const updateSensor = (deviceId, sensor, body) => put(`/api/devices/${enc(deviceId)}/sensors/${enc(sensor)}`, body);
export const deleteSensor = (deviceId, sensor) => del(`/api/devices/${enc(deviceId)}/sensors/${enc(sensor)}`);
export const getNotifications = () => json("/api/notifications");
export const getNotificationSettings = () => json("/api/notifications/settings");
export const saveNotificationSettings = (body) =>
  json("/api/notifications/settings", { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
export const testNotifications = () => post("/api/notifications/test");

export function alertsSocketUrl() {
  const proto = window.location.protocol === "https:" ? "wss" : "ws";
  return `${proto}://${window.location.host}/ws/alerts`;
}

export function cameraViewSocketUrl() {
  const proto = window.location.protocol === "https:" ? "wss" : "ws";
  return `${proto}://${window.location.host}/ws/camera/view`;
}
