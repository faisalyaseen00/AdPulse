import { useEffect, useMemo, useRef } from "react";
import { useFrame } from "@react-three/fiber";
import * as THREE from "three";
import type { ModelSpec, RobotState } from "./types";

/**
 * MODEL_NOTES (placeholder honesty)
 * The CC0 "RobotExpressive" placeholder has clips + three face morphs (Angry, Surprised, Sad) but no blink or
 * mouth/viseme morphs. Blink and speaking are therefore approximated (see `blink` / `speak` below). When the final
 * model ships `blink` and `mouthOpen` morphs, set them in MODEL_SPEC and the real ones are used automatically.
 */
export const MODEL_SPEC: ModelSpec = {
  url: "robot.glb",
  clips: { idle: "Idle", listening: "Idle", thinking: "Idle", speaking: "Yes", happy: "Wave", error: "No" },
  headBone: "Head",
  neckBone: "Neck",
  morphs: { surprised: "Surprised", sad: "Sad", angry: "Angry" },
};

/** Per-state look. Everything is a target; the frame loop eases toward it, so changes never snap. */
interface StatePose {
  clipSpeed: number;
  headPitch: number; // + = look down/forward
  headYaw: number;
  headRoll: number;
  followPointer: number; // 0..1 how much the head tracks the cursor
  surprised: number;
  sad: number;
  angry: number;
  bob: number; // extra vertical bounce amplitude
  sway: number; // slow thinking sway amplitude
}

const POSES: Record<RobotState, StatePose> = {
  idle: { clipSpeed: 1, headPitch: 0, headYaw: 0, headRoll: 0, followPointer: 0.25, surprised: 0, sad: 0, angry: 0, bob: 0, sway: 0 },
  listening: { clipSpeed: 0.8, headPitch: 0.18, headYaw: 0, headRoll: 0.06, followPointer: 0.9, surprised: 0.3, sad: 0, angry: 0, bob: 0, sway: 0 },
  thinking: { clipSpeed: 0.6, headPitch: -0.22, headYaw: 0.25, headRoll: 0.16, followPointer: 0, surprised: 0, sad: 0.18, angry: 0, bob: 0, sway: 0.12 },
  speaking: { clipSpeed: 0.55, headPitch: 0.04, headYaw: 0, headRoll: 0, followPointer: 0.35, surprised: 0, sad: 0, angry: 0, bob: 0, sway: 0.04 },
  happy: { clipSpeed: 1, headPitch: -0.08, headYaw: 0, headRoll: 0, followPointer: 0.2, surprised: 0.45, sad: 0, angry: 0, bob: 0.06, sway: 0 },
  error: { clipSpeed: 0.9, headPitch: 0.1, headYaw: 0, headRoll: -0.05, followPointer: 0, surprised: 0, sad: 0.85, angry: 0.12, bob: 0, sway: 0 },
};

const FADE = 0.35; // seconds between clips

function findBone(root: THREE.Object3D, name: string): THREE.Bone | null {
  let hit: THREE.Bone | null = null;
  root.traverse((o) => {
    if (!hit && (o as THREE.Bone).isBone && o.name === name) hit = o as THREE.Bone;
  });
  return hit;
}

function findMorphMeshes(root: THREE.Object3D): THREE.Mesh[] {
  const out: THREE.Mesh[] = [];
  root.traverse((o) => {
    const m = o as THREE.Mesh;
    if (m.isMesh && m.morphTargetDictionary && m.morphTargetInfluences) out.push(m);
  });
  return out;
}

/**
 * Drives the robot from a single `state`. Clips cross-fade; head, face and bounce are layered on top every frame.
 * Runs after drei's useAnimations (registered earlier in the same component), so offsets apply on top of the clip.
 */
