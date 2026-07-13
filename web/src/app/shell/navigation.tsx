/**
 * Summary: Renders the shared primary navigation from centralized route copy.
 * Why: Keeps desktop and drawer navigation semantically identical.
 */
import { NavLink } from "react-router-dom";

import { Icon } from "../../ui/icon";
import { navigationItems, shellCopy } from "./shell-copy";
import styles from "./app-shell.module.css";

export function Navigation({ onNavigate }: { onNavigate?: () => void }) {
  return (
    <nav aria-label={shellCopy.navigationLabel} className={styles.navigation}>
      {navigationItems.map((item) => (
        <NavLink
          className={styles.navigationLink}
          end={item.to === "/"}
          key={item.to}
          onClick={onNavigate}
          to={item.to}
        >
          <Icon name={item.icon} />
          {item.label}
        </NavLink>
      ))}
    </nav>
  );
}
