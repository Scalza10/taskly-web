import { useState, type FormEvent } from "react";
import { api, type ListInfo } from "./api";
import type { Change } from "./ListScreen";

export function NewList({ change, onCreated, onCancel }: { change: Change; onCreated: (id: string) => void; onCancel: () => void }) {
  const [name, setName] = useState("");

  async function submit(event: FormEvent) {
    event.preventDefault();
    const trimmed = name.trim();
    if (!trimmed) return;
    const created = await change(() => api<ListInfo>("POST", "/api/lists", { name: trimmed }));
    if (created) onCreated(created.id);
  }

  return (
    <form className="card panel row" onSubmit={submit} autoComplete="off">
      <input aria-label="new list name" placeholder="List name" value={name} onChange={(e) => setName(e.target.value)} maxLength={100} required autoFocus />
      <button type="submit" className="primary">Create</button>
      <button type="button" className="text" onClick={onCancel}>Cancel</button>
    </form>
  );
}
