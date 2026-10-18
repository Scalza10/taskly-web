// The due date picker, a row under a task on the List screen (its calendar chip opens it):
// Today, Tomorrow, any day (the device's own date picker, then Set), or no due date; and an
// optional time for any of them (an appointment), in this device's time. Tomorrow without a time
// means by noon tomorrow. Picking one closes it; so do Cancel and Escape. note: the time where it
// was set, when that reads differently here.
import { useState, type FormEvent, type KeyboardEvent } from "react";
import { addDays, type DueInput } from "./due";

// "Tomorrow" is by noon tomorrow, in this device's time zone, unless a time is typed.
const TOMORROW_NOON = "12:00";

type Props = {
  title: string; value: DueInput | null; note?: string; today: string;
  onPick: (due: DueInput | null) => void; onCancel: () => void;
};

export function DuePicker({ title, value, note, today, onPick, onCancel }: Props) {
  // Set, not the field's change: typing a year digit by digit makes dates like 0002-10-17 on the way.
  const [day, setDay] = useState(value?.date ?? "");
  const [time, setTime] = useState(value?.time ?? "");
  const pick = (date: string) => onPick({ date, time: time || null });

  function submit(event: FormEvent) {
    event.preventDefault();
    if (day) pick(day);
  }

  function onKeyDown(event: KeyboardEvent) {
    if (event.key === "Escape") onCancel();
  }

  return (
    <form className="due-picker" aria-label={`due date of "${title}"`} onSubmit={submit} onKeyDown={onKeyDown}>
      <button type="button" className="action" onClick={() => pick(today)}>Today</button>
      <button type="button" className="action" title="Tomorrow by noon, or at the time typed"
        onClick={() => onPick({ date: addDays(today, 1), time: time || TOMORROW_NOON })}>Tomorrow</button>
      <span className="due-day">
        <input type="date" aria-label="due date" value={day} onChange={(e) => setDay(e.target.value)} />
        <input type="time" aria-label="due time (optional)" value={time} onChange={(e) => setTime(e.target.value)} />
        {time && <button type="button" className="text" onClick={() => setTime("")}>No time</button>}
        <button type="submit" className="primary" disabled={!day}>Set</button>
      </span>
      {value && <button type="button" className="text" onClick={() => onPick(null)}>No due date</button>}
      <button type="button" className="text" onClick={onCancel}>Cancel</button>
      {note && <p className="due-note">That's {note}.</p>}
    </form>
  );
}
