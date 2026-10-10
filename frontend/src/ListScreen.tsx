// The List screen: which list (with its settings and a new one), how many things are open, the
// add bar, and the tasks. On a phone the list's links and the sync status move to the bottom.
import { ChevronDown, Plus } from "lucide-react";
import { useRef, useState, type FormEvent } from "react";
import { ApiError, type TaskList } from "./api";
import { Empty } from "./Chrome";
import { ClearDone } from "./ClearDone";
import { sync } from "./device";
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
  onSessionLost: () => void;
};

export function ListScreen({ lists, current, me, local, enqueue, found, onChoose, onSessionLost }: Props) {
  const wide = useWide();
  const [panel, setPanel] = useState<Panel>("none");
  const [error, setError] = useState<string | null>(null);
  const online = local.sync.connection === "online";
  const toggle = (which: Panel) => setPanel(panel === which ? "none" : which);

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
          {wide && links}
        </div>
      )}
      {wide && panels}
      <h1 className="headline">{current ? headline(current.tasks) : "No lists yet."}</h1>
      {current ? (
        <Tasks key={current.id} list={current} enqueue={enqueue} wide={wide} found={found} />
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

// The add bar, the tasks, then "Clear done". The device picks a new task's id.
function Tasks({ list, enqueue, wide, found }: { list: TaskList; enqueue: Enqueue; wide: boolean; found: string | null }) {
  const [title, setTitle] = useState("");
  const titleInput = useRef<HTMLInputElement>(null);

  async function add(event: FormEvent) {
    event.preventDefault();
    const trimmed = title.trim();
    if (!trimmed) return;
    await enqueue({ method: "POST", path: "/api/tasks", body: { id: crypto.randomUUID(), list_id: list.id, title: trimmed } });
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
          placeholder="What needs doing?"
        />
        <button type="submit" className="primary add" aria-label={wide ? undefined : "Add"}>
          <Plus size={wide ? 18 : 20} strokeWidth={2.5} aria-hidden="true" />
          {wide && "Add"}
        </button>
      </form>
      {list.tasks.length > 0 ? (
        <>
          <ul className="tasks">
            {list.tasks.map((task) => <TaskItem key={task.id} task={task} enqueue={enqueue} found={task.id === found} />)}
          </ul>
          <ClearDone list={list} enqueue={enqueue} />
        </>
      ) : (
        <Empty>Nothing to do. Add something above.</Empty>
      )}
    </>
  );
}
