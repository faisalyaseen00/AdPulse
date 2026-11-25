/**
 * The floating "Ask AdPulse" robot icon. Purely visual: it renders inside a small transparent frame in the corner
 * of the Streamlit app, and a link layered on top (in the app) handles the click to the "Ask a question" page.
 *
 * Behaviour: idle (float, blink, head drift) most of the time, a friendly wave every few seconds.
 */
import { StrictMode, Suspense, lazy, useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import { Fallback2D, hasWebGL } from "./AICompanion/Fallback2D";
import type { RobotState } from "./AICompanion/types";

const RobotScene = lazy(() => import("./AICompanion/RobotScene"));

const CSS = `
  html, body { margin: 0; padding: 0; width: 100%; height: 100%; background: transparent; overflow: hidden; }
  /* the frame is a fixed 124x140 box: give the 3D canvas that exact size (a collapsed parent leaves it at 300x150) */
  #root { position: fixed; inset: 0; display: block; }
  #root > div { position: absolute; inset: 0; }
  #root canvas { display: block; width: 100% !important; height: 100% !important; }
  #root > svg { position: absolute; left: 50%; bottom: 0; transform: translateX(-50%); }
  .aic-fallback { display: block; overflow: visible; }
  .aic-fb-body { animation: aic-float 3.2s ease-in-out infinite; transform-box: fill-box; }
  .aic-fb-eye { transform-box: fill-box; transform-origin: center; animation: aic-blink 4.4s infinite; }
  @keyframes aic-float { 0%, 100% { transform: translateY(0); } 50% { transform: translateY(-4px); } }
  @keyframes aic-blink { 0%, 93%, 100% { transform: scaleY(1); } 96% { transform: scaleY(.1); } }
  @media (prefers-reduced-motion: reduce) { * { animation: none !important; } }
`;

function useVisible() {
  const [v, setV] = useState(!document.hidden);
  useEffect(() => {
    const on = () => setV(!document.hidden);
    document.addEventListener("visibilitychange", on);
    return () => document.removeEventListener("visibilitychange", on);
  }, []);
  return v;
}

function RobotIcon({ modelUrl }: { modelUrl: string }) {
  const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const visible = useVisible();
  const [state, setState] = useState<RobotState>("idle");

  // a wave every ~9 s (skipped when motion is reduced or the tab is hidden)
  useEffect(() => {
    if (reduced || !visible) return;
    let back: number | undefined;
    const wave = window.setInterval(() => {
      setState("happy");
      back = window.setTimeout(() => setState("idle"), 2600);
    }, 9000);
    const first = window.setTimeout(() => {
      setState("happy");
      back = window.setTimeout(() => setState("idle"), 2600);
    }, 1200);
    return () => {
      clearInterval(wave);
      clearTimeout(first);
      if (back) clearTimeout(back);
    };
  }, [reduced, visible]);

  const fallback = <Fallback2D state={state} size={96} />;
  if (!hasWebGL()) return fallback;
  return (
    <div style={{ position: "absolute", inset: 0 }}>
      <Suspense fallback={fallback}>
        <RobotScene modelUrl={modelUrl} state={state} variant="launcher" active={visible} reducedMotion={reduced} />
      </Suspense>
    </div>
  );
}

/** Mount into #root. The model URL comes from the host page (data-model on the script tag or a default). */
export function mount(el: HTMLElement, modelUrl: string) {
  const style = document.createElement("style");
  style.textContent = CSS;
  document.head.appendChild(style);
  createRoot(el).render(
    <StrictMode>
      <RobotIcon modelUrl={modelUrl} />
    </StrictMode>,
  );
}

const root = document.getElementById("root");
if (root) mount(root, root.dataset.model || "robot.glb");
