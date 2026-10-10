// The Focus screen's pomodoro timer: focus sessions and short and long breaks. Pure functions of
// the time (Date.now() in ms) so it's easy to test. While it runs it keeps the moment it ends, not
// a count of ticks, so a phone that sleeps or a background tab still shows the right time.
// It stays on this device (localStorage, see useTimer.ts); the server knows nothing of it, nor of
// the task picked to focus on and how many focus sessions each task has had.
export type Mode = "focus" | "short" | "long";

export type Timer = {
  mode: Mode;
  running: boolean;
  remaining: number; // seconds left, while stopped
  endsAt: number | null; // ms timestamp, while running
  sessions: number; // focus sessions finished, 0–4
  taskId: string | null; // the task being focused on: a finished focus session counts for it
  counts: Record<string, number>; // focus sessions finished per task id
};

export const DURATION: Record<Mode, number> = { focus: 25 * 60, short: 5 * 60, long: 15 * 60 };
export const SESSIONS = 4; // before a long break

export function initialTimer(): Timer {
  return { mode: "focus", running: false, remaining: DURATION.focus, endsAt: null, sessions: 0, taskId: null, counts: {} };
}

// Whole seconds left, rounded up: a fresh 25:00 shows 25:00 for its first second.
export function remainingAt(timer: Timer, now: number): number {
  if (!timer.running || timer.endsAt === null) return timer.remaining;
  return Math.max(0, Math.ceil((timer.endsAt - now) / 1000));
}

// Play or pause. Play at 0:00 starts the mode again from full.
export function toggle(timer: Timer, now: number): Timer {
  if (timer.running) return { ...timer, running: false, remaining: remainingAt(timer, now), endsAt: null };
  const seconds = timer.remaining > 0 ? timer.remaining : DURATION[timer.mode];
  return { ...timer, running: true, remaining: seconds, endsAt: now + seconds * 1000 };
}

export function reset(timer: Timer): Timer {
  return setMode(timer, timer.mode);
}

export function setMode(timer: Timer, mode: Mode): Timer {
  return { ...timer, mode, running: false, remaining: DURATION[mode], endsAt: null };
}

// Focus on a task (or none); the timer itself carries on.
export function pick(timer: Timer, taskId: string | null): Timer {
  return { ...timer, taskId };
}

// At 0:00 the timer stops. A focus session counts (up to four) and for the picked task; a
// finished long break starts the four again. Returns the same object while there's nothing to do.
export function finishDue(timer: Timer, now: number): Timer {
  if (!timer.running || timer.endsAt === null || timer.endsAt > now) return timer;
  const focus = timer.mode === "focus";
  const sessions = focus ? Math.min(SESSIONS, timer.sessions + 1) : timer.mode === "long" ? 0 : timer.sessions;
  const counts = focus && timer.taskId ? { ...timer.counts, [timer.taskId]: (timer.counts[timer.taskId] ?? 0) + 1 } : timer.counts;
  return { ...timer, running: false, remaining: 0, endsAt: null, sessions, counts };
}

// Forget the tasks that are gone (deleted, or in a list left). The same object if none are.
export function keepCounts(timer: Timer, ids: Set<string>): Timer {
  const gone = Object.keys(timer.counts).some((id) => !ids.has(id)) || (timer.taskId !== null && !ids.has(timer.taskId));
  if (!gone) return timer;
  const counts = Object.fromEntries(Object.entries(timer.counts).filter(([id]) => ids.has(id)));
  return { ...timer, taskId: timer.taskId !== null && ids.has(timer.taskId) ? timer.taskId : null, counts };
}

export function runLabel(timer: Timer, now: number): "Start" | "Pause" | "Resume" {
  if (timer.running) return "Pause";
  const left = remainingAt(timer, now);
  return left > 0 && left < DURATION[timer.mode] ? "Resume" : "Start";
}

export function clock(seconds: number): string {
  return `${String(Math.floor(seconds / 60)).padStart(2, "0")}:${String(seconds % 60).padStart(2, "0")}`;
}

// A timer saved on this device, if it still makes sense.
export function parseTimer(json: string | null): Timer | undefined {
  let value: unknown;
  try {
    value = JSON.parse(json ?? "");
  } catch {
    return undefined;
  }
  const t = value as Partial<Timer> | null;
  if (!t || typeof t !== "object") return undefined;
  const whole = (n: unknown, max: number) => typeof n === "number" && Number.isInteger(n) && n >= 0 && n <= max;
  if (t.mode !== "focus" && t.mode !== "short" && t.mode !== "long") return undefined;
  if (typeof t.running !== "boolean" || !whole(t.sessions, SESSIONS) || !whole(t.remaining, DURATION[t.mode])) return undefined;
  if (t.running ? typeof t.endsAt !== "number" : t.endsAt !== null) return undefined;
  // A timer saved before tasks were picked has neither taskId nor counts.
  const taskId = t.taskId ?? null;
  const counts = t.counts ?? {};
  if (taskId !== null && typeof taskId !== "string") return undefined;
  if (typeof counts !== "object" || counts === null || Array.isArray(counts)) return undefined;
  if (!Object.values(counts).every((n) => whole(n, Number.MAX_SAFE_INTEGER))) return undefined;
  return { mode: t.mode, running: t.running, remaining: t.remaining!, endsAt: t.endsAt!, sessions: t.sessions!, taskId, counts };
}
