// Who is logged in, the light/dark button, and a menu (the burger button) with "Sync" (send waiting changes and download
// the latest now; the result shows in the status line), "Download" (install as an app), "Change
// password" and "Log out" (the logout itself lives in App, so it survives the switch to the login
// screen when the session has expired). One button keeps the header on one line on any phone.
import { useEffect, useRef, useState } from "react";
import { ChangePassword } from "./ChangePassword";
import { sync } from "./device";
import { promptInstall, useInstall } from "./install";
import { currentTheme, setTheme, systemDark, type Theme } from "./theme";

export function AccountBar({ username, onLogout }: { username: string; onLogout: () => void }) {
  const [open, setOpen] = useState(false);
  const [changing, setChanging] = useState(false);
  const [steps, setSteps] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const install = useInstall();
  const menu = useRef<HTMLDivElement>(null);
  const toggleButton = useRef<HTMLButtonElement>(null);

  // A tap outside the menu or Escape closes it.
  useEffect(() => {
    if (!open) return;
    const outside = (event: PointerEvent) => {
      if (!menu.current?.contains(event.target as Node)) setOpen(false);
    };
    const escape = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      setOpen(false);
      toggleButton.current?.focus();
    };
    document.addEventListener("pointerdown", outside);
    document.addEventListener("keydown", escape);
    return () => {
      document.removeEventListener("pointerdown", outside);
      document.removeEventListener("keydown", escape);
    };
  }, [open]);

  // Every item closes the menu first.
  const pick = (action: () => void) => () => {
    setOpen(false);
    action();
  };

  async function syncNow() {
    setSyncing(true);
    await sync.request(); // always resolves
    setSyncing(false);
  }

  function download() {
    if (install === "prompt") promptInstall().catch(() => setSteps(true));
    else setSteps(!steps);
  }

  return (
    <>
      <div className="account">
        <span>{username}</span>
        <ThemeButton />
        <div className="menu" ref={menu}>
          <button
            type="button"
            className="plain burger"
            ref={toggleButton}
            aria-label="Menu"
            aria-expanded={open}
            aria-controls="account-menu"
            onClick={() => setOpen(!open)}
          >
            <svg viewBox="0 0 20 20" width="20" height="20" aria-hidden="true" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
              <path d="M3 5h14M3 10h14M3 15h14" />
            </svg>
          </button>
          {open && (
            <div className="menu-items" id="account-menu">
              <button type="button" className="plain" onClick={pick(() => void syncNow())} disabled={syncing}>
                {syncing ? "Syncing…" : "Sync"}
              </button>
              {install !== "installed" && <button type="button" className="plain" onClick={pick(download)}>Download</button>}
              <button type="button" className="plain" onClick={pick(() => setChanging(!changing))}>Change password</button>
              <button type="button" className="plain" onClick={pick(onLogout)}>Log out</button>
            </div>
          )}
        </div>
      </div>
      {steps && install !== "installed" && <InstallSteps onClose={() => setSteps(false)} />}
      {changing && <ChangePassword onDone={() => setChanging(false)} />}
    </>
  );
}

// Shows what a tap switches to: the moon in light mode, the sun in dark mode.
function ThemeButton() {
  const [theme, setShown] = useState<Theme>(currentTheme);

  // Until someone chooses, the page follows the device, which can change while it's open.
  useEffect(() => {
    const follow = () => setShown(currentTheme());
    systemDark.addEventListener("change", follow);
    return () => systemDark.removeEventListener("change", follow);
  }, []);

  function toggle() {
    const next = theme === "dark" ? "light" : "dark";
    setTheme(next);
    setShown(next);
  }

  const label = theme === "dark" ? "Light mode" : "Dark mode";
  return (
    <button type="button" className="plain theme" onClick={toggle} aria-label={label} title={label}>
      <svg viewBox="0 0 20 20" width="20" height="20" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
        {theme === "dark" ? (
          <>
            <circle cx="10" cy="10" r="3.5" />
            <path d="M10 1.5v2M10 16.5v2M1.5 10h2M16.5 10h2M4 4l1.4 1.4M14.6 14.6L16 16M4 16l1.4-1.4M14.6 5.4L16 4" />
          </>
        ) : (
          <path d="M16.5 12.2A7 7 0 1 1 7.8 3.5a5.5 5.5 0 0 0 8.7 8.7z" />
        )}
      </svg>
    </button>
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
