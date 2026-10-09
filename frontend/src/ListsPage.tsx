// Everything after logging in: the header, the List, Board and Focus screens (the tabs), and on a
// phone the tab bar. The lists come from the device's copy (works offline); task changes queue up
// and sync, list and member changes go straight to the server and need a connection.
import { useEffect, useState, type ReactNode } from "react";
import { BoardScreen } from "./BoardScreen";
import { Empty } from "./Chrome";
import { FocusScreen } from "./FocusScreen";
import { Header, TabBar } from "./Header";
import { ListScreen } from "./ListScreen";
import { pickList, savedList, saveList } from "./pickList";
import { savedScreen, saveScreen, type Screen } from "./screen";
import { StatusLine } from "./StatusLine";
import { useLocal } from "./useLocal";
import { useTimer } from "./useTimer";
import { useWide } from "./useWide";
import { applyQueue } from "./view";

type Props = { username: string; notes: ReactNode; onLogout: () => void; onSessionLost: () => void };

export function ListsPage({ username, notes, onLogout, onSessionLost }: Props) {
  const wide = useWide();
  const { local, enqueue } = useLocal();
  const [selected, setSelected] = useState<string | null>(savedList);
  const [screen, setScreen] = useState<Screen>(savedScreen);
  const [timer, act] = useTimer();

  useEffect(() => {
    if (local?.sync.loggedOut) onSessionLost();
  }, [local, onSessionLost]);

  function show(next: Screen) {
    setScreen(next);
    saveScreen(next);
    window.scrollTo(0, 0);
  }

  function choose(id: string) {
    setSelected(id);
    saveList(id);
  }

  let content: ReactNode = null;
  if (local && !local.stored) {
    // The first download hasn't arrived yet: the status line says why.
    content = (
      <div className="screen list-screen">
        <StatusLine local={local} />
      </div>
    );
  } else if (local?.stored) {
    const view = applyQueue(local.stored.data, local.queue);
    const current = view.lists.find((list) => list.id === pickList(view.lists, selected));
    if (screen === "list") {
      content = (
        <ListScreen
          lists={view.lists}
          current={current}
          me={view.me}
          local={local}
          enqueue={enqueue}
          onChoose={choose}
          onSessionLost={onSessionLost}
        />
      );
    } else if (!current) {
      content = (
        <div className="screen list-screen">
          <Empty>No lists yet. Make one on the List screen.</Empty>
        </div>
      );
    } else if (screen === "board") {
      content = <BoardScreen key={current.id} list={current} enqueue={enqueue} />;
    } else {
      content = <FocusScreen tasks={current.tasks} timer={timer} act={act} />;
    }
  }

  return (
    <>
      <Header username={username} screen={screen} onScreen={show} onLogout={onLogout} />
      {notes}
      <main className="content">{content}</main>
      {!wide && <TabBar screen={screen} onScreen={show} />}
    </>
  );
}
