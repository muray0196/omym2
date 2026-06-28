import type { ReactNode } from "react";

type ActiveRoute = "settings" | "history" | "run_detail" | "check" | "tracks";

type ShellProps = {
  activeRoute: ActiveRoute;
  children: ReactNode;
  onNavigate: (path: string) => void;
};

const navItems = [
  { href: "/settings", label: "Settings", route: "settings" },
  { href: "/history", label: "History", route: "history" },
  { href: "/check", label: "Check", route: "check" },
  { href: "/tracks", label: "Tracks", route: "tracks" }
] as const;

export function Shell({ activeRoute, children, onNavigate }: ShellProps) {
  return (
    <div className="app-shell">
      <header className="topbar">
        <a className="brand" href="/settings" onClick={(event) => navigate(event, "/settings", onNavigate)}>
          OMYM2
        </a>
        <nav className="topnav" aria-label="Primary">
          {navItems.map((item) => {
            const isActive = activeRoute === item.route || (activeRoute === "run_detail" && item.route === "history");
            return (
              <a
                key={item.href}
                className={isActive ? "topnav__link topnav__link--active" : "topnav__link"}
                href={item.href}
                onClick={(event) => navigate(event, item.href, onNavigate)}
              >
                {item.label}
              </a>
            );
          })}
        </nav>
      </header>
      <main className="main-content">{children}</main>
    </div>
  );
}

function navigate(event: React.MouseEvent<HTMLAnchorElement>, path: string, onNavigate: (path: string) => void) {
  event.preventDefault();
  window.history.pushState({}, "", path);
  onNavigate(path);
}
