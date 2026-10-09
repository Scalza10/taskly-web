// The pomodoro timer for React. It lives above the screens, so it keeps running on the List and
// the Board, and in localStorage, so it survives a reload or closing the installed app.
import { useCallback, useEffect, useState } from "react";
import { finishDue, initialTimer, parseTimer, type Timer } from "./timer";

const KEY = "taskly.timer";

function load(): Timer {
  try {
    return parseTimer(localStorage.getItem(KEY)) ?? initialTimer();
  } catch {
    return initialTimer(); // storage blocked
  }
}

export type TimerAction = (change: (timer: Timer, now: number) => Timer) => void;

export function useTimer(): [Timer, TimerAction] {
  const [timer, setTimer] = useState<Timer>(() => finishDue(load(), Date.now()));

  useEffect(() => {
    try {
      localStorage.setItem(KEY, JSON.stringify(timer));
    } catch {
      // not kept; harmless
    }
  }, [timer]);

  // Stop at 0:00 (and count the session), also if the page slept through it.
  useEffect(() => {
    if (!timer.running || timer.endsAt === null) return;
    const finish = () => setTimer((t) => finishDue(t, Date.now()));
    const wait = window.setTimeout(finish, Math.max(0, timer.endsAt - Date.now()) + 50);
    document.addEventListener("visibilitychange", finish);
    return () => {
      window.clearTimeout(wait);
      document.removeEventListener("visibilitychange", finish);
    };
  }, [timer]);

  const act = useCallback<TimerAction>((change) => {
    setTimer((t) => {
      const now = Date.now();
      return change(finishDue(t, now), now);
    });
  }, []);

  return [timer, act];
}

// The time, four times a second while the timer runs (so the display never skips a second).
export function useNow(running: boolean): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    setNow(Date.now());
    if (!running) return;
    const timer = window.setInterval(() => setNow(Date.now()), 250);
    return () => window.clearInterval(timer);
  }, [running]);
  return now;
}
