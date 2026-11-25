import { Suspense, memo } from "react";
import { Canvas } from "@react-three/fiber";
import { ContactShadows, Environment, Float, Lightformer } from "@react-three/drei";
import { RobotModel } from "./RobotModel";
import type { RobotViewProps } from "./types";

/** Camera framing per placement: the launcher shows head and chest, the panel header just the face. */
const FRAMING = {
  launcher: { position: [0, 1.25, 4.7] as [number, number, number], fov: 30, target: 1.1 },
  header: { position: [0, 1.75, 1.75] as [number, number, number], fov: 28, target: 1.68 },
};

interface Props extends RobotViewProps {
  modelUrl: string;
}

/**
 * The 3D layer. Memoised so chat typing never re-renders WebGL; it only reacts to state/variant/active changes.
 * Rendering: continuous while visible, paused entirely ("never") when hidden, single frames for reduced motion.
 */
function RobotSceneInner({ modelUrl, state, variant, active, reducedMotion }: Props) {
  const f = FRAMING[variant];
  return (
    <Canvas
      dpr={[1, 1.5]}
      frameloop={!active ? "never" : reducedMotion ? "demand" : "always"}
      camera={{ position: f.position, fov: f.fov, near: 0.1, far: 50 }}
      gl={{ antialias: true, alpha: true, powerPreference: "low-power" }}
      onCreated={({ camera }) => camera.lookAt(0, f.target, 0)}
      style={{ background: "transparent" }}
      aria-hidden
    >
      {/* soft studio lighting: key, cool rim, and a lightformer environment for reflections (no network fetch) */}
      <ambientLight intensity={0.55} />
      <directionalLight position={[2.5, 4, 3]} intensity={1.6} />
      <directionalLight position={[-3, 2.5, -2]} intensity={1.1} color="#7DD3FC" />
      <Environment resolution={64}>
        <Lightformer form="rect" intensity={2.2} position={[0, 4, 3]} scale={[6, 2, 1]} />
        <Lightformer form="rect" intensity={1.2} color="#A5F3FC" position={[-4, 1, -2]} scale={[2, 4, 1]} />
        <Lightformer form="circle" intensity={0.8} position={[4, 2, 1]} scale={2} />
      </Environment>

      <Suspense fallback={null}>
        <Float
          enabled={!reducedMotion}
          speed={1.6}
          rotationIntensity={0.15}
          floatIntensity={variant === "launcher" ? 0.35 : 0.15}
          floatingRange={[-0.04, 0.06]}
        >
          <RobotModel url={modelUrl} state={state} reducedMotion={reducedMotion} />
        </Float>
      </Suspense>
      {variant === "launcher" && (
        <ContactShadows position={[0, 0.0, 0]} opacity={0.32} scale={3} blur={2.6} far={2} resolution={256} frames={1} />
      )}
    </Canvas>
  );
}

const RobotScene = memo(RobotSceneInner);
export default RobotScene;
