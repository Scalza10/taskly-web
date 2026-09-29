// One list's tasks: add a task (the device picks its id), then the tasks themselves.
import { useRef, useState, type FormEvent } from "react";
import { api, type TaskList } from "./api";
import type { Change } from "./ListsPage";
import { TaskItem } from "./TaskItem";

export function Tasks({ list, change }: { list: TaskList; change: Change }) {
  const [title, setTitle] = useState("");
  const titleInput = useRef<HTMLInputElement>(null);

  async function add(event: FormEvent) {
    event.preventDefault();
    const trimmed = title.trim();
    if (!trimmed) return;
    await change(() => api("POST", "/api/tasks", { id: crypto.randomUUID(), list_id: list.id, title: trimmed }));
    setTitle("");
    titleInput.current?.focus();
  }

  return (
    <>
      <form onSubmit={add} autoComplete="off">
        <input ref={titleInput} name="title" value={title} onChange={(e) => setTitle(e.target.value)} maxLength={500} placeholder="What needs doing?" required />
        <button type="submit">Add</button>
      </form>
      <ul>
        {list.tasks.map((task) => <TaskItem key={task.id} task={task} change={change} />)}
      </ul>
      {list.tasks.length === 0 && <p className="empty">Nothing to do. Add something above.</p>}
    </>
  );
}
