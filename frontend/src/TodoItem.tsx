// One todo: tick it, click the title to rename (Enter or leaving the field saves, Escape cancels), × deletes.
import { useRef, useState, type FocusEvent, type KeyboardEvent } from "react";
import { api, type Todo } from "./api";
import type { Change } from "./TodoPage";

export function TodoItem({ todo, change }: { todo: Todo; change: Change }) {
  const [editing, setEditing] = useState(false);
  const cancelled = useRef(false);
  const path = `/api/todos/${todo.id}`;

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
    if (newTitle && newTitle !== todo.title) void change(() => api("PATCH", path, { title: newTitle }));
  }

  return (
    <li className={todo.done ? "done" : undefined}>
      <input
        type="checkbox"
        checked={todo.done}
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
            defaultValue={todo.title}
            maxLength={500}
            autoFocus
            onKeyDown={onKeyDown}
            onBlur={onBlur}
          />
        ) : (
          <span className="title" onClick={() => setEditing(true)}>{todo.title}</span>
        )}
        {(todo.created_by || todo.done_by) && (
          <small className="by">
            {[todo.created_by && `added by ${todo.created_by}`, todo.done_by && `done by ${todo.done_by}`]
              .filter(Boolean)
              .join(" · ")}
          </small>
        )}
      </div>
      <button className="delete" aria-label={`delete "${todo.title}"`} onClick={() => void change(() => api("DELETE", path))}>
        ×
      </button>
    </li>
  );
}
