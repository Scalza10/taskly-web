import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App";
import "./style.css";
import { registerSW } from "virtual:pwa-register";
import { watchInstall } from "./install";

registerSW({ immediate: true });
watchInstall();

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
