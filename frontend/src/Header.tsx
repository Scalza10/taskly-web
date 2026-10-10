// The top of every signed-in screen: the wordmark, the screen tabs (on a phone they're the bar at
// the bottom, see TabBar), search (opens SearchScreen), who is logged in, the light/dark button and a menu (the burger button)
// with "Sync" (send waiting changes and download the latest now; the result shows in the status
// line), "Download" (install as an app), "Change password" and "Log out" (the logout itself lives
// in App, so it survives the switch to the login screen when the session has expired). On a phone
// the light/dark choice moves into the menu, so the header stays on one line.
import { Menu, Moon, Search, Sun } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { ChangePassword } from "./ChangePassword";
import { Avatar, Wordmark } from "./Chrome";
import { sync } from "./device";
import { promptInstall, useInstall } from "./install";
import { SCREENS, type Screen } from "./screen";
import { currentTheme, setTheme, systemDark, type Theme } from "./theme";
import { useWide } from "./useWide";

type Props = {
  username: string;
  screen: Screen;
  searching: boolean;
  onScreen: (screen: Screen) => void;
  onSearch: () => void;
  onLogout: () => void;
};

export function Header({ username, screen, searching, onScreen, onSearch, onLogout }: Props) {
  const wide = useWide();
  const [open, setOpen] = useState(false);
  const [changing, setChanging] = useState(false);
  const [steps, setSteps] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [theme, toggleTheme] = useTheme();
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

  const themeLabel = theme === "dark" ? "Light mode" : "Dark mode";

  return (
    <>
      <header className="top">
        <Wordmark />
        {wide && <ScreenTabs screen={screen} onScreen={onScreen} />}
        <div className="who">
          <button
            type="button"
            className={wide ? "round outline" : "round"}
            aria-label="Search"
            aria-pressed={searching}
            title="Search every list"
            onClick={onSearch}
          >
            <Search size={wide ? 18 : 20} aria-hidden="true" />
          </button>
          <Avatar name={username} />
          {wide && <span className="who-name">{username}</span>}
          {wide && (
            <button type="button" className="round outline" onClick={toggleTheme} aria-label={themeLabel} title={themeLabel}>
              {theme === "dark" ? <Moon size={18} aria-hidden="true" /> : <Sun size={18} aria-hidden="true" />}
            </button>
          )}
          <div className="menu" ref={menu}>
            <button
              type="button"
              className={wide ? "round outline" : "round"}
              ref={toggleButton}
              aria-label="Menu"
              aria-expanded={open}
              aria-controls="account-menu"
              onClick={() => setOpen(!open)}
            >
              <Menu size={wide ? 18 : 20} aria-hidden="true" />
            </button>
            {open && (
              <div className="menu-items" id="account-menu">
                {!wide && <span className="menu-who">{username}</span>}
                <button type="button" onClick={pick(() => void syncNow())} disabled={syncing}>
                  {syncing ? "Syncing…" : "Sync"}
                </button>
                {!wide && <button type="button" onClick={pick(toggleTheme)}>{themeLabel}</button>}
                {install !== "installed" && <button type="button" onClick={pick(download)}>Download</button>}
                <button type="button" onClick={pick(() => setChanging(!changing))}>Change password</button>
                <button type="button" onClick={pick(onLogout)}>Log out</button>
              </div>
            )}
          </div>
        </div>
      </header>
      {steps && install !== "installed" && <InstallSteps onClose={() => setSteps(false)} />}
      {changing && <ChangePassword onDone={() => setChanging(false)} />}
    </>
  );
}

// The pill group in the desktop header; the Focus screen's modes look the same.
export function ScreenTabs({ screen, onScreen }: { screen: Screen; onScreen: (screen: Screen) => void }) {
  return (
    <nav className="pills" aria-label="Screens">
      {SCREENS.map((s) => (
        <button key={s.screen} type="button" className="pill" aria-current={s.screen === screen ? "page" : undefined} onClick={() => onScreen(s.screen)}>
          {s.label}
        </button>
      ))}
    </nav>
  );
}

// The phone's tab bar, at the bottom of the screen.
export function TabBar({ screen, onScreen }: { screen: Screen; onScreen: (screen: Screen) => void }) {
  return (
    <div className="tabbar">
      <nav aria-label="Screens">
        {SCREENS.map((s) => (
          <button key={s.screen} type="button" aria-current={s.screen === screen ? "page" : undefined} onClick={() => onScreen(s.screen)}>
            {s.label}
          </button>
        ))}
      </nav>
    </div>
  );
}

// Light or dark; until someone chooses, the page follows the device, which can change while it's open.
function useTheme(): [Theme, () => void] {
  const [theme, setShown] = useState<Theme>(currentTheme);

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

  return [theme, toggle];
}

function InstallSteps({ onClose }: { onClose: () => void }) {
  return (
    <div className="card panel stack">
      <p className="hint">Install Taskly to open it like an app and use it offline:</p>
      <ul className="steps">
        <li><b>iPhone or iPad (Safari):</b> Share → Add to Home Screen</li>
        <li><b>Android (Chrome):</b> menu → Install app</li>
        <li><b>Computer (Chrome or Edge):</b> the install icon at the end of the address bar</li>
        <li><b>Mac (Safari):</b> File → Add to Dock</li>
      </ul>
      <p className="hint">Already installed? Open Taskly from your home screen or apps.</p>
      <div className="row">
        <button type="button" className="text" onClick={onClose}>Close</button>
      </div>
    </div>
  );
}
