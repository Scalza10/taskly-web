// What the screen shows: the last snapshot from the server with the unsent changes applied on
// top, sorted as the server sorts. Pure: easy to test, and the same answer every time.
import type { Snapshot, Status, Task, TaskList } from "./api";
import type { QueuedChange, TaskChange } from "./store";

const TASKS = "/api/tasks";

export type Connection = "online" | "offline" | "trouble";

export function applyQueue(snapshot: Snapshot, queue: QueuedChange[]): Snapshot {
  // A snapshot stored by the page before tasks had a status has only done; one from before due dates has none.
  const lists = snapshot.lists.map((list) => ({
    ...list,
    tasks: list.tasks.map((task) => ({ ...task, status: task.status ?? (task.done ? "done" : "new"), due_date: task.due_date ?? null })),
  }));
  const find = (id: string) => {
    for (const list of lists) {
      const index = list.tasks.findIndex((task) => task.id === id);
      if (index >= 0) return { list, index };
    }
    return undefined;
  };

  for (const change of queue) {
    if (change.method === "POST" && change.path === TASKS) {
      const body = change.body as { id: string; list_id: string; title: string; due_date?: string | null };
      const list = lists.find((l) => l.id === body.list_id);
      if (!list || find(body.id)) continue;
      list.tasks.push({
        id: body.id, list_id: body.list_id, title: body.title, status: "new", done: false, due_date: body.due_date ?? null,
        created_by: snapshot.me, done_by: null, created_at: change.queuedAt, updated_at: change.queuedAt, pending: true,
      });
      continue;
    }
    if (!change.path.startsWith(`${TASKS}/`)) continue;
    const found = find(change.path.slice(TASKS.length + 1));
    if (!found) continue;
    if (change.method === "DELETE") {
      found.list.tasks.splice(found.index, 1);
      continue;
    }
    const body = change.body as { title?: string; done?: boolean; status?: Status; due_date?: string | null };
    const task = found.list.tasks[found.index];
    if (body.title !== undefined) task.title = body.title;
    if (body.due_date !== undefined) task.due_date = body.due_date; // null removes it
    const status = nextStatus(task.status, body);
    if (status !== undefined) {
      task.status = status;
      task.done = status === "done";
      task.done_by = task.done ? snapshot.me : null;
    }
    task.pending = true;
  }

  return { ...snapshot, lists: lists.map((list) => ({ ...list, tasks: sortTasks(list.tasks) })) };
}

// As the server applies a PATCH: status wins; done: true finishes; done: false reopens only a
// finished task (one in progress stays in progress). undefined: the status doesn't change.
function nextStatus(current: Status, body: { done?: boolean; status?: Status }): Status | undefined {
  if (body.status !== undefined) return body.status;
  if (body.done === true) return "done";
  if (body.done === false && current === "done") return "new";
  return undefined;
}

// "Clear done": a delete for each of the list's finished tasks.
export function clearDoneChanges(list: TaskList): TaskChange[] {
  return list.tasks.filter((task) => task.status === "done").map((task) => ({ method: "DELETE", path: `${TASKS}/${task.id}` }));
}

// As the server sorts: not done first, then oldest first. Ties keep their order (the server's).
export function sortTasks(tasks: Task[]): Task[] {
  return tasks
    .map((task, index) => ({ task, index }))
    .sort((a, b) =>
      Number(a.task.status === "done") - Number(b.task.status === "done") ||
      a.task.created_at.localeCompare(b.task.created_at) ||
      a.index - b.index)
    .map(({ task }) => task);
}

export function syncedLabel(syncedAt: string | undefined, now: Date): string {
  if (!syncedAt) return "Not synced yet";
  const minutes = Math.floor((now.getTime() - new Date(syncedAt).getTime()) / 60_000);
  if (minutes < 1) return "Synced just now";
  if (minutes < 60) return `Synced ${minutes} min ago`;
  return `Synced at ${new Date(syncedAt).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}`;
}

export function statusText(connection: Connection, waiting: number, syncedAt: string | undefined, now: Date): string {
  const changes = waiting === 1 ? "1 change waiting" : `${waiting} changes waiting`;
  if (connection === "offline") return waiting ? `Offline · ${changes}` : "Offline";
  if (connection === "trouble") return waiting ? `Can't reach the server · ${changes}` : "Can't reach the server";
  if (waiting) return `Syncing · ${changes}`;
  return syncedLabel(syncedAt, now);
}
