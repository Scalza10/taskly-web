import { expect, test } from "vitest";
import { DURATION, finishDue, initialTimer, keepCounts, parseTimer, pick, remainingAt, reset, runLabel, setMode, toggle, type Timer } from "./timer";

const t0 = 1_000_000;
const s = (seconds: number) => t0 + seconds * 1000;

test("a new timer is a full focus session, stopped", () => {
  const timer = initialTimer();
  expect(timer).toMatchObject({ mode: "focus", running: false, sessions: 0, taskId: null, counts: {} });
  expect(remainingAt(timer, t0)).toBe(25 * 60);
  expect(runLabel(timer, t0)).toBe("Start");
});

test("it counts down from timestamps, so a background tab stays right", () => {
  const running = toggle(initialTimer(), t0);
  expect(running.running).toBe(true);
  expect(remainingAt(running, t0)).toBe(1500);
  expect(remainingAt(running, s(0.4))).toBe(1500); // shows a full second until it has passed
  expect(remainingAt(running, s(1))).toBe(1499);
  expect(remainingAt(running, s(600))).toBe(900);
  expect(runLabel(running, s(600))).toBe("Pause");
});

test("pause keeps the time left; play resumes from there", () => {
  const paused = toggle(toggle(initialTimer(), t0), s(60));
  expect(paused.running).toBe(false);
  expect(remainingAt(paused, s(500))).toBe(1440);
  expect(runLabel(paused, s(500))).toBe("Resume");
  const resumed = toggle(paused, s(500));
  expect(remainingAt(resumed, s(510))).toBe(1430);
});

test("at zero it stops and a focus session counts, up to four", () => {
  const running = toggle(initialTimer(), t0);
  expect(finishDue(running, s(1499))).toBe(running); // not yet
  const finished = finishDue(running, s(1500));
  expect(finished).toMatchObject({ running: false, sessions: 1 });
  expect(remainingAt(finished, s(2000))).toBe(0);
  expect(runLabel(finished, s(2000))).toBe("Start");

  const four: Timer = { ...running, sessions: 4 };
  expect(finishDue(four, s(1500)).sessions).toBe(4);
});

test("a break doesn't count; a finished long break starts the four again", () => {
  const short = toggle(setMode({ ...initialTimer(), sessions: 2 }, "short"), t0);
  expect(finishDue(short, s(DURATION.short)).sessions).toBe(2);
  const long = toggle(setMode({ ...initialTimer(), sessions: 4 }, "long"), t0);
  expect(finishDue(long, s(DURATION.long)).sessions).toBe(0);
});

test("play at 0:00 starts the mode again from full", () => {
  const finished = finishDue(toggle(initialTimer(), t0), s(1500));
  const again = toggle(finished, s(3000));
  expect(again.running).toBe(true);
  expect(remainingAt(again, s(3001))).toBe(1499);
});

test("changing mode or reset stops and fills the timer", () => {
  const running = toggle(initialTimer(), t0);
  const short = setMode(running, "short");
  expect(short).toMatchObject({ mode: "short", running: false });
  expect(remainingAt(short, s(100))).toBe(300);
  const back = reset(toggle(short, s(100)));
  expect(back.running).toBe(false);
  expect(remainingAt(back, s(200))).toBe(300);
});

test("a stored timer is read back only if it makes sense", () => {
  const timer = toggle(initialTimer(), t0);
  expect(parseTimer(JSON.stringify(timer))).toEqual(timer);
  expect(parseTimer(null)).toBeUndefined();
  expect(parseTimer("{")).toBeUndefined();
  expect(parseTimer(JSON.stringify({ ...timer, mode: "nap" }))).toBeUndefined();
  expect(parseTimer(JSON.stringify({ ...timer, sessions: 9 }))).toBeUndefined();
});

test("a finished focus session counts for the task picked; a break or no task counts for none", () => {
  const running = toggle(pick(initialTimer(), "a"), t0);
  const once = finishDue(running, s(1500));
  expect(once).toMatchObject({ taskId: "a", counts: { a: 1 } });
  const twice = finishDue(toggle(once, s(2000)), s(3500));
  expect(twice.counts).toEqual({ a: 2 });
  expect(finishDue(toggle(pick(twice, "b"), s(4000)), s(5500)).counts).toEqual({ a: 2, b: 1 });

  const short = toggle(setMode(twice, "short"), s(4000));
  expect(finishDue(short, s(4000 + DURATION.short)).counts).toEqual({ a: 2 });
  expect(finishDue(toggle(initialTimer(), t0), s(1500)).counts).toEqual({});
});

test("picking a task doesn't stop or change the timer", () => {
  const running = toggle(initialTimer(), t0);
  expect(pick(running, "a")).toEqual({ ...running, taskId: "a" });
});

test("counts of tasks that are gone are dropped; nothing to drop keeps the same timer", () => {
  const timer: Timer = { ...initialTimer(), taskId: "gone", counts: { a: 2, gone: 1 } };
  expect(keepCounts(timer, new Set(["a", "b"]))).toEqual({ ...timer, taskId: null, counts: { a: 2 } });
  const kept = { ...timer, taskId: "a", counts: { a: 2 } };
  expect(keepCounts(kept, new Set(["a"]))).toBe(kept);
});

test("a timer stored by the page before tasks had counts still loads", () => {
  const old = { mode: "focus", running: false, remaining: 600, endsAt: null, sessions: 2 };
  expect(parseTimer(JSON.stringify(old))).toEqual({ ...old, taskId: null, counts: {} });
  const timer = { ...old, taskId: "a", counts: { a: 3 } };
  expect(parseTimer(JSON.stringify(timer))).toEqual(timer);
  expect(parseTimer(JSON.stringify({ ...timer, taskId: 7 }))).toBeUndefined();
  expect(parseTimer(JSON.stringify({ ...timer, counts: { a: -1 } }))).toBeUndefined();
  expect(parseTimer(JSON.stringify({ ...timer, counts: [] }))).toBeUndefined();
});
