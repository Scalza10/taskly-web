// The lists: reads everything from /api/sync, and after every change reads it again,
// so the page always shows what the server has.
import { useEffect, useState } from "react";
import { api, type Snapshot } from "./api";
import { ListPicker } from "./ListPicker";
import { ListSettings } from "./ListSettings";
import { isLoggedOut } from "./messages";
import { NewList } from "./NewList";
import { pickList, savedList, saveList } from "./pickList";
import { Tasks } from "./Tasks";

export type Change = <T>(request: () => Promise<T>) => Promise<T | undefined>;
type Panel = "none" | "new" | "settings";

export function ListsPage({ onLoggedOut }: { onLoggedOut: () => void }) {
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const [selected, setSelected] = useState<string | null>(savedList);
  const [panel, setPanel] = useState<Panel>("none");
  const [error, setError] = useState<string | null>(null);

  function fail(e: unknown) {
    if (isLoggedOut(e)) onLoggedOut();
    else setError((e as Error).message);
  }

  async function refresh() {
    try {
      setSnapshot(await api<Snapshot>("GET", "/api/sync"));
    } catch (e) {
      fail(e);
    }
  }

  async function change<T>(request: () => Promise<T>): Promise<T | undefined> {
    let result: T | undefined;
    try {
      result = await request();
      setError(null);
    } catch (e) {
      fail(e);
    }
    await refresh();
    return result;
  }

  useEffect(() => {
    void refresh();
  }, []);

  function choose(id: string) {
    setSelected(id);
    saveList(id);
    setPanel("none");
  }

  if (!snapshot) return <main>{error && <p className="error" role="alert">{error}</p>}</main>;

  const current = snapshot.lists.find((list) => list.id === pickList(snapshot.lists, selected));
  const toggle = (which: Panel) => setPanel(panel === which ? "none" : which);

  return (
    <main>
      <ListPicker
        lists={snapshot.lists}
        current={current}
        onChoose={choose}
        onNew={() => toggle("new")}
        onSettings={() => toggle("settings")}
      />
      {panel === "new" && <NewList change={change} onCreated={choose} onCancel={() => setPanel("none")} />}
      {panel === "settings" && current && (
        <ListSettings list={current} me={snapshot.me} change={change} onClose={() => setPanel("none")} />
      )}
      {error && <p className="error" role="alert">{error}</p>}
      {current ? (
        <Tasks key={current.id} list={current} change={change} />
      ) : (
        <p className="empty">No lists yet. Make one with “New list”.</p>
      )}
    </main>
  );
}
