// Search, opened from the header's magnifier: a field, then the matching tasks of every list,
// grouped by list. A result opens its list on the List screen at that task. × or Escape closes.
import { X } from "lucide-react";
import { useState, type KeyboardEvent } from "react";
import type { TaskList } from "./api";
import { Empty } from "./Chrome";
import { searchTasks } from "./search";
import { stage } from "./stages";

type Props = { lists: TaskList[]; onOpen: (listId: string, taskId: string) => void; onClose: () => void };

export function SearchScreen({ lists, onOpen, onClose }: Props) {
  const [query, setQuery] = useState("");
  const found = searchTasks(lists, query);

  function onKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (event.key === "Escape") onClose();
  }

  return (
    <div className="screen list-screen search-screen">
      <h1 className="visually-hidden">Search</h1>
      <div className="add-bar search-bar">
        <input
          type="search"
          aria-label="search tasks in every list"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={onKeyDown}
          placeholder="Search every list"
          autoComplete="off"
          autoFocus
        />
        <button type="button" className="delete" aria-label="Close search" onClick={onClose}>
          <X size={18} aria-hidden="true" />
        </button>
      </div>
      {query.trim() && found.length === 0 && <Empty>No task matches “{query.trim()}”.</Empty>}
      {found.map(({ list, tasks }) => (
        <section key={list.id} className="found-group" aria-label={list.name}>
          <h2 className="found-list">
            {list.name}
            <span className="count">{tasks.length}</span>
          </h2>
          <ul className="tasks">
            {tasks.map((task) => (
              <li key={task.id}>
                <button type="button" className={["task found-task", task.status === "done" && "done"].filter(Boolean).join(" ")} onClick={() => onOpen(list.id, task.id)}>
                  <span className="title">{task.title}</span>
                  <span className={`chip chip-${task.status}`}>{stage(task.status).label}</span>
                </button>
              </li>
            ))}
          </ul>
        </section>
      ))}
    </div>
  );
}
