/**
 * Summary: Defines the lazy read-only Library browsing route boundary.
 * Why: Loads persisted Track inspection without pulling feature code into the app shell.
 */
import { LibraryList } from "../../features/library/library-list";

export function Component() {
  return <LibraryList />;
}
