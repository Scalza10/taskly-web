// One task: tick it, click the title to rename (Enter or leaving the field saves, Escape cancels), × deletes.
import { useRef, useState, type FocusEvent, type KeyboardEvent } from "react";
import { api, type Task } from "./api";
import type { Change } from "./ListsPage";

export function TaskItem({ task, change }: { task: Task; change: Change }) {
  const [editing, setEditing] = useState(false);
  const cancelled = useRef(false);
  const path = `/api/tasks/${task.id}`;

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
    if (newTitle && newTitle !== task.title) void change(() => api("PATCH", path, { title: newTitle }));
  }

  return (
    <li className={task.done ? "done" : undefined}>
      <input
        type="checkbox"
        checked={task.done}
        aria-label="done"
        onChange={(e) => {
          const done = e.target.checked;
          void change(() => api("PATCH", path, { done }));
        }}
      />
      <div className="body">
        {editing ? (
          <input
            className="title"
            aria-label="title"
            defaultValue={task.title}
            maxLength={500}
            autoFocus
            onKeyDown={onKeyDown}
            onBlur={onBlur}
          />
        ) : (
          <span className="title" onClick={() => setEditing(true)}>{task.title}</span>
        )}
        {(task.created_by || task.done_by) && (
          <small className="by">
            {[task.created_by && `added by ${task.created_by}`, task.done_by && `done by ${task.done_by}`]
              .filter(Boolean)
              .join(" · ")}
          </small>
        )}
      </div>
      <button className="delete" aria-label={`delete "${task.title}"`} onClick={() => void change(() => api("DELETE", path))}>
        ×
      </button>
    </li>
  );
}
