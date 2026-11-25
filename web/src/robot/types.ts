/** The robot's behaviour states. Drive them through the `state` prop; never animate the model directly. */
export type RobotState = "idle" | "listening" | "thinking" | "speaking" | "happy" | "error";

export const ROBOT_STATES: RobotState[] = ["idle", "listening", "thinking", "speaking", "happy", "error"];

export interface ChatMessage {
  id: string;
  role: "assistant" | "user";
  text: string;
}

/** Everything the 3D layer needs to know. Kept tiny so the scene re-renders only when it truly changes. */
export interface RobotViewProps {
  state: RobotState;
  /** "launcher" = small floating robot; "header" = compact robot in the open panel. */
  variant: "launcher" | "header";
  /** Pause rendering (panel closed / tab hidden / scrolled away). */
  active: boolean;
  reducedMotion: boolean;
}

/** Names the code expects on the model. The placeholder lacks some; see MODEL_NOTES in useRobotAnimation.ts. */
export interface ModelSpec {
  url: string;
  clips: Partial<Record<RobotState, string>>;
  headBone: string;
  neckBone: string;
  morphs: { surprised?: string; sad?: string; angry?: string; blink?: string; mouthOpen?: string; smile?: string };
}
