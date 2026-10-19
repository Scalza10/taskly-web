// The due date picker, a row under a task on the List screen (its calendar chip opens it):
// Today, Tomorrow, any day (the device's own date picker, then Set), or no due date; an optional
// time for any of them (an appointment), in this device's time; and how it repeats from that day
// (repeat.ts): a choice named after the day, or Custom (every how many days, weeks, months or
// years; for weeks, on which days; on the schedule, or counted from the day it's done). Tomorrow
// without a time means by noon tomorrow. Picking one closes it; so do Cancel and Escape. note: the
// time where it was set, when that reads differently here.
import { ChevronDown } from "lucide-react";
import { useState, type FormEvent, type KeyboardEvent } from "react";
import { addDays, type DueInput } from "./due";
import { buildRule, choiceOf, dayOfWeek, presets, type Choice, type Custom, type Freq } from "./repeat";

// "Tomorrow" is by noon tomorrow, in this device's time zone, unless a time is typed.
const TOMORROW_NOON = "12:00";
const UNITS: [Freq, string][] = [["DAILY", "day"], ["WEEKLY", "week"], ["MONTHLY", "month"], ["YEARLY", "year"]];
const WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];

type Props = {
  title: string; value: DueInput | null; note?: string; today: string;
  onPick: (due: DueInput | null) => void; onCancel: () => void;
};

export function DuePicker({ title, value, note, today, onPick, onCancel }: Props) {
  // Set, not the field's change: typing a year digit by digit makes dates like 0002-10-17 on the way.
  const [day, setDay] = useState(value?.date ?? "");
  const [time, setTime] = useState(value?.time ?? "");
  const [repeat, setRepeat] = useState(() => choiceOf(value?.repeat ?? null, value?.date ?? ""));
  const [every, setEvery] = useState(String(repeat.custom.interval)); // as typed
  const [changed, setChanged] = useState(false);

  // The task's own rule, as it is, until the date or the repeat changes (one on the 31st, opened
  // on Feb 28, stays on the 31st); else the one the choice makes for the date picked.
  const ruleFor = (date: string) =>
    !changed && date === value?.date ? value.repeat : buildRule(repeat.choice, { ...repeat.custom, interval: Number(every) }, date);
  const pick = (date: string, at = time || null) => onPick({ date, time: at, repeat: ruleFor(date) });

  function choose(choice: Choice, custom: Partial<Custom> = {}) {
    setRepeat({ choice, custom: { ...repeat.custom, ...custom } });
    setChanged(true);
  }

  // None picked means the date's own weekday (buildRule), so that one shows as picked.
  const days = repeat.custom.days.length || !day ? repeat.custom.days : [dayOfWeek(day)];
  function toggleDay(weekday: number) {
    choose("custom", { days: days.includes(weekday) ? days.filter((d) => d !== weekday) : [...days, weekday].sort() });
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    if (day) pick(day);
  }

  function onKeyDown(event: KeyboardEvent) {
    if (event.key === "Escape") onCancel();
  }

  const { custom } = repeat;
  return (
    <form className="due-picker" aria-label={`due date of "${title}"`} onSubmit={submit} onKeyDown={onKeyDown}>
      <button type="button" className="action" onClick={() => pick(today)}>Today</button>
      <button type="button" className="action" title="Tomorrow by noon, or at the time typed"
        onClick={() => pick(addDays(today, 1), time || TOMORROW_NOON)}>Tomorrow</button>
      <span className="due-day">
        <input type="date" aria-label="due date" value={day} onChange={(e) => setDay(e.target.value)} />
        <input type="time" aria-label="due time (optional)" value={time} onChange={(e) => setTime(e.target.value)} />
        {time && <button type="button" className="text" onClick={() => setTime("")}>No time</button>}
        <button type="submit" className="primary" disabled={!day}>Set</button>
      </span>
      {value && <button type="button" className="text" onClick={() => onPick(null)}>No due date</button>}
      <button type="button" className="text" onClick={onCancel}>Cancel</button>
      <span className="due-repeat">
        <label className="select">
          <select aria-label="repeat" value={repeat.choice} onChange={(e) => choose(e.target.value as Choice)}>
            {presets(day).map(({ choice, label }) => <option key={choice} value={choice}>{label}</option>)}
          </select>
          <ChevronDown size={14} strokeWidth={2.5} aria-hidden="true" />
        </label>
        {repeat.choice === "custom" && (
          <span className="repeat-custom">
            <label className="repeat-every">
              Every
              <input type="number" inputMode="numeric" min={1} max={999} aria-label="every how many" value={every}
                onChange={(e) => { setEvery(e.target.value); setChanged(true); }} />
            </label>
            <label className="select">
              <select aria-label="days, weeks, months or years" value={custom.freq} onChange={(e) => choose("custom", { freq: e.target.value as Freq })}>
                {UNITS.map(([freq, unit]) => <option key={freq} value={freq}>{Number(every) === 1 ? unit : `${unit}s`}</option>)}
              </select>
              <ChevronDown size={14} strokeWidth={2.5} aria-hidden="true" />
            </label>
            {custom.freq === "WEEKLY" && !custom.fromDone && (
              <span className="weekdays" role="group" aria-label="on these days">
                {WEEKDAYS.map((name, weekday) => (
                  <button key={name} type="button" className="weekday" aria-pressed={days.includes(weekday)} aria-label={name}
                    title={name} onClick={() => toggleDay(weekday)}>{name[0]}</button>
                ))}
              </span>
            )}
            <label className="select">
              <select aria-label="counted from" value={custom.fromDone ? "done" : "schedule"}
                onChange={(e) => choose("custom", { fromDone: e.target.value === "done" })}>
                <option value="schedule">on the schedule</option>
                <option value="done">after it's done</option>
              </select>
              <ChevronDown size={14} strokeWidth={2.5} aria-hidden="true" />
            </label>
          </span>
        )}
      </span>
      {note && <p className="due-note">That's {note}.</p>}
    </form>
  );
}
