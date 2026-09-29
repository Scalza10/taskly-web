import { useState, type FormEvent } from "react";
import { api, type TaskList } from "./api";
import type { Change } from "./ListsPage";

export function NewList({ change, onCreated, onCancel }: { change: Change; onCreated: (id: string) => void; onCancel: () => void }) {
  const [name, setName] = useState("");

  async function submit(event: FormEvent) {
    event.preventDefault();
    const trimmed = name.trim();
    if (!trimmed) return;
    const created = await change(() => api<TaskList>("POST", "/api/lists", { name: trimmed }));
    if (created) onCreated(created.id);
  }

  return (
    <form className="panel row" onSubmit={submit} autoComplete="off">
      <input aria-label="new list name" placeholder="List name" value={name} onChange={(e) => setName(e.target.value)} maxLength={100} required autoFocus />
      <button type="submit">Create</button>
      <button type="button" className="plain" onClick={onCancel}>Cancel</button>
    </form>
  );
}
