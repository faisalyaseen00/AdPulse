import type { RobotState } from "./types";

/**
 * Lightweight stand-in: shown before the 3D scene has loaded, when WebGL is unavailable, or if the model fails.
 * Pure SVG + CSS (the animations live in styles.css and respect reduced motion).
 */
export function Fallback2D({ state, size = 96 }: { state: RobotState; size?: number }) {
  const eye = state === "error" ? "#F87171" : "#22D3EE";
  return (
    <svg className={`aic-fallback aic-fb-${state}`} width={size} height={size} viewBox="0 0 96 96" aria-hidden>
      <defs>
        <linearGradient id="aicShell" x1="0" x2="0" y1="0" y2="1">
          <stop offset="0" stopColor="#FFFFFF" />
          <stop offset="1" stopColor="#D9E0EA" />
        </linearGradient>
      </defs>
      <ellipse cx="48" cy="90" rx="22" ry="3" fill="#0B1226" opacity=".18" />
      <g className="aic-fb-body">
        <rect x="28" y="58" width="40" height="28" rx="14" fill="url(#aicShell)" stroke="#C7D0DC" />
        <circle cx="48" cy="70" r="4" fill={eye} opacity=".9" />
        <line x1="48" y1="14" x2="48" y2="22" stroke="#B9C3D1" strokeWidth="3" strokeLinecap="round" />
        <circle cx="48" cy="12" r="4" fill={eye} />
        <rect x="18" y="20" width="60" height="42" rx="21" fill="url(#aicShell)" stroke="#C7D0DC" />
        <rect x="26" y="28" width="44" height="26" rx="13" fill="#0B1426" />
        <ellipse className="aic-fb-eye" cx="39" cy="40" rx="4" ry="5" fill={eye} />
        <ellipse className="aic-fb-eye" cx="57" cy="40" rx="4" ry="5" fill={eye} />
        <path className="aic-fb-mouth" d="M42 48 Q48 51 54 48" fill="none" stroke={eye} strokeWidth="2" strokeLinecap="round" />
      </g>
    </svg>
  );
}

export function hasWebGL(): boolean {
  try {
    const c = document.createElement("canvas");
    return !!(window.WebGLRenderingContext && (c.getContext("webgl2") || c.getContext("webgl")));
  } catch {
    return false;
  }
}
