/**
 * Emploi loading loop — the 3 logo-mark bars pulsing in a cascading
 * top-to-bottom wave. Spec (design handoff "Emploi Loading Loop"):
 * 1.15s cycle, 0.16s stagger per bar, scaleY 1→1.16→1 + opacity 0.5→1→0.5
 * on a cosine curve, each bar scaling from its own center.
 * Stateless and decorative; use wherever work is in progress.
 */
export function LoadingMark({
  size = 96,
  label = "Loading",
}: {
  size?: number;
  label?: string;
}) {
  return (
    <span role="status" aria-label={label} className="inline-flex">
      <svg
        viewBox="0 0 143 165"
        width={size}
        height={size * (165 / 143)}
        xmlns="http://www.w3.org/2000/svg"
        aria-hidden="true"
      >
        <defs>
          <linearGradient id="loading-mark-grad" x1="0%" y1="61.566%" x2="78.801%" y2="0%">
            <stop offset="0%" stopColor="#8b48fd" />
            <stop offset="30%" stopColor="#6f4afb" />
            <stop offset="62%" stopColor="#5d4ffd" />
            <stop offset="99%" stopColor="#435afe" />
          </linearGradient>
        </defs>
        <path
          className="loading-mark-bar"
          fill="#4651fc"
          d="M116.665,45.258 L15.894,45.258 C7.127,45.258 0.020,38.150 0.020,29.383 C0.020,20.616 7.127,13.509 15.894,13.509 L116.665,13.509 C125.432,13.509 132.540,20.616 132.540,29.383 C132.540,38.150 125.432,45.258 116.665,45.258 Z"
        />
        <path
          className="loading-mark-bar"
          style={{ animationDelay: "0.16s" }}
          fill="url(#loading-mark-grad)"
          d="M127.617,95.089 L15.894,95.089 C7.127,95.089 0.020,87.982 0.020,79.215 C0.020,70.448 7.127,63.340 15.894,63.340 L127.617,63.340 C136.385,63.340 143.492,70.448 143.492,79.215 C143.492,87.982 136.385,95.089 127.617,95.089 Z"
        />
        <path
          className="loading-mark-bar"
          style={{ animationDelay: "0.32s" }}
          fill="#4651fc"
          d="M119.951,144.921 L108.154,144.921 C108.149,144.925 108.144,144.929 108.139,144.933 L25.751,144.933 C16.984,144.933 9.876,152.040 9.876,160.807 C9.876,161.209 9.896,161.606 9.926,162.000 C4.137,159.808 0.020,154.216 0.020,147.659 L0.020,131.243 L0.174,131.243 C0.075,130.524 0.020,129.792 0.020,129.046 C0.020,120.279 7.127,113.172 15.894,113.172 L119.951,113.172 C128.718,113.172 135.825,120.279 135.825,129.046 C135.825,137.814 128.718,144.921 119.951,144.921 Z"
        />
      </svg>
    </span>
  );
}