export function useRobotAnimation(
  root: THREE.Object3D,
  actions: Record<string, THREE.AnimationAction | null>,
  state: RobotState,
  reducedMotion: boolean,
  group: React.RefObject<THREE.Group | null>,
) {
  const head = useMemo(() => findBone(root, MODEL_SPEC.headBone), [root]);
  const neck = useMemo(() => findBone(root, MODEL_SPEC.neckBone), [root]);
  const faces = useMemo(() => findMorphMeshes(root), [root]);
  const live = useRef({ pitch: 0, yaw: 0, roll: 0, surprised: 0, sad: 0, angry: 0, blink: 0, y: 0 });
  const nextBlink = useRef(2 + Math.random() * 3);
  const current = useRef<THREE.AnimationAction | null>(null);
  // Rest poses, so offsets on bones the current clip does NOT animate don't pile up frame after frame.
  const rest = useMemo(() => ({ head: head?.quaternion.clone(), neck: neck?.quaternion.clone() }), [head, neck]);
  const driven = useRef({ head: false, neck: false });

  // ---- clip cross-fades on state change -------------------------------------------------------------------
  useEffect(() => {
    const name = MODEL_SPEC.clips[state] ?? MODEL_SPEC.clips.idle!;
    const next = actions[name] ?? actions[MODEL_SPEC.clips.idle!];
    if (!next) return;
    next.reset();
    next.setEffectiveTimeScale(reducedMotion ? 0 : POSES[state].clipSpeed);
    next.setLoop(THREE.LoopRepeat, Infinity);
    next.setEffectiveWeight(1);
    if (current.current && current.current !== next) next.crossFadeFrom(current.current, FADE, true);
    next.play();
    current.current = next;
    const tracks = next.getClip().tracks.map((tr) => tr.name);
    const drives = (bone: THREE.Bone | null) => !!bone && tracks.some((n) => n.startsWith(`${bone.name}.`));
    driven.current = { head: drives(head), neck: drives(neck) };
  }, [state, actions, reducedMotion, head, neck]);

  // ---- procedural layer -------------------------------------------------------------------------------------
  useFrame((three, delta) => {
    const p = POSES[state];
    const t = three.clock.elapsedTime;
    const l = live.current;
    const k = reducedMotion ? 1000 : 6; // reduced motion: jump straight to the pose, no easing wobble
    const pointer = three.pointer;

    // head targets: state pose + pointer follow + slow sway, eased
    const sway = reducedMotion ? 0 : Math.sin(t * 0.9) * p.sway;
    const pitchT = p.headPitch - pointer.y * 0.35 * p.followPointer;
    const yawT = p.headYaw + pointer.x * 0.6 * p.followPointer + sway;
    const rollT = p.headRoll + sway * 0.6;
    l.pitch = THREE.MathUtils.damp(l.pitch, pitchT, k, delta);
    l.yaw = THREE.MathUtils.damp(l.yaw, yawT, k, delta);
    l.roll = THREE.MathUtils.damp(l.roll, rollT, k, delta);
    if (head) {
      if (!driven.current.head && rest.head) head.quaternion.copy(rest.head);
      head.rotation.x += l.pitch;
      head.rotation.y += l.yaw;
      head.rotation.z += l.roll;
    }
    if (neck) {
      if (!driven.current.neck && rest.neck) neck.quaternion.copy(rest.neck);
      neck.rotation.x += l.pitch * 0.35;
    }

    // face: state expression, speaking pulse (mouth stand-in), periodic blink
    let surprisedT = p.surprised;
    if (state === "speaking" && !reducedMotion) {
      // placeholder has no mouth morph: a syllable-like pulse on "Surprised" reads as talking
      surprisedT = 0.12 + 0.38 * Math.max(0, Math.sin(t * 11) * Math.sin(t * 3.7 + 1));
    }
    l.surprised = THREE.MathUtils.damp(l.surprised, surprisedT, state === "speaking" ? 18 : 5, delta);
    l.sad = THREE.MathUtils.damp(l.sad, p.sad, 5, delta);
    l.angry = THREE.MathUtils.damp(l.angry, p.angry, 5, delta);

    nextBlink.current -= delta;
    if (!reducedMotion && nextBlink.current <= 0) {
      l.blink = 1;
      nextBlink.current = 2.5 + Math.random() * 3.5;
    }
    l.blink = THREE.MathUtils.damp(l.blink, 0, 16, delta);

    for (const m of faces) {
      const dict = m.morphTargetDictionary!;
      const inf = m.morphTargetInfluences!;
      const set = (name: string | undefined, v: number) => {
        if (name && dict[name] !== undefined) inf[dict[name]] = THREE.MathUtils.clamp(v, 0, 1);
      };
      set(MODEL_SPEC.morphs.surprised, l.surprised);
      set(MODEL_SPEC.morphs.sad, l.sad);
      if (MODEL_SPEC.morphs.blink) {
        set(MODEL_SPEC.morphs.blink, l.blink);
        set(MODEL_SPEC.morphs.angry, l.angry);
      } else {
        // placeholder blink: a quick brow-down squint on "Angry", blended with the state's own anger
        set(MODEL_SPEC.morphs.angry, Math.max(l.angry, l.blink * 0.55));
      }
    }

    // body: happy bounce, eased
    const yT = reducedMotion ? 0 : Math.abs(Math.sin(t * 5)) * p.bob;
    l.y = THREE.MathUtils.damp(l.y, yT, 10, delta);
    if (group.current) group.current.position.y = l.y;
  });
}
