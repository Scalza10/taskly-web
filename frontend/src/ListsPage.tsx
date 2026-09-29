// The lists, from the device's copy (works offline). Task changes queue up and sync;
// list and member changes go straight to the server and need a connection.
import { useEffect, useState } from "react";
import { ApiError } from "./api";
import { sync } from "./device";
import { ListPicker } from "./ListPicker";
import { ListSettings } from "./ListSettings";
import { isLoggedOut } from "./messages";
import { NewList } from "./NewList";
import { pickList, savedList, saveList } from "./pickList";
import { StatusLine } from "./StatusLine";
import { Tasks } from "./Tasks";
import { useLocal } from "./useLocal";
import { applyQueue } from "./view";

export type Change = <T>(request: () => Promise<T>) => Promise<T | undefined>;
type Panel = "none" | "new" | "settings";

export function ListsPage({ onSessionLost }: { onSessionLost: () => void }) {
  const { local, enqueue } = useLocal();
  const [selected, setSelected] = useState<string | null>(savedList);
  const [panel, setPanel] = useState<Panel>("none");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (local?.sync.loggedOut) onSessionLost();
  }, [local, onSessionLost]);

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
    setSelected(id);
    saveList(id);
    setPanel("none");
  }

  if (!local) return null;
  if (!local.stored) {
    return (
      <main>
        <h1>Taskly</h1>
        <StatusLine local={local} />
      </main>
    );
  }

  const view = applyQueue(local.stored.data, local.queue);
  const current = view.lists.find((list) => list.id === pickList(view.lists, selected));
  const online = local.sync.connection === "online";
  const toggle = (which: Panel) => setPanel(panel === which ? "none" : which);

  return (
    <main>
      <ListPicker
        lists={view.lists}
        current={current}
        online={online}
        onChoose={choose}
        onNew={() => toggle("new")}
        onSettings={() => toggle("settings")}
      />
      {online && panel === "new" && <NewList change={change} onCreated={choose} onCancel={() => setPanel("none")} />}
      {online && panel === "settings" && current && (
        <ListSettings key={current.id} list={current} me={view.me} change={change} onClose={() => setPanel("none")} />
      )}
      {error && <p className="error" role="alert">{error}</p>}
      {current ? (
        <Tasks key={current.id} list={current} enqueue={enqueue} />
      ) : (
        <p className="empty">No lists yet. Make one with “New list”.</p>
      )}
      <StatusLine local={local} />
    </main>
  );
}
