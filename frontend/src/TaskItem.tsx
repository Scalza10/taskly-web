// One task on the List screen: the round box ticks it (unticking sends it back to New), click the
// title to rename (Enter or leaving the field saves, Escape cancels), the chip shows its stage,
// the calendar chip its due date (on an open task without one, just the calendar) and opens the
// due date picker, the timer button (open tasks) focuses on it on the Focus screen, × deletes.
// A task opened from search scrolls into view and lights up for a moment (found).
import { CalendarDays, CalendarPlus, Check, Timer, X } from "lucide-react";
import { useEffect, useRef, useState, type FocusEvent, type KeyboardEvent } from "react";
import type { Task } from "./api";
import { dueOf } from "./due";
import { DuePicker } from "./DuePicker";
import { stage } from "./stages";
import type { Enqueue } from "./useLocal";

type Props = { task: Task; today: string; enqueue: Enqueue; onFocus: (taskId: string) => void; found?: boolean };

export function TaskItem({ task, today, enqueue, onFocus, found = false }: Props) {
  const [editing, setEditing] = useState(false);
  const [picking, setPicking] = useState(false);
  const cancelled = useRef(false);
  const item = useRef<HTMLLIElement>(null);

  useEffect(() => {
    if (found) item.current?.scrollIntoView({ block: "center" });
  }, [found]);
  const path = `/api/tasks/${task.id}`;
  const done = task.status === "done";

  function onKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (event.key === "Enter") event.currentTarget.blur();
    if (event.key === "Escape") {
      cancelled.current = true;
      event.currentTarget.blur();
    }
  }

  function onBlur(event: FocusEvent<HTMLInputElement>) {
    setEditing(false);
    if (cancelled.current) {
      cancelled.current = false;
      return;
    }
    const newTitle = event.currentTarget.value.trim();
    if (newTitle && newTitle !== task.title) void enqueue({ method: "PATCH", path, body: { title: newTitle } });
  }

  function pickDue(dueDate: string | null) {
    setPicking(false);
    if (dueDate !== task.due_date) void enqueue({ method: "PATCH", path, body: { due_date: dueDate } });
  }

  const due = dueOf(task, today);

  const by = [task.created_by && `added by ${task.created_by}`, task.done_by && `done by ${task.done_by}`].filter(Boolean).join(" · ");
  const classes = ["task", done && "done", task.pending && "pending", found && "found"].filter(Boolean).join(" ");

  return (
    <li ref={item} className={classes}>
      <button
        type="button"
        className="check"
        role="checkbox"
        aria-checked={done}
        aria-label={`done: ${task.title}`}
        onClick={() => void enqueue({ method: "PATCH", path, body: { status: done ? "new" : "done" } })}
      >
        {done && <Check size={14} strokeWidth={3.5} aria-hidden="true" />}
      </button>
      {editing ? (
        <input className="title" aria-label="title" defaultValue={task.title} maxLength={500} autoFocus onKeyDown={onKeyDown} onBlur={onBlur} />
      ) : (
        <span className="title" onClick={() => setEditing(true)}>{task.title}</span>
      )}
      {/* One wrapping row on a phone; on a desktop the chip goes right and the details stay under the title. */}
      <span className="meta">
        <span className={`chip chip-${task.status}`}>{stage(task.status).label}</span>
        <span className="details">
          {(due || !done) && (
            <button
              type="button"
              className={due ? `due due-${due.kind}` : "due due-add"}
              aria-expanded={picking}
              aria-label={due ? `due ${due.full}: change the due date of "${task.title}"` : `add a due date to "${task.title}"`}
              title={due ? due.full : "Add a due date"}
              onClick={() => setPicking(!picking)}
            >
              {due ? <CalendarDays aria-hidden="true" /> : <CalendarPlus aria-hidden="true" />}
              {due?.label}
            </button>
          )}
          {by && <small className="by">{by}</small>}
        </span>
      </span>
      {!done && (
        <button type="button" className="focus-on" aria-label={`focus on "${task.title}"`} title="Focus on this" onClick={() => onFocus(task.id)}>
          <Timer size={18} aria-hidden="true" />
        </button>
      )}
      <button type="button" className="delete" aria-label={`delete "${task.title}"`} onClick={() => void enqueue({ method: "DELETE", path })}>
        <X size={18} aria-hidden="true" />
      </button>
      {picking && <DuePicker title={task.title} value={task.due_date} today={today} onPick={pickDue} onCancel={() => setPicking(false)} />}
    </li>
  );
}
