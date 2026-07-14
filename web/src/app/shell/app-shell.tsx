/**
 * Summary: Renders the responsive application shell and global interaction surfaces.
 * Why: Provides stable navigation, shortcut discovery, and route focus management.
 */
import {
  lazy,
  Suspense,
  useCallback,
  useRef,
  useState,
  type MouseEvent,
} from "react";
import { Outlet } from "react-router-dom";

import { useGlobalShortcuts } from "../shortcuts/use-global-shortcuts";
import { BootstrapBoundary } from "../../features/bootstrap/bootstrap-boundary";
import { Icon } from "../../ui/icon";
import { Button } from "../../ui/primitives/button";
import { Dialog } from "../../ui/primitives/dialog";
import {
  LiveAnnouncementProvider,
  LiveRegion,
} from "../../ui/primitives/live-region";
import { Navigation } from "./navigation";
import { shellCopy } from "./shell-copy";
import styles from "./app-shell.module.css";

const loadCommandCenter = () =>
  import("../../features/command-center/command-center-dialog");
const LazyCommandCenter = lazy(async () => {
  const module = await loadCommandCenter();
  return { default: module.CommandCenterDialog };
});

export function AppShell() {
  const [commandCenterOpen, setCommandCenterOpen] = useState(false);
  const [commandCenterRequested, setCommandCenterRequested] = useState(false);
  const [navigationOpen, setNavigationOpen] = useState(false);
  const [shortcutHelpOpen, setShortcutHelpOpen] = useState(false);
  const [shortcutsReady, setShortcutsReady] = useState(false);
  const commandCenterOpenRef = useRef(false);
  const commandReturnFocusRef = useRef<HTMLElement | null>(null);
  const menuButtonRef = useRef<HTMLButtonElement>(null);
  const navigationReturnFocusRef = useRef<HTMLElement | null>(null);
  const shortcutHelpOpenRef = useRef(false);
  const shortcutReturnFocusRef = useRef<HTMLElement | null>(null);

  const requestCommandCenter = useCallback(
    (returnTarget: HTMLElement | null) => {
      if (commandCenterOpenRef.current) {
        return;
      }
      commandCenterOpenRef.current = true;
      commandReturnFocusRef.current = returnTarget;
      setCommandCenterRequested(true);
      setCommandCenterOpen(true);
    },
    [],
  );

  const closeCommandCenter = useCallback(() => {
    commandCenterOpenRef.current = false;
    setCommandCenterOpen(false);
  }, []);

  const openCommandCenter = useCallback(() => {
    requestCommandCenter(
      document.activeElement instanceof HTMLElement
        ? document.activeElement
        : null,
    );
  }, [requestCommandCenter]);

  const requestShortcutHelp = useCallback(
    (returnTarget: HTMLElement | null) => {
      if (shortcutHelpOpenRef.current) {
        return;
      }
      shortcutHelpOpenRef.current = true;
      shortcutReturnFocusRef.current = returnTarget;
      setShortcutHelpOpen(true);
    },
    [],
  );

  const closeShortcutHelp = useCallback(() => {
    shortcutHelpOpenRef.current = false;
    setShortcutHelpOpen(false);
  }, []);

  const openShortcutHelp = useCallback(() => {
    requestShortcutHelp(
      document.activeElement instanceof HTMLElement
        ? document.activeElement
        : null,
    );
  }, [requestShortcutHelp]);
  const markShortcutsReady = useCallback(() => setShortcutsReady(true), []);

  useGlobalShortcuts({
    onCommandCenter: openCommandCenter,
    onReady: markShortcutsReady,
    onShortcutHelp: openShortcutHelp,
  });

  function openCommandCenterFromButton(event: MouseEvent<HTMLButtonElement>) {
    requestCommandCenter(event.currentTarget);
  }

  function openShortcutHelpFromButton(event: MouseEvent<HTMLButtonElement>) {
    requestShortcutHelp(event.currentTarget);
  }

  function openShortcutHelpFromNavigation() {
    setNavigationOpen(false);
    requestShortcutHelp(menuButtonRef.current);
  }

  function openNavigation(event: MouseEvent<HTMLButtonElement>) {
    navigationReturnFocusRef.current = event.currentTarget;
    setNavigationOpen(true);
  }

  function navigateFromDrawer() {
    navigationReturnFocusRef.current = null;
    setNavigationOpen(false);
  }

  return (
    <div
      className={styles.shell}
      data-omym2-shell-interactive={shortcutsReady ? "true" : undefined}
    >
      <a className={styles.skipLink} href="#main-content">
        {shellCopy.skipToContent}
      </a>

      <aside className={styles.rail}>
        <Brand />
        <Navigation />
        <Button
          onClick={openCommandCenterFromButton}
          onFocus={() => void loadCommandCenter()}
          onMouseEnter={() => void loadCommandCenter()}
          title={shellCopy.commandCenter}
          variant="secondary"
        >
          <Icon name="command" />
          <span className={styles.railActionLabel}>
            {shellCopy.commandCenter}
          </span>
        </Button>
        <Button
          onClick={openShortcutHelpFromButton}
          title={shellCopy.shortcutHelp}
          variant="quiet"
        >
          <Icon name="info" />
          <span className={styles.railActionLabel}>
            {shellCopy.shortcutHelp}
          </span>
        </Button>
        <p className={styles.railFooter}>{shellCopy.footer}</p>
      </aside>

      <header className={styles.mobileHeader}>
        <Brand />
        <div className={styles.mobileActions}>
          <Button
            aria-label={shellCopy.commandCenter}
            iconOnly
            onClick={openCommandCenterFromButton}
            onFocus={() => void loadCommandCenter()}
            onMouseEnter={() => void loadCommandCenter()}
            variant="quiet"
          >
            <Icon name="search" />
          </Button>
          <Button
            aria-label={shellCopy.openNavigation}
            iconOnly
            onClick={openNavigation}
            ref={menuButtonRef}
            variant="quiet"
          >
            <Icon name="menu" />
          </Button>
        </div>
      </header>

      <main className={styles.main} id="main-content" tabIndex={-1}>
        <div className={styles.routeFrame}>
          <LiveAnnouncementProvider>
            <BootstrapBoundary>
              <Outlet />
            </BootstrapBoundary>
          </LiveAnnouncementProvider>
        </div>
      </main>

      <Dialog
        closeLabel={shellCopy.closeNavigation}
        label={shellCopy.navigationTitle}
        onRequestClose={() => setNavigationOpen(false)}
        open={navigationOpen}
        returnFocusRef={navigationReturnFocusRef}
        variant="drawer"
      >
        <div className={styles.mobileNavigation}>
          <Navigation onNavigate={navigateFromDrawer} />
          <Button onClick={openShortcutHelpFromNavigation} variant="quiet">
            {shellCopy.shortcutHelp}
          </Button>
        </div>
      </Dialog>

      <Dialog
        closeLabel={shellCopy.closeShortcutHelp}
        label={shellCopy.shortcutHelp}
        onRequestClose={closeShortcutHelp}
        open={shortcutHelpOpen}
        returnFocusRef={shortcutReturnFocusRef}
      >
        <p>{shellCopy.shortcutHelpDescription}</p>
        <ul className={styles.shortcutList}>
          {shellCopy.shortcuts.map(([key, description]) => (
            <li className={styles.shortcutRow} key={key}>
              <kbd className={styles.keycap}>{key}</kbd>
              <span>{description}</span>
            </li>
          ))}
        </ul>
      </Dialog>

      {commandCenterRequested ? (
        <Suspense
          fallback={<LiveRegion>{shellCopy.loadingCommandCenter}</LiveRegion>}
        >
          <LazyCommandCenter
            onRequestClose={closeCommandCenter}
            open={commandCenterOpen}
            returnFocusRef={commandReturnFocusRef}
          />
        </Suspense>
      ) : null}
    </div>
  );
}

function Brand() {
  return (
    <div className={styles.brand}>
      <p className={styles.brandName}>
        <span className={styles.brandFull}>{shellCopy.productName}</span>
        <span className={styles.brandCompact}>O2</span>
      </p>
      <p className={styles.brandDescription}>{shellCopy.productDescription}</p>
    </div>
  );
}
