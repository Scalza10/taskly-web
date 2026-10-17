// The List screen: which list (with its settings and a new one), the "Due today" filter, how many
// things are open, the add bar, and the tasks. On a phone the list's links and the sync status
// move to the bottom.
import { CalendarCheck, ChevronDown, Plus } from "lucide-react";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { ApiError, type TaskList } from "./api";
import { Empty } from "./Chrome";
import { ClearDone } from "./ClearDone";
import { sync } from "./device";
import { dueToday, localDay } from "./due";
import { ListSettings } from "./ListSettings";
import { isLoggedOut } from "./messages";
import { NewList } from "./NewList";
import { headline } from "./stages";
import { StatusLine } from "./StatusLine";
import { TaskItem } from "./TaskItem";
import type { Enqueue, Local } from "./useLocal";
import { useWide } from "./useWide";

export type Change = <T>(request: () => Promise<T>) => Promise<T | undefined>;
type Panel = "none" | "new" | "settings";

type Props = {
  lists: TaskList[];
  current: TaskList | undefined;
  me: string;
  local: Local;
  enqueue: Enqueue;
  found: string | null; // a task opened from search
  onChoose: (id: string) => void;
  onFocus: (taskId: string) => void;
  onSessionLost: () => void;
};

export function ListScreen({ lists, current, me, local, enqueue, found, onChoose, onFocus, onSessionLost }: Props) {
  const wide = useWide();
  const [panel, setPanel] = useState<Panel>("none");
  const [error, setError] = useState<string | null>(null);
  // "Due today": only the open tasks due today or overdue. Off for a task opened from search.
  const [dueOnly, setDueOnly] = useState(false);
  const online = local.sync.connection === "online";
  const toggle = (which: Panel) => setPanel(panel === which ? "none" : which);
  // Worked out on every draw (each sync redraws, at least every 30 s), so it moves on at midnight.
  const today = localDay(new Date());
  const due = current ? dueToday(current.tasks, today) : [];

  useEffect(() => {
    if (found) setDueOnly(false);
  }, [found]);

  async function change<T>(request: () => Promise<T>): Promise<T | undefined> {
    let result: T | undefined;
    try {
      result = await request();
      setError(null);
    } catch (e) {
      if (isLoggedOut(e)) {
        onSessionLost();
        return undefined;
      }
      setError(e instanceof ApiError ? e.message : "That needs a connection.");
    }
    await sync.request();
    return result;
  }

  function choose(id: string) {
    onChoose(id);
    setPanel("none");
  }

  const offline = online ? undefined : "Needs a connection";
  const links = (
    <>
      {current && <button type="button" className="text" disabled={!online} title={offline} onClick={() => toggle("settings")}>Settings</button>}
      <button type="button" className="text" disabled={!online} title={offline} onClick={() => toggle("new")}>New list</button>
    </>
  );

  // On a desktop under the list's links, on a phone above them (they're at the bottom there).
  const panels = (
    <>
      {online && panel === "new" && <NewList change={change} onCreated={choose} onCancel={() => setPanel("none")} />}
      {online && panel === "settings" && current && (
        // Not key={current.id}: the tasks below have that key, and siblings sharing a key leave this panel behind when it closes.
        <ListSettings key={`settings-${current.id}`} list={current} me={me} change={change} onClose={() => setPanel("none")} />
      )}
      {error && <p className="error" role="alert">{error}</p>}
    </>
  );

  return (
    <div className="screen list-screen">
      {(current || wide) && (
        <div className="toolbar">
          {current && (
            <label className="select">
              <select aria-label="list" value={current.id} onChange={(e) => choose(e.target.value)}>
                {lists.map((list) => <option key={list.id} value={list.id}>{list.name}</option>)}
              </select>
              <ChevronDown size={wide ? 16 : 14} strokeWidth={2.5} aria-hidden="true" />
            </label>
          )}
          {current && (due.length > 0 || dueOnly) && (
            <button type="button" className="filter" aria-pressed={dueOnly} onClick={() => setDueOnly(!dueOnly)}>
              <CalendarCheck size={wide ? 16 : 14} strokeWidth={2.5} aria-hidden="true" />
              Due today
              <span className="count">{due.length}</span>
            </button>
          )}
          {wide && links}
        </div>
      )}
      {wide && panels}
      <h1 className="headline">{current ? headline(dueOnly ? due : current.tasks) : "No lists yet."}</h1>
      {current ? (
        <Tasks key={current.id} list={current} shown={dueOnly ? due : current.tasks} dueOnly={dueOnly} today={today}
          enqueue={enqueue} wide={wide} found={found} onFocus={onFocus} />
      ) : (
        <Empty>Make one with “New list”.</Empty>
      )}
      {!wide && panels}
      {wide ? (
        <StatusLine local={local} />
      ) : (
        <div className="list-footer">
          <div className="links">{links}</div>
          <StatusLine local={local} />
        </div>
      )}
    </div>
  );
}

// The add bar, the tasks shown, then "Clear done". The device picks a new task's id. While only the
// tasks due today show, a task added is due today too, so it doesn't vanish as it's added.
type TasksProps = {
  list: TaskList; shown: TaskList["tasks"]; dueOnly: boolean; today: string;
  enqueue: Enqueue; wide: boolean; found: string | null; onFocus: (taskId: string) => void;
};

function Tasks({ list, shown, dueOnly, today, enqueue, wide, found, onFocus }: TasksProps) {
  const [title, setTitle] = useState("");
  const titleInput = useRef<HTMLInputElement>(null);

  async function add(event: FormEvent) {
    event.preventDefault();
    const trimmed = title.trim();
    if (!trimmed) return;
    const body = { id: crypto.randomUUID(), list_id: list.id, title: trimmed, ...(dueOnly && { due_date: today }) };
    await enqueue({ method: "POST", path: "/api/tasks", body });
    setTitle("");
    titleInput.current?.focus();
  }

  return (
    <>
      <form className="add-bar" onSubmit={add} autoComplete="off">
        <input
          ref={titleInput}
          name="title"
          aria-label="new task"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          maxLength={500}
          placeholder={dueOnly ? "What needs doing today?" : "What needs doing?"}
        />
        <button type="submit" className="primary add" aria-label={wide ? undefined : "Add"}>
          <Plus size={wide ? 18 : 20} strokeWidth={2.5} aria-hidden="true" />
          {wide && "Add"}
        </button>
      </form>
      {shown.length > 0 ? (
        <>
          <ul className="tasks">
            {shown.map((task) => <TaskItem key={task.id} task={task} today={today} enqueue={enqueue} onFocus={onFocus} found={task.id === found} />)}
          </ul>
          {!dueOnly && <ClearDone list={list} enqueue={enqueue} />}
        </>
      ) : (
        <Empty>{dueOnly ? "Nothing due today." : "Nothing to do. Add something above."}</Empty>
      )}
    </>
  );
}
