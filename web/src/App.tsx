import { useEffect, useState } from "react";

import { Shell } from "./components/Shell";
import { CheckPage } from "./pages/CheckPage";
import { HistoryPage } from "./pages/HistoryPage";
import { RunDetailPage } from "./pages/RunDetailPage";
import { SettingsPage } from "./pages/SettingsPage";
import { TracksPage } from "./pages/TracksPage";

type Route =
  | { name: "settings" }
  | { name: "history" }
  | { name: "run_detail"; runId: string }
  | { name: "check" }
  | { name: "tracks" };

export function App() {
  const [path, setPath] = useState(window.location.pathname);

  useEffect(() => {
    const handlePopState = () => setPath(window.location.pathname);
    window.addEventListener("popstate", handlePopState);
    return () => window.removeEventListener("popstate", handlePopState);
  }, []);

  const route = routeFromPath(path);
  return (
    <Shell activeRoute={route.name} onNavigate={setPath}>
      {route.name === "settings" && <SettingsPage />}
      {route.name === "history" && <HistoryPage />}
      {route.name === "run_detail" && <RunDetailPage runId={route.runId} />}
      {route.name === "check" && <CheckPage />}
      {route.name === "tracks" && <TracksPage />}
    </Shell>
  );
}

function routeFromPath(path: string): Route {
  if (path === "/" || path === "/settings") {
    return { name: "settings" };
  }
  if (path === "/history") {
    return { name: "history" };
  }
  if (path.startsWith("/history/")) {
    return { name: "run_detail", runId: decodeURIComponent(path.replace("/history/", "")) };
  }
  if (path === "/check") {
    return { name: "check" };
  }
  if (path === "/tracks") {
    return { name: "tracks" };
  }
  return { name: "settings" };
}
