// Which screen: the lists (from the device's copy if there is one, so it opens offline),
// the login screen, or "connect once" for a first visit without a connection.
import { useCallback, useEffect, useState } from "react";
import { api, type Me } from "./api";
import { AccountBar } from "./AccountBar";
import { store, sync } from "./device";
import { ListsPage } from "./ListsPage";
import { Login } from "./Login";
import { isLoggedOut } from "./messages";
import { prepareForUser } from "./store";

type Screen = { kind: "checking" } | { kind: "login" } | { kind: "connect" } | { kind: "lists"; me: string };

export function App() {
  const [screen, setScreen] = useState<Screen>({ kind: "checking" });

  useEffect(() => {
    void (async () => {
      const stored = await store.snapshot();
      if (stored) return setScreen({ kind: "lists", me: stored.data.me });
      try {
        const me = await api<Me>("GET", "/api/me");
        await prepareForUser(store, me.username);
        setScreen({ kind: "lists", me: me.username });
      } catch (e) {
        setScreen(isLoggedOut(e) ? { kind: "login" } : { kind: "connect" });
      }
    })();
  }, []);

  // The session ended (expired, password changed elsewhere): log in again, keep unsent changes.
  const sessionLost = useCallback(() => setScreen({ kind: "login" }), []);

  async function loggedIn(username: string) {
    await prepareForUser(store, username); // someone else's unsent changes are deleted, never sent
    sync.resume();
    setScreen({ kind: "lists", me: username });
  }

  switch (screen.kind) {
    case "checking":
      return null;
    case "connect":
      return <main><h1>Taskly</h1><p className="hint">Connect to the internet once to log in.</p></main>;
    case "login":
      return <Login onLoggedIn={loggedIn} />;
    case "lists":
      return (
        <>
          <AccountBar username={screen.me} />
          <ListsPage onSessionLost={sessionLost} />
        </>
      );
  }
}
