// The due date picker, a row under a task on the List screen (its calendar chip opens it):
// Today, Tomorrow, any day (the device's own date picker, then Set), or no due date. Picking one
// closes it; so do Cancel and Escape.
import { useState, type FormEvent, type KeyboardEvent } from "react";
import { addDays } from "./due";

type Props = { title: string; value: string | null; today: string; onPick: (dueDate: string | null) => void; onCancel: () => void };

export function DuePicker({ title, value, today, onPick, onCancel }: Props) {
  // Set, not the field's change: typing a year digit by digit makes dates like 0002-10-17 on the way.
  const [day, setDay] = useState(value ?? "");

  function submit(event: FormEvent) {
    event.preventDefault();
    if (day) onPick(day);
  }

  function onKeyDown(event: KeyboardEvent) {
    if (event.key === "Escape") onCancel();
  }

  return (
    <form className="due-picker" aria-label={`due date of "${title}"`} onSubmit={submit} onKeyDown={onKeyDown}>
      <button type="button" className="action" onClick={() => onPick(today)}>Today</button>
      <button type="button" className="action" onClick={() => onPick(addDays(today, 1))}>Tomorrow</button>
      <span className="due-day">
        <input type="date" aria-label="due date" value={day} onChange={(e) => setDay(e.target.value)} />
        <button type="submit" className="primary" disabled={!day}>Set</button>
      </span>
      {value && <button type="button" className="text" onClick={() => onPick(null)}>No due date</button>}
      <button type="button" className="text" onClick={onCancel}>Cancel</button>
    </form>
  );
}
