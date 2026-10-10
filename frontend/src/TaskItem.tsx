// One task on the List screen: the round box ticks it (unticking sends it back to New), click the
// title to rename (Enter or leaving the field saves, Escape cancels), the chip shows its stage,
// × deletes. A task opened from search scrolls into view and lights up for a moment (found).
import { Check, X } from "lucide-react";
import { useEffect, useRef, useState, type FocusEvent, type KeyboardEvent } from "react";
import type { Task } from "./api";
import { stage } from "./stages";
import type { Enqueue } from "./useLocal";

export function TaskItem({ task, enqueue, found = false }: { task: Task; enqueue: Enqueue; found?: boolean }) {
  const [editing, setEditing] = useState(false);
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
      {by && <small className="by">{by}</small>}
      <span className={`chip chip-${task.status}`}>{stage(task.status).label}</span>
      <button type="button" className="delete" aria-label={`delete "${task.title}"`} onClick={() => void enqueue({ method: "DELETE", path })}>
        <X size={18} aria-hidden="true" />
      </button>
    </li>
  );
}
