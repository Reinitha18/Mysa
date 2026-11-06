// Logo Mysa en SVG : même maison + Wi-Fi que le logo PNG, mais avec un logotype clair
// (le PNG a un fond blanc et un texte noir, illisibles sur le thème sombre).
export default function Logo({ height = 40 }) {
  return (
    <svg className="logo" height={height} viewBox="0 0 196 64" role="img" aria-label="Mysa">
      <defs>
        <linearGradient id="logo-g" x1="0" x2="1" y1="0" y2="0">
          <stop offset="0" stopColor="#22d3ff" />
          <stop offset=".55" stopColor="#2f8dff" />
          <stop offset="1" stopColor="#5b6cff" />
        </linearGradient>
      </defs>
      <g className="logo-mark">
        <path d="M6 44 L32 24 L58 44" fill="none" stroke="url(#logo-g)" strokeWidth="7" strokeLinecap="round" strokeLinejoin="round" />
        <rect x="15" y="25" width="6" height="9" rx="1" fill="#2f8dff" />
        <g fill="#38bdf8">
          <rect x="27" y="36" width="4.5" height="4.5" /><rect x="32.5" y="36" width="4.5" height="4.5" />
          <rect x="27" y="41.5" width="4.5" height="4.5" /><rect x="32.5" y="41.5" width="4.5" height="4.5" />
        </g>
        <g className="logo-wifi" fill="none" stroke="#22d3ff" strokeWidth="3.2" strokeLinecap="round">
          <path d="M24 12 a12 12 0 0 1 16 0" /><path d="M27.5 16.5 a6.5 6.5 0 0 1 9 0" />
        </g>
        <circle cx="32" cy="20" r="2.2" fill="#22d3ff" />
      </g>
      <text x="72" y="46" className="logo-word">Mysa</text>
    </svg>
  );
}
