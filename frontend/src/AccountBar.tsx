// Who is logged in, with "Change password" and "Log out" (the logout itself lives in App,
// so it survives the switch to the login screen when the session has expired).
import { useState } from "react";
import { ChangePassword } from "./ChangePassword";

export function AccountBar({ username, onLogout }: { username: string; onLogout: () => void }) {
  const [changing, setChanging] = useState(false);

  return (
    <>
      <div className="account">
        <span>{username}</span>
        <button type="button" className="plain" onClick={() => setChanging(!changing)}>Change password</button>
        <button type="button" className="plain" onClick={onLogout}>Log out</button>
      </div>
      {changing && <ChangePassword onDone={() => setChanging(false)} />}
    </>
  );
}
