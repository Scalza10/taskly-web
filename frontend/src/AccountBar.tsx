// Who is logged in, with "Download" (install as an app), "Change password" and "Log out" (the
// logout itself lives in App, so it survives the switch to the login screen when the session has expired).
import { useState } from "react";
import { ChangePassword } from "./ChangePassword";
import { promptInstall, useInstall } from "./install";

export function AccountBar({ username, onLogout }: { username: string; onLogout: () => void }) {
  const [changing, setChanging] = useState(false);
  const [steps, setSteps] = useState(false);
  const install = useInstall();

  function download() {
    if (install === "prompt") promptInstall().catch(() => setSteps(true));
    else setSteps(!steps);
  }

  return (
    <>
      <div className="account">
        <span>{username}</span>
        {install !== "installed" && <button type="button" className="plain" onClick={download}>Download</button>}
        <button type="button" className="plain" onClick={() => setChanging(!changing)}>Change password</button>
        <button type="button" className="plain" onClick={onLogout}>Log out</button>
      </div>
      {steps && install !== "installed" && <InstallSteps onClose={() => setSteps(false)} />}
      {changing && <ChangePassword onDone={() => setChanging(false)} />}
    </>
  );
}

function InstallSteps({ onClose }: { onClose: () => void }) {
  return (
    <div className="panel stack">
      <p className="hint">Install Taskly to open it like an app and use it offline:</p>
      <ul className="steps">
        <li><b>iPhone or iPad (Safari):</b> Share → Add to Home Screen</li>
        <li><b>Android (Chrome):</b> menu → Install app</li>
        <li><b>Computer (Chrome or Edge):</b> the install icon at the end of the address bar</li>
        <li><b>Mac (Safari):</b> File → Add to Dock</li>
      </ul>
      <p className="hint">Already installed? Open Taskly from your home screen or apps.</p>
      <div className="row">
        <button type="button" className="plain" onClick={onClose}>Close</button>
      </div>
    </div>
  );
}
