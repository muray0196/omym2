/**
 * Summary: Owns the clean-room MSW server used by frontend tests.
 * Why: Gives generated API handlers one strict shared interception boundary.
 */
import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";

import { normalBootstrap } from "./fixtures/bootstrap";

export const server = setupServer(
  http.get("*/api/bootstrap", () => HttpResponse.json(normalBootstrap)),
);
