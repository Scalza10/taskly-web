// One task on the List screen: the round box ticks it (unticking sends it back to New), click the
// title to rename (Enter or leaving the field saves, Escape cancels), the notes' first two lines
// show under it (click them to read them all and edit), the chip shows its stage, the calendar
// chip its due date and time (on an open task without one, just the calendar; a repeating one adds
// the repeat mark) and opens the due date picker, the notes button opens the notes (on an open task without any, adds them), the
// timer button (open tasks) focuses on it on the Focus screen, × deletes. One editor opens at a time.
// A task opened from search scrolls into view and lights up for a moment (found).
import { CalendarDays, CalendarPlus, Check, NotebookPen, NotebookText, Repeat, Timer, X } from "lucide-react";
import { useEffect, useRef, useState, type FocusEvent, type KeyboardEvent, type MouseEvent } from "react";
import type { Task } from "./api";
import { deviceZone, dueInput, dueOf, localDay, type DueInput } from "./due";
import { DuePicker } from "./DuePicker";
import { describeRule } from "./repeat";
import { NotesEditor, NotesText } from "./TaskNotes";
import { stage, statusChange } from "./stages";
import type { Enqueue } from "./useLocal";

type Props = { task: Task; now: Date; enqueue: Enqueue; onFocus: (taskId: string) => void; found?: boolean };
type Panel = "due" | "notes" | null;

export function TaskItem({ task, now, enqueue, onFocus, found = false }: Props) {
  const [editing, setEditing] = useState(false);
  const [panel, setPanel] = useState<Panel>(null);
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

  // A time is kept with this device's time zone, so it is the same moment on every device. The
  // date, time and repeat go together, so the rule's day is the date's as this device sees it.
  function pickDue(picked: DueInput | null) {
    setPanel(null);
    const current = dueInput(task);
    if (picked?.date === current?.date && picked?.time === current?.time && picked?.repeat === current?.repeat) return;
    const body = picked
      ? { due_date: picked.date, due_time: picked.time, due_zone: picked.time ? deviceZone() : null, repeat: picked.repeat }
      : { due_date: null };
    void enqueue({ method: "PATCH", path, body });
  }

  function saveNotes(notes: string | null) {
    setPanel(null);
    if (notes !== task.notes) void enqueue({ method: "PATCH", path, body: { notes } });
  }

  // Like the title, a click opens the editor; one on a link opens its page instead.
  function onNoteClick(event: MouseEvent) {
    if (!(event.target as Element).closest("a")) setPanel("notes");
  }

  const toggle = (which: Panel) => setPanel(panel === which ? null : which);
  const due = dueOf(task, now);
  const repeats = task.repeat ? describeRule(task.repeat) : undefined;
  const dueText = due && (repeats ? `${due.full} · ${repeats}` : due.full);
  const noteShown = Boolean(task.notes) && panel !== "notes";

  const by = [task.created_by && `added by ${task.created_by}`, task.done_by && `done by ${task.done_by}`].filter(Boolean).join(" · ");
  const classes = ["task", done && "done", task.pending && "pending", found && "found", noteShown && "has-notes"].filter(Boolean).join(" ");

  return (
    <li ref={item} className={classes}>
      <button
        type="button"
        className="check"
        role="checkbox"
        aria-checked={done}
        aria-label={`done: ${task.title}`}
        onClick={() => void enqueue(statusChange(task, done ? "new" : "done")!)}
      >
        {done && <Check size={14} strokeWidth={3.5} aria-hidden="true" />}
      </button>
      {editing ? (
        <input className="title" aria-label="title" defaultValue={task.title} maxLength={500} autoFocus onKeyDown={onKeyDown} onBlur={onBlur} />
      ) : (
        <span className="title" onClick={() => setEditing(true)}>{task.title}</span>
      )}
      {noteShown && <p className="task-note" onClick={onNoteClick}><NotesText text={task.notes!} /></p>}
      {/* One wrapping row on a phone; on a desktop the chip goes right and the details stay under the title. */}
      <span className="meta">
        <span className={`chip chip-${task.status}`}>{stage(task.status).label}</span>
        <span className="details">
          {(due || !done) && (
            <button
              type="button"
              className={due ? `due due-${due.kind}` : "due due-add"}
              aria-expanded={panel === "due"}
              aria-label={due ? `due ${dueText}: change the due date of "${task.title}"` : `add a due date to "${task.title}"`}
              title={dueText ?? "Add a due date"}
              onClick={() => toggle("due")}
            >
              {due ? <CalendarDays aria-hidden="true" /> : <CalendarPlus aria-hidden="true" />}
              {due?.label}
              {due && repeats && <Repeat aria-hidden="true" />}
            </button>
          )}
          {(task.notes || !done) && (
            <button
              type="button"
              className={task.notes ? "due due-add notes-button has" : "due due-add notes-button"}
              aria-expanded={panel === "notes"}
              aria-label={task.notes ? `notes of "${task.title}"` : `add notes to "${task.title}"`}
              title={task.notes ? "Notes" : "Add notes"}
              onClick={() => toggle("notes")}
            >
              {task.notes ? <NotebookText aria-hidden="true" /> : <NotebookPen aria-hidden="true" />}
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
      {panel === "due" && (
        <DuePicker title={task.title} value={dueInput(task)} note={due?.note} today={localDay(now)} onPick={pickDue} onCancel={() => setPanel(null)} />
      )}
      {panel === "notes" && <NotesEditor title={task.title} value={task.notes} onSave={saveNotes} onCancel={() => setPanel(null)} />}
    </li>
  );
}
