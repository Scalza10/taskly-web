// Who is logged in, with "Change password" and "Log out". Logging out needs a connection:
// only the server can end the session. Unsent changes are sent first, or discarded on request.
import { useState } from "react";
import { api } from "./api";
import { ChangePassword } from "./ChangePassword";
import { forgetDevice, store, sync } from "./device";

export function AccountBar({ username }: { username: string }) {
  const [changing, setChanging] = useState(false);
  const [unsynced, setUnsynced] = useState(0);
  const [error, setError] = useState<string | null>(null);

  async function logout() {
    if ((await store.queue()).length) {
      await sync.request();
      const waiting = (await store.queue()).length;
      if (waiting) return setUnsynced(waiting);
    }
    await logoutAnyway();
  }

  async function logoutAnyway() {
    try {
      await api("POST", "/api/logout");
    } catch {
      setUnsynced(0);
      return setError("Logging out needs a connection.");
    }
    await forgetDevice();
    location.reload(); // a fresh page: new store, login screen
  }

  return (
    <>
      <div className="account">
        <span>{username}</span>
        <button type="button" className="plain" onClick={() => setChanging(!changing)}>Change password</button>
        <button type="button" className="plain" onClick={logout}>Log out</button>
      </div>
      {error && <p className="error account-error" role="alert">{error}</p>}
      {unsynced > 0 && (
        <div className="panel row confirm">
          <span>{unsynced === 1 ? "1 change hasn't" : `${unsynced} changes haven't`} synced. Log out anyway?</span>
          <button type="button" className="danger" onClick={logoutAnyway}>Log out</button>
          <button type="button" className="plain" onClick={() => setUnsynced(0)}>Cancel</button>
        </div>
      )}
      {changing && <ChangePassword onDone={() => setChanging(false)} />}
    </>
  );
}
