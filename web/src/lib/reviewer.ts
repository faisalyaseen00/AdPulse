import { useSyncExternalStore } from "react";

/** The reviewer's name, remembered in this browser. Approvals record it, so the team knows who decided. */
const KEY = "adpulse.reviewer";
const listeners = new Set<() => void>();

function read(): string {
  try {
    return localStorage.getItem(KEY) ?? "";
  } catch {
    return "";
  }
}

export function setReviewer(name: string) {
  try {
    localStorage.setItem(KEY, name.trim());
  } catch { /* storage blocked: name lasts for this page only */ }
  memory = name.trim();
  listeners.forEach((l) => l());
}

let memory = read();

export function useReviewer(): string {
  return useSyncExternalStore(
    (cb) => {
      listeners.add(cb);
      return () => listeners.delete(cb);
    },
    () => memory,
  );
}
