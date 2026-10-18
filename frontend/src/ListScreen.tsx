// The List screen: which list (with its settings and a new one), the "Due today" filter, how many
// things are open, the add bar, and the tasks. On a phone the list's links and the sync status
// move to the bottom.
import { CalendarCheck, ChevronDown, NotebookPen, Plus } from "lucide-react";
import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from "react";
import { ApiError, type TaskList } from "./api";
import { Empty } from "./Chrome";
import { ClearDone } from "./ClearDone";
import { sync } from "./device";
import { dueToday, localDay } from "./due";
import { ListSettings } from "./ListSettings";
import { isLoggedOut } from "./messages";
import { NewList } from "./NewList";
import { NOTES_MAX } from "./notes";
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
  // Worked out on every draw (each sync redraws, at least every 30 s), so it moves on at midnight
  // and a time turns overdue when it passes.
  const now = new Date();
  const due = current ? dueToday(current.tasks, now) : [];

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
        <Tasks key={current.id} list={current} shown={dueOnly ? due : current.tasks} dueOnly={dueOnly} now={now}
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
// tasks due today show, a task added is due today too, so it doesn't vanish as it's added. The
// notes button opens a field for the new task's notes under the bar (Ctrl+Enter there adds too).
type TasksProps = {
  list: TaskList; shown: TaskList["tasks"]; dueOnly: boolean; now: Date;
  enqueue: Enqueue; wide: boolean; found: string | null; onFocus: (taskId: string) => void;
};

function Tasks({ list, shown, dueOnly, now, enqueue, wide, found, onFocus }: TasksProps) {
  const [title, setTitle] = useState("");
  const [withNotes, setWithNotes] = useState(false);
  const [notes, setNotes] = useState("");
  const titleInput = useRef<HTMLInputElement>(null);

  async function add(event: FormEvent) {
    event.preventDefault();
    const trimmed = title.trim();
    if (!trimmed) return;
    const note = withNotes ? notes.trim() : "";
    const body = { id: crypto.randomUUID(), list_id: list.id, title: trimmed, ...(dueOnly && { due_date: localDay(now) }), ...(note ? { notes: note } : {}) };
    await enqueue({ method: "POST", path: "/api/tasks", body });
    setTitle("");
    setNotes("");
    setWithNotes(false);
    titleInput.current?.focus();
  }

  function onNotesKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) {
      event.preventDefault();
      event.currentTarget.form?.requestSubmit();
    }
  }

  return (
    <>
      <form className="add-form" onSubmit={add} autoComplete="off">
        <div className="add-bar">
          <input
            ref={titleInput}
            name="title"
            aria-label="new task"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            maxLength={500}
            placeholder={dueOnly ? "What needs doing today?" : "What needs doing?"}
          />
          <button type="button" className="add-notes-toggle" aria-pressed={withNotes} aria-label="notes for the new task" title="Add notes"
            onClick={() => setWithNotes(!withNotes)}>
            <NotebookPen aria-hidden="true" />
          </button>
          <button type="submit" className="primary add" aria-label={wide ? undefined : "Add"}>
            <Plus size={wide ? 18 : 20} strokeWidth={2.5} aria-hidden="true" />
            {wide && "Add"}
          </button>
        </div>
        {withNotes && (
          <textarea
            className="add-notes"
            aria-label="notes"
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            onKeyDown={onNotesKeyDown}
            maxLength={NOTES_MAX}
            rows={3}
            placeholder="Notes: links, details…"
            autoFocus
          />
        )}
      </form>
      {shown.length > 0 ? (
        <>
          <ul className="tasks">
            {shown.map((task) => <TaskItem key={task.id} task={task} now={now} enqueue={enqueue} onFocus={onFocus} found={task.id === found} />)}
          </ul>
          {!dueOnly && <ClearDone list={list} enqueue={enqueue} />}
        </>
      ) : (
        <Empty>{dueOnly ? "Nothing due today." : "Nothing to do. Add something above."}</Empty>
      )}
    </>
  );
}
