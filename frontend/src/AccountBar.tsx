// Who is logged in, with "Change password" and "Log out".
import { useState } from "react";
import { api } from "./api";
import { ChangePassword } from "./ChangePassword";

export function AccountBar({ username, onLoggedOut }: { username: string; onLoggedOut: () => void }) {
  const [changing, setChanging] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function logout() {
    try {
      await api("POST", "/api/logout");
      onLoggedOut();
    } catch {
      // Only the server can end the session (the cookie is HttpOnly), so don't pretend.
      setError("Logging out needs a connection.");
    }
  }

  return (
    <>
      <div className="account">
        <span>{username}</span>
        <button type="button" className="plain" onClick={() => setChanging(!changing)}>Change password</button>
        <button type="button" className="plain" onClick={logout}>Log out</button>
      </div>
      {error && <p className="error account-error" role="alert">{error}</p>}
      {changing && <ChangePassword onDone={() => setChanging(false)} />}
    </>
  );
}
