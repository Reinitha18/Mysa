// Le toit du logo Mysa, à l'échelle de la page : sa couleur dit l'état de la maison,
// ses ondes Wi-Fi s'animent à l'arrivée de nouveaux messages.
const TONES = {
  calm: ["#00BAED", "#0369B1", "#0C1F5B"],
  watch: ["#F4C25A", "#D9922E", "#7A4A0E"],
  alert: ["#F38A80", "#D0433A", "#6E1712"],
};

export default function Roof({ tone = "calm", pulse = 0, live = false }) {
  const [a, b, c] = TONES[tone];
  const wave = tone === "calm" ? "#0369B1" : b;
  return (
    <svg className="roof" viewBox="0 0 1000 190" preserveAspectRatio="xMidYMax meet" aria-hidden="true">
      <defs>
        <linearGradient id="roof-grad" gradientUnits="userSpaceOnUse" x1="18" x2="984" y1="0" y2="0">
          <stop offset="0" stopColor={a} />
          <stop offset="0.42" stopColor={b} />
          <stop offset="1" stopColor={c} />
        </linearGradient>
        <linearGradient id="eave-grad" x1="0" x2="0" y1="0" y2="1">
          <stop offset="0" stopColor={a} stopOpacity="0.55" />
          <stop offset="1" stopColor={a} stopOpacity="0" />
        </linearGradient>
      </defs>
      {/* cheminée */}
      <rect x="292" y="76" width="34" height="40" rx="3" fill={b} />
      {/* versant gauche plein, comme dans le logo */}
      <path d="M18 182 Q30 168 52 150 L300 104 Q420 76 486 58 Q500 54 512 66 Q470 82 390 112 Q230 168 40 188 Z"
            fill="url(#roof-grad)" />
      {/* long versant droit, effilé */}
      <path d="M486 58 Q500 52 514 64 Q600 140 700 160 Q830 180 984 186 Q820 186 700 174 Q588 158 486 58 Z"
            fill="url(#roof-grad)" />
      {/* fenêtre */}
      <g fill={b}>
        <rect x="474" y="98" width="17" height="17" rx="2" />
        <rect x="496" y="98" width="17" height="17" rx="2" />
        <rect x="474" y="120" width="17" height="17" rx="2" />
        <rect x="496" y="120" width="17" height="17" rx="2" />
      </g>
      {/* ondes */}
      <g key={pulse} className={`waves ${live ? "is-live" : ""}`} fill="none" stroke={wave} strokeLinecap="round">
        <circle cx="493" cy="34" r="5" fill={wave} stroke="none" className="w0" />
        <path d="M478 22 a21 21 0 0 1 30 0" strokeWidth="7" className="w1" />
        <path d="M466 10 a38 38 0 0 1 54 0" strokeWidth="7" className="w2" />
      </g>
    </svg>
  );
}
