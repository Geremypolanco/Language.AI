import { createRoot } from "react-dom/client";
import App from "./App";
import "./index.css";

createRoot(document.getElementById("root")!).render(<App />);

// Offline-first PWA: registers the runtime-caching service worker (see
// public/sw.js) so the app shell and previously-viewed lesson/unit data
// stay available without a connection — production only, so local dev's
// rapid rebuilds never get served a stale cached bundle.
if (import.meta.env.PROD && "serviceWorker" in navigator) {
  window.addEventListener("load", () => {
    navigator.serviceWorker.register("/sw.js").catch(() => {
      // Best-effort — a failed registration just means no offline support,
      // never a broken app.
    });
  });
}
