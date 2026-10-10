// "Clear done": deletes the list's finished tasks, for everyone on it, after an inline
// confirmation. Each delete goes into the queue like the × on a task, so it works offline.
// On the List screen under the tasks, on the Board at the foot of the Done column.
import { useState } from "react";
import type { TaskList } from "./api";
import type { Enqueue } from "./useLocal";
import { clearDoneChanges } from "./view";

export function ClearDone({ list, enqueue }: { list: TaskList; enqueue: Enqueue }) {
  const [confirming, setConfirming] = useState(false);
  const changes = clearDoneChanges(list);
  if (changes.length === 0) return null;

  async function clear() {
    setConfirming(false);
    for (const change of changes) await enqueue(change);
  }

  const tasks = changes.length === 1 ? "the done task" : `${changes.length} done tasks`;
  const everyone = list.members.length > 1 ? " for everyone on this list" : "";
  return confirming ? (
    <div className="row confirm clear-done">
      <span>Delete {tasks}{everyone}?</span>
      <button type="button" className="primary" onClick={() => void clear()}>Delete</button>
      <button type="button" className="text" onClick={() => setConfirming(false)}>Cancel</button>
    </div>
  ) : (
    <button type="button" className="text clear-done" onClick={() => setConfirming(true)}>
      Clear done ({changes.length})
    </button>
  );
}
