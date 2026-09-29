// Owners rename, add and remove people, and delete. Members see who's in and can leave.
import { useState, type FormEvent } from "react";
import { api, type ListInfo, type TaskList } from "./api";
import type { Change } from "./ListsPage";

type Props = { list: TaskList; me: string; change: Change; onClose: () => void };

export function ListSettings({ list, me, change, onClose }: Props) {
  const [name, setName] = useState(list.name);
  const [newMember, setNewMember] = useState("");
  const [confirming, setConfirming] = useState(false);
  const owner = list.role === "owner";
  const base = `/api/lists/${list.id}`;
  const member = (username: string) => `${base}/members/${encodeURIComponent(username)}`;

  function rename(event: FormEvent) {
    event.preventDefault();
    const trimmed = name.trim();
    if (trimmed && trimmed !== list.name) void change(() => api<ListInfo>("PATCH", base, { name: trimmed }));
  }

  async function add(event: FormEvent) {
    event.preventDefault();
    const username = newMember.trim();
    if (!username) return;
    if ((await change(() => api<ListInfo>("POST", `${base}/members`, { username }))) !== undefined) setNewMember("");
  }

  async function deleteOrLeave() {
    const done = await change(() => api("DELETE", owner ? base : member(me)));
    if (done !== undefined) onClose();
  }

  return (
    <section className="panel stack">
      {owner ? (
        <form className="row" onSubmit={rename}>
          <input aria-label="list name" value={name} onChange={(e) => setName(e.target.value)} maxLength={100} required />
          <button type="submit">Rename</button>
        </form>
      ) : (
        <p className="hint">{list.owner ? `${list.owner} owns this list.` : "Nobody owns this list."}</p>
      )}

      <div>
        <h2>People</h2>
        <ul className="members">
          {list.members.map((username) => (
            <li key={username}>
              <span>{username}{username === list.owner && " (owner)"}</span>
              {owner && username !== list.owner && (
                <button type="button" className="delete" aria-label={`remove ${username}`} onClick={() => void change(() => api("DELETE", member(username)))}>
                  ×
                </button>
              )}
            </li>
          ))}
        </ul>
        {owner && (
          <form className="row" onSubmit={add} autoComplete="off">
            <input aria-label="username to add" placeholder="Username" value={newMember} onChange={(e) => setNewMember(e.target.value)} autoCapitalize="none" />
            <button type="submit">Add</button>
          </form>
        )}
      </div>

      {confirming ? (
        <div className="row confirm">
          <span>{owner ? `Delete “${list.name}” and its ${list.tasks.length} ${list.tasks.length === 1 ? "task" : "tasks"}?` : `Leave “${list.name}”?`}</span>
          <button type="button" className="danger" onClick={deleteOrLeave}>{owner ? "Delete" : "Leave"}</button>
          <button type="button" className="plain" onClick={() => setConfirming(false)}>Cancel</button>
        </div>
      ) : (
        <div className="row">
          <button type="button" className="plain danger-text" onClick={() => setConfirming(true)}>
            {owner ? "Delete list" : "Leave list"}
          </button>
          <button type="button" className="plain" onClick={onClose}>Close</button>
        </div>
      )}
    </section>
  );
}
