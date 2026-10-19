// The Today screen: from every list, what's overdue, what's due today (timed ones in time order)
// and what's in progress, then what was finished today, crossed out until midnight (today.ts). The
// rows are the List screen's, with their list's name, all in one list so a row that changes section
// (a time passes, someone starts it) keeps an open editor. The add bar adds a task due today to the
// list picked next to it (remembered on this device; no picker with only one list).
import { ChevronDown, Plus } from "lucide-react";
import { useRef, useState, type FormEvent } from "react";
import type { TaskList } from "./api";
import { Empty } from "./Chrome";
import { localDay } from "./due";
import { pickList, savedList, savedTodayList, saveTodayList } from "./pickList";
import { todayHeadline } from "./stages";
import { StatusLine } from "./StatusLine";
import { TaskItem } from "./TaskItem";
import { todayView, type Today } from "./today";
import type { Enqueue, Local } from "./useLocal";
import { useWide } from "./useWide";

type Props = { lists: TaskList[]; local: Local; enqueue: Enqueue; onFocus: (taskId: string, listId: string) => void };

const SECTIONS: [keyof Today, string][] = [["overdue", "Overdue"], ["today", "Today"], ["progress", "In progress"], ["done", "Done today"]];

export function TodayScreen({ lists, local, enqueue, onFocus }: Props) {
  const wide = useWide();
  const [picked, setPicked] = useState(savedTodayList);
  const [title, setTitle] = useState("");
  const titleInput = useRef<HTMLInputElement>(null);
  // Worked out on every draw (each sync redraws, at least every 30 s), as on the List screen.
  const now = new Date();
  const view = todayView(lists, now);
  const open = view.overdue.length + view.today.length + view.progress.length;
  const target = pickList(lists, picked, savedList());
  const sections = SECTIONS.filter(([key]) => view[key].length > 0);

  function pick(id: string) {
    setPicked(id);
    saveTodayList(id);
  }

  async function add(event: FormEvent) {
    event.preventDefault();
    const trimmed = title.trim();
    if (!trimmed || !target) return;
    await enqueue({ method: "POST", path: "/api/tasks", body: { id: crypto.randomUUID(), list_id: target, title: trimmed, due_date: localDay(now) } });
    setTitle("");
    titleInput.current?.focus();
  }

  const status = <StatusLine local={local} />;
  if (lists.length === 0) {
    return (
      <div className="screen list-screen today-screen">
        <h1 className="headline">No lists yet.</h1>
        <Empty>Make one on the List screen.</Empty>
        {wide ? status : <div className="list-footer">{status}</div>}
      </div>
    );
  }

  return (
    <div className="screen list-screen today-screen">
      <h1 className="headline">{todayHeadline(open)}</h1>
      <form className="add-form" onSubmit={add} autoComplete="off">
        <div className="add-bar">
          <input ref={titleInput} name="title" aria-label="new task, due today" value={title} onChange={(e) => setTitle(e.target.value)}
            maxLength={500} placeholder="What's for today?" />
          {lists.length > 1 && target && (
            <label className="select">
              <select aria-label="add to list" value={target} onChange={(e) => pick(e.target.value)}>
                {lists.map((list) => <option key={list.id} value={list.id}>{list.name}</option>)}
              </select>
              <ChevronDown size={14} strokeWidth={2.5} aria-hidden="true" />
            </label>
          )}
          <button type="submit" className="primary add" aria-label={wide ? undefined : "Add"}>
            <Plus size={wide ? 18 : 20} strokeWidth={2.5} aria-hidden="true" />
            {wide && "Add"}
          </button>
        </div>
      </form>
      {sections.length > 0 ? (
        <ul className="tasks">
          {sections.flatMap(([key, label]) => [
            <li key={`section-${key}`} className="today-heading">
              <h2 className="found-list">
                {label}
                <span className="count">{view[key].length}</span>
              </h2>
            </li>,
            ...view[key].map(({ task, list }) => (
              <TaskItem key={task.id} task={task} listName={list.name} now={now} enqueue={enqueue} onFocus={(id) => onFocus(id, list.id)} />
            )),
          ])}
        </ul>
      ) : (
        <Empty>Nothing due today. What's overdue, due today or in progress in any list shows here.</Empty>
      )}
      {wide ? status : <div className="list-footer">{status}</div>}
    </div>
  );
}
