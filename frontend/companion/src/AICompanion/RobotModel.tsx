import { useEffect, useMemo, useRef } from "react";
import { useAnimations, useGLTF } from "@react-three/drei";
import { useFrame } from "@react-three/fiber";
import * as THREE from "three";
import { clone as cloneSkinned } from "three/examples/jsm/utils/SkeletonUtils.js";
import { MODEL_SPEC, useRobotAnimation } from "./useRobotAnimation";
import type { RobotState } from "./types";

interface Props {
  url: string;
  state: RobotState;
  reducedMotion: boolean;
}

/**
 * Premium white / silver / cyan finish. The placeholder ships flat cartoon colours; we restyle it by material name
 * so it reads closer to the final design. The final model will carry its own PBR materials and skip this step.
 */
function restyle(root: THREE.Object3D): Record<string, THREE.MeshPhysicalMaterial> {
  const shell = new THREE.MeshPhysicalMaterial({
    color: "#F4F6FA", roughness: 0.28, metalness: 0.05, clearcoat: 1, clearcoatRoughness: 0.12, sheen: 0.2,
  });
  const silver = new THREE.MeshPhysicalMaterial({ color: "#B9C3D1", roughness: 0.32, metalness: 0.85 });
  const glass = new THREE.MeshPhysicalMaterial({
    color: "#0B1426", roughness: 0.12, metalness: 0.2, clearcoat: 1, emissive: new THREE.Color("#22D3EE"),
    emissiveIntensity: 0.22,
  });
  const map: Record<string, THREE.MeshPhysicalMaterial> = { Main: shell, Grey: silver, Black: glass };
  root.traverse((o) => {
    const m = o as THREE.Mesh;
    if (!m.isMesh) return;
    m.castShadow = true;
    // skinned meshes keep bind-pose bounds that don't match the posed robot, so culling would hide it
    m.frustumCulled = false;
    const mats = Array.isArray(m.material) ? m.material : [m.material];
    const swapped = mats.map((mat) => map[(mat as THREE.Material).name] ?? mat);
    m.material = Array.isArray(m.material) ? swapped : swapped[0];
  });
  return map;
}

export function RobotModel({ url, state, reducedMotion }: Props) {
  const { scene, animations } = useGLTF(url);
  const group = useRef<THREE.Group>(null);
  const bounce = useRef<THREE.Group>(null);

  // Own copy (skinned meshes need SkeletonUtils), normalised to ~2 units tall and centred on its feet.
  const { model, materials } = useMemo(() => {
    const c = cloneSkinned(scene);
    const materials = restyle(c);
    // measure the posed (skinned) vertices: the plain bounds come from the bind pose and are ~75x too large
    c.updateMatrixWorld(true);
    const box = new THREE.Box3().setFromObject(c, true);
    const size = box.getSize(new THREE.Vector3());
    const s = 2 / size.y;
    c.scale.setScalar(s);
    c.position.set(-((box.min.x + box.max.x) / 2) * s, -box.min.y * s, -((box.min.z + box.max.z) / 2) * s);
    return { model: c, materials };
  }, [scene]);

  const { actions } = useAnimations(animations, group);
  useRobotAnimation(model, actions, state, reducedMotion, bounce);

  // Visor glow follows the state: cyan when calm, brighter while speaking, soft red on error.
  const glow = useRef({ color: new THREE.Color("#22D3EE"), intensity: 0.22 });
  useFrame((three, delta) => {
    const g = glow.current;
    const targetColor = state === "error" ? "#F87171" : state === "happy" ? "#5EEAD4" : "#22D3EE";
    let targetI = state === "error" ? 0.75 : state === "speaking" ? 0.45 : state === "thinking" ? 0.35 : 0.22;
    if (state === "thinking" && !reducedMotion) targetI += Math.sin(three.clock.elapsedTime * 3) * 0.12;
    g.color.lerp(new THREE.Color(targetColor), Math.min(1, delta * 4));
    g.intensity = THREE.MathUtils.damp(g.intensity, targetI, 4, delta);
    materials.Black.emissive.copy(g.color);
    materials.Black.emissiveIntensity = g.intensity;
  });

  useEffect(() => () => {
    Object.values(materials).forEach((m) => m.dispose());
  }, [materials]);

  return (
    <group ref={bounce}>
      <group ref={group}>
        <primitive object={model} />
      </group>
    </group>
  );
}

export function preloadRobot(url: string) {
  useGLTF.preload(url);
}

export { MODEL_SPEC };
