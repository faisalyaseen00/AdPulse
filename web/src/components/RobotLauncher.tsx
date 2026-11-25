import { Suspense, lazy, useEffect, useState } from "react";
import { Link } from "react-router";
import { Fallback2D, hasWebGL } from "@/robot/Fallback2D";
import type { RobotState } from "@/robot/types";

const RobotScene = lazy(() => import("@/robot/RobotScene"));

function useVisible() {
  const [v, setV] = useState(!document.hidden);
  useEffect(() => {
    const on = () => setV(!document.hidden);
    document.addEventListener("visibilitychange", on);
    return () => document.removeEventListener("visibilitychange", on);
  }, []);
  return v;
}

/** Floating 3D robot, bottom-right: a shortcut to the Ask page. Waves now and then; still when motion is reduced. */
export default function RobotLauncher() {
  const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const visible = useVisible();
  const [state, setState] = useState<RobotState>("idle");
  const [webgl] = useState(hasWebGL);

  useEffect(() => {
    if (reduced || !visible) return;
    let back: number | undefined;
    const wave = () => {
      setState("happy");
      back = window.setTimeout(() => setState("idle"), 2600);
    };
    const first = window.setTimeout(wave, 1500);
    const every = window.setInterval(wave, 12000);
    return () => { clearTimeout(first); clearInterval(every); if (back) clearTimeout(back); };
  }, [reduced, visible]);

  const fallback = <div className="grid h-full place-items-end justify-center"><Fallback2D state={state} size={64} /></div>;

  return (
    <Link
      to="/ask"
      aria-label="Ask AdPulse a question"
      className="group fixed bottom-4 right-3 z-20 block h-[92px] w-[80px] overflow-visible [&_canvas]:!max-w-full sm:bottom-6 sm:right-6"
    >
      <span className="pointer-events-none absolute -top-9 right-0 whitespace-nowrap rounded-md border border-ink bg-surface px-2.5 py-1 text-xs font-medium text-ink opacity-0 transition-opacity group-hover:opacity-100 group-focus-visible:opacity-100">
        Ask a question
      </span>
      <div className="absolute inset-0 overflow-hidden">
        {webgl ? (
          <Suspense fallback={fallback}>
            <RobotScene modelUrl="/robot.glb" state={state} variant="launcher" active={visible} reducedMotion={reduced} />
          </Suspense>
        ) : fallback}
      </div>
    </Link>
  );
}
