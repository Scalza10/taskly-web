// Which screen: the lists (from the device's copy if there is one, so it opens offline),
// the login screen, or "connect once" for a first visit without a connection.
// Logging out is handled here, above every screen: an expired session switches to the login
// screen mid-logout, and the device must still be cleared.
import { useCallback, useEffect, useState } from "react";
import { api, type Me } from "./api";
import { AccountBar } from "./AccountBar";
import { forgetDevice, store, sync } from "./device";
import { ListsPage } from "./ListsPage";
import { Login } from "./Login";
import { isLoggedOut } from "./messages";
import { prepareForUser } from "./store";

type Screen = { kind: "checking" } | { kind: "login" } | { kind: "connect" } | { kind: "blocked" } | { kind: "lists"; me: string };

export function App() {
  const [screen, setScreen] = useState<Screen>({ kind: "checking" });
  const [unsynced, setUnsynced] = useState(0);
  const [logoutError, setLogoutError] = useState<string | null>(null);

  const start = useCallback(async () => {
    let stored;
    try {
      stored = await store.snapshot();
    } catch {
      return setScreen({ kind: "blocked" });
    }
    if (stored) return setScreen({ kind: "lists", me: stored.data.me });
    try {
      const me = await api<Me>("GET", "/api/me");
      await prepareForUser(store, me.username);
      setScreen({ kind: "lists", me: me.username });
    } catch (e) {
      setScreen(isLoggedOut(e) ? { kind: "login" } : { kind: "connect" });
    }
  }, []);

  useEffect(() => {
    void start();
  }, [start]);

  // An installed phone app has no reload button: retry when the network returns.
  const connecting = screen.kind === "connect";
  useEffect(() => {
    if (!connecting) return;
    const retry = () => void start();
    window.addEventListener("online", retry);
    return () => window.removeEventListener("online", retry);
  }, [connecting, start]);

  // The session ended (expired, password changed elsewhere): log in again, keep unsent changes.
  const sessionLost = useCallback(() => setScreen({ kind: "login" }), []);

  async function logout() {
    setLogoutError(null);
    if ((await store.queue()).length) {
      await sync.request();
      const waiting = (await store.queue()).length;
      if (waiting) return setUnsynced(waiting);
    }
    await logoutAnyway();
  }

  // /api/logout answers 204 even without a session, so this also works after it expired.
  async function logoutAnyway() {
    try {
      await api("POST", "/api/logout");
    } catch {
      setUnsynced(0);
      return setLogoutError("Logging out needs a connection.");
    }
    await forgetDevice();
    location.reload(); // a fresh page: new store, login screen
  }

  async function loggedIn(username: string) {
    setUnsynced(0);
    setLogoutError(null);
    await prepareForUser(store, username); // someone else's unsent changes are deleted, never sent
    sync.resume();
    setScreen({ kind: "lists", me: username });
  }

  const logoutNotes = (
    <>
      {logoutError && <p className="error account-error" role="alert">{logoutError}</p>}
      {unsynced > 0 && (
        <div className="panel row confirm">
          <span>{unsynced === 1 ? "1 change hasn't" : `${unsynced} changes haven't`} synced. Log out anyway?</span>
          <button type="button" className="danger" onClick={logoutAnyway}>Log out</button>
          <button type="button" className="plain" onClick={() => setUnsynced(0)}>Cancel</button>
        </div>
      )}
    </>
  );

  switch (screen.kind) {
    case "checking":
      return null;
    case "blocked":
      return (
        <main>
          <h1>Taskly</h1>
          <p className="error" role="alert">
            This browser won't let Taskly save data on this device, which it needs. Check that site data isn't blocked, or try another browser.
          </p>
        </main>
      );
    case "connect":
      return (
        <main>
          <h1>Taskly</h1>
          <p className="hint">Connect to the internet once to log in.</p>
          <button type="button" onClick={() => void start()}>Try again</button>
        </main>
      );
    case "login":
      return <>{logoutNotes}<Login onLoggedIn={loggedIn} /></>;
    case "lists":
      return (
        <>
          <AccountBar username={screen.me} onLogout={logout} />
          {logoutNotes}
          <ListsPage onSessionLost={sessionLost} />
        </>
      );
  }
}
