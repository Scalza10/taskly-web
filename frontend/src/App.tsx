// Decides between the login screen and the list. undefined = still asking the server.
import { useEffect, useState } from "react";
import { api, type Me } from "./api";
import { AccountBar } from "./AccountBar";
import { Login } from "./Login";
import { isLoggedOut } from "./messages";
import { TodoPage } from "./TodoPage";

export function App() {
  const [user, setUser] = useState<string | null | undefined>(undefined);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api<Me>("GET", "/api/me").then(
      (me) => setUser(me.username),
      (e) => (isLoggedOut(e) ? setUser(null) : setError((e as Error).message)),
    );
  }, []);

  if (error) return <main><h1>Taskly</h1><p className="error" role="alert">{error}</p></main>;
  if (user === undefined) return null;
  if (user === null) return <Login onLoggedIn={setUser} />;
  return (
    <>
      <AccountBar username={user} onLoggedOut={() => setUser(null)} />
      <TodoPage onLoggedOut={() => setUser(null)} />
    </>
  );
}
