// Everything after logging in: the header, the Today, List, Board and Focus screens (the tabs),
// search (over the screen while open), and on a phone the tab bar. The lists come from the device's
// copy (works offline); task changes queue up and sync, list and member changes go straight to the
// server and need a connection.
import { useEffect, useState, type ReactNode } from "react";
import { BoardScreen } from "./BoardScreen";
import { Empty } from "./Chrome";
import { FocusScreen } from "./FocusScreen";
import { Header, TabBar } from "./Header";
import { ListScreen } from "./ListScreen";
import { pickList, savedList, saveList } from "./pickList";
import { savedScreen, saveScreen, type Screen } from "./screen";
import { SearchScreen } from "./SearchScreen";
import { StatusLine } from "./StatusLine";
import { TodayScreen } from "./TodayScreen";
import { useLocal } from "./useLocal";
import { keepCounts, pick } from "./timer";
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
  const [searching, setSearching] = useState(false);
  const [found, setFound] = useState<string | null>(null); // a task opened from search, highlighted for a moment

  useEffect(() => {
    if (!found) return;
    const done = window.setTimeout(() => setFound(null), 2500);
    return () => window.clearTimeout(done);
  }, [found]);

  useEffect(() => {
    if (local?.sync.loggedOut) onSessionLost();
  }, [local, onSessionLost]);

  // The timer forgets the tasks that are gone, each time the device's copy changes.
  useEffect(() => {
    if (!local?.stored) return;
    const ids = new Set(applyQueue(local.stored.data, local.queue).lists.flatMap((list) => list.tasks.map((task) => task.id)));
    act((t) => keepCounts(t, ids));
  }, [local, act]);

  function show(next: Screen) {
    setSearching(false);
    setScreen(next);
    saveScreen(next);
    window.scrollTo(0, 0);
  }

  function choose(id: string) {
    setSelected(id);
    saveList(id);
  }

  // From Today the task can be in any list: that list becomes the chosen one, as the Focus screen
  // shows the chosen list's tasks (and the List tab then shows it too).
  function focusOn(taskId: string, listId?: string) {
    if (listId) choose(listId);
    act((t) => pick(t, taskId));
    show("focus");
  }

  function openFound(listId: string, taskId: string) {
    choose(listId);
    show("list");
    setFound(taskId);
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
    if (searching) {
      content = <SearchScreen lists={view.lists} onOpen={openFound} onClose={() => setSearching(false)} />;
    } else if (screen === "today") {
      content = <TodayScreen lists={view.lists} local={local} enqueue={enqueue} onFocus={focusOn} />;
    } else if (screen === "list") {
      content = (
        <ListScreen
          lists={view.lists}
          current={current}
          me={view.me}
          local={local}
          enqueue={enqueue}
          found={found}
          onChoose={choose}
          onFocus={focusOn}
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
      content = <BoardScreen key={current.id} list={current} enqueue={enqueue} onFocus={focusOn} />;
    } else {
      content = <FocusScreen tasks={current.tasks} timer={timer} act={act} />;
    }
  }

  return (
    <>
      <Header username={username} screen={screen} searching={searching} onScreen={show} onSearch={() => setSearching(!searching)} onLogout={onLogout} />
      {notes}
      <main className="content">{content}</main>
      {!wide && <TabBar screen={screen} onScreen={show} />}
    </>
  );
}
