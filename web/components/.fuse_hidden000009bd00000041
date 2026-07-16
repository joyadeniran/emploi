/** Simple brand illustration of the Career Twin bot (pure SVG, no assets). */
export function CareerTwinBot({ size = 190 }: { size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 200 200"
      role="img"
      aria-label="Your Career Twin assistant"
    >
      <defs>
        <linearGradient id="bot-body" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stopColor="#c9b8ff" />
          <stop offset="100%" stopColor="#a08bff" />
        </linearGradient>
        <linearGradient id="bot-face" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#2a2354" />
          <stop offset="100%" stopColor="#171242" />
        </linearGradient>
      </defs>

      {/* halo rings */}
      <circle cx="100" cy="105" r="88" fill="none" stroke="#8b48fd" strokeOpacity="0.12" strokeWidth="1.5" />
      <circle cx="100" cy="105" r="68" fill="none" stroke="#8b48fd" strokeOpacity="0.18" strokeWidth="1.5" />

      {/* antenna */}
      <line x1="100" y1="30" x2="100" y2="44" stroke="#8b7bff" strokeWidth="4" strokeLinecap="round" />
      <circle cx="100" cy="26" r="6" fill="#8b48fd" />

      {/* head */}
      <rect x="52" y="44" width="96" height="70" rx="30" fill="url(#bot-body)" />
      <rect x="64" y="56" width="72" height="46" rx="20" fill="url(#bot-face)" />
      {/* eyes: happy arcs */}
      <path d="M82 82 q6 -9 12 0" stroke="#7ef0e2" strokeWidth="4.5" fill="none" strokeLinecap="round" />
      <path d="M106 82 q6 -9 12 0" stroke="#7ef0e2" strokeWidth="4.5" fill="none" strokeLinecap="round" />
      {/* smile */}
      <path d="M92 91 q8 7 16 0" stroke="#7ef0e2" strokeWidth="3.5" fill="none" strokeLinecap="round" />

      {/* body */}
      <rect x="62" y="118" width="76" height="52" rx="24" fill="url(#bot-body)" />
      {/* chest mark: three logo bars */}
      <rect x="88" y="132" width="24" height="5.5" rx="2.75" fill="#4651fc" />
      <rect x="88" y="141" width="28" height="5.5" rx="2.75" fill="#8b48fd" />
      <rect x="88" y="150" width="21" height="5.5" rx="2.75" fill="#4651fc" />

      {/* arms */}
      <rect x="42" y="124" width="16" height="34" rx="8" fill="#b3a3ff" transform="rotate(18 50 141)" />
      <rect x="142" y="124" width="16" height="34" rx="8" fill="#b3a3ff" transform="rotate(-18 150 141)" />

      {/* floating chips */}
      <g>
        <rect x="14" y="70" width="30" height="30" rx="9" fill="#ffffff" stroke="#ecebf6" />
        <rect x="22" y="79" width="14" height="10" rx="2" fill="#0e9f6e" />
        <rect x="26" y="76" width="6" height="4" rx="1.5" fill="#0e9f6e" />
      </g>
      <g>
        <rect x="156" y="58" width="30" height="30" rx="9" fill="#ffffff" stroke="#ecebf6" />
        <path d="M171 64 l9 4 v6 c0 6 -4 9 -9 11 c-5 -2 -9 -5 -9 -11 v-6 Z" fill="#435afe" />
        <path d="M167 74 l3 3 l5 -6" stroke="#fff" strokeWidth="2" fill="none" strokeLinecap="round" strokeLinejoin="round" />
      </g>
      <g>
        <rect x="152" y="140" width="30" height="30" rx="9" fill="#ffffff" stroke="#ecebf6" />
        <path d="M159 162 l6 -7 l4 4 l7 -9" stroke="#8b48fd" strokeWidth="2.5" fill="none" strokeLinecap="round" strokeLinejoin="round" />
      </g>
    </svg>
  );
}
