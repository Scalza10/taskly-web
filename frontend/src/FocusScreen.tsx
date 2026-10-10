// The Focus screen: a pomodoro timer (focus, short break, long break) next to the task being
// worked on: the one picked (here, or with a task's Focus button), else the current list's first
// task in progress (else its first new one). Play focuses on the task shown; a finished focus
// session counts for it ("3 sessions on this task", kept on this device only). The timer itself
// lives in ListsPage (useTimer), so it keeps running on the other screens.
import { ChevronDown, RotateCcw } from "lucide-react";
import type { Task } from "./api";
import { PauseIcon, PlayIcon } from "./Chrome";
import { focusTask } from "./stages";
import { clock, DURATION, pick, remainingAt, reset, runLabel, SESSIONS, setMode, toggle, type Mode, type Timer } from "./timer";
import { useNow, type TimerAction } from "./useTimer";
import { useWide } from "./useWide";

const MODES: { mode: Mode; label: string; short: string; caption: string }[] = [
  { mode: "focus", label: "Focus", short: "Focus", caption: "Focus session" },
  { mode: "short", label: "Short break", short: "Short", caption: "Short break" },
  { mode: "long", label: "Long break", short: "Long", caption: "Long break" },
];

const RING = 2 * Math.PI * 180; // the ring's length, r=180 on a 400 viewBox
const PEBBLES = ["pebble-a", "pebble-b", "pebble-c", "pebble-d"];

export function FocusScreen({ tasks, timer, act }: { tasks: Task[]; timer: Timer; act: TimerAction }) {
  const wide = useWide();
  const now = useNow(timer.running);
  const left = remainingAt(timer, now);
  const total = DURATION[timer.mode];
  const label = runLabel(timer, now);
  const shown = focusTask(tasks, timer.taskId);
  const count = shown ? timer.counts[shown.id] ?? 0 : 0;
  const caption = MODES.find((m) => m.mode === timer.mode)!.caption;

  const pebbles = (
    <div className="pebbles" role="img" aria-label={`${timer.sessions} of ${SESSIONS} focus sessions done`}>
      {PEBBLES.map((shape, i) => <span key={shape} className={`pebble ${shape}${i < timer.sessions ? " filled" : ""}`} />)}
    </div>
  );

  const current = shown ? (
    <label className="select focus-pick">
      <select aria-label="Working on" value={shown.id} onChange={(e) => act((t) => pick(t, e.target.value))}>
        {tasks.filter((task) => task.status !== "done").map((task) => <option key={task.id} value={task.id}>{task.title}</option>)}
      </select>
      <ChevronDown size={wide ? 18 : 16} strokeWidth={2.5} aria-hidden="true" />
    </label>
  ) : (
    <span className="working-on">Nothing in progress</span>
  );
  const sessionsOnIt = count > 0 && <span className="sessions-text">{count === 1 ? "1 session" : `${count} sessions`} on this task</span>;

  return (
    <div className="screen focus-screen">
      <div className="timer">
        <div className="pills" role="group" aria-label="Timer">
          {MODES.map((m) => (
            <button key={m.mode} type="button" className="pill" aria-pressed={timer.mode === m.mode} onClick={() => act((t) => setMode(t, m.mode))}>
              {wide ? m.label : m.short}
            </button>
          ))}
        </div>

        <div className="dial">
          <span className="dial-blob pebble-a" aria-hidden="true" />
          <span className="dial-blob dial-blob-2 pebble-b" aria-hidden="true" />
          <svg viewBox="0 0 400 400" aria-hidden="true">
            <circle className="ring-track" cx="200" cy="200" r="180" strokeWidth={wide ? 6 : 7} />
            <circle
              className="ring"
              cx="200"
              cy="200"
              r="180"
              strokeWidth={wide ? 8 : 10}
              strokeDasharray={RING}
              strokeDashoffset={RING * (left / total)}
              transform="rotate(-90 200 200)"
            />
          </svg>
          <div className="dial-face">
            <span className="digits" role="timer" aria-label={`${Math.floor(left / 60)} minutes ${left % 60} seconds left`}>{clock(left)}</span>
            <span className="caption">{caption}</span>
          </div>
        </div>

        <div className="controls">
          <button type="button" className="round outline reset" aria-label="Reset" onClick={() => act(reset)}>
            <RotateCcw size={20} aria-hidden="true" />
          </button>
          <button type="button" className="play pebble-play" aria-label={label} onClick={() => act((t, at) => toggle(t.running ? t : pick(t, shown?.id ?? null), at))}>
            {timer.running ? <PauseIcon size={wide ? 26 : 24} /> : <PlayIcon size={wide ? 26 : 24} />}
          </button>
          <span className="run-label" aria-hidden="true">{label}</span>
        </div>
      </div>

      {wide ? (
        <aside className="focus-side">
          <div className="side-card">
            <span className="side-label">Working on</span>
            {current}
            {sessionsOnIt}
          </div>
          <div className="side-card">
            <span className="side-label">Sessions</span>
            {pebbles}
            <span className="sessions-text">{timer.sessions} of {SESSIONS} before a long break</span>
          </div>
        </aside>
      ) : (
        <div className="side-card focus-card">
          <div className="focus-card-text">
            <span className="side-label">Working on</span>
            {current}
            {sessionsOnIt}
          </div>
          {pebbles}
        </div>
      )}
    </div>
  );
}
