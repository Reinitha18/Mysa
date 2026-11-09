// État courant d'un actionneur, lu sur la dernière mesure du capteur qui le rapporte. Sert à désactiver
// un bouton qui ne ferait rien : « Allumer » quand la prise est déjà allumée, « Fermer » quand la porte est fermée.
const REPORTED = {
  lock: ["lock", { open: true, close: false }],
  arm: ["arm", { on: true, off: false }],
  alarm: ["alarm", { on: true, off: false }],
  relay: ["relay", { on: true, off: false }],
  mode: ["relay_auto", { auto: true, manual: false }],
};

// deviceLatest : { capteur: { value, ts } } de l'appareil. Faux si l'état est inconnu.
export function alreadyIn(actuator, value, deviceLatest) {
  const [sensor, targets] = REPORTED[actuator] ?? [];
  const row = deviceLatest?.[sensor];
  if (!sensor || row?.value == null || !(value in targets)) return false;
  // Prise en mode automatique : « Allumer » / « Éteindre » la repassent en manuel, ce n'est pas un « déjà fait ».
  if (actuator === "relay" && deviceLatest?.relay_auto?.value >= 0.5) return false;
  return row.value >= 0.5 === targets[value];
}
