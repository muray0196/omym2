/**
 * Summary: Verifies shell shortcuts, lazy Command Center behavior, and focus restoration.
 * Why: Protects the keyboard-first foundation at its primary interaction boundary.
 */
import { screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { renderShell } from "../../test/render-shell";

describe("AppShell", () => {
  it("marks the shell interactive after its global shortcut listener is installed", async () => {
    const { container } = renderShell();

    await waitFor(() => {
      expect(
        container.querySelector("[data-omym2-shell-interactive='true']"),
      ).toBeInTheDocument();
    });
  });

  it("opens the lazy Command Center and restores focus when it closes", async () => {
    const { user } = renderShell();
    const trigger = within(screen.getByRole("banner")).getByRole("button", {
      name: "Command Center",
    });

    await user.click(trigger);
    const dialog = await screen.findByRole("dialog", {
      name: "Command Center",
    });
    expect(dialog).toBeVisible();
    expect(
      screen.getByRole("combobox", { name: "Search commands and navigation" }),
    ).toHaveFocus();

    await user.click(
      screen.getByRole("button", { name: "Close Command Center" }),
    );
    await waitFor(() => expect(dialog).not.toBeVisible());
    expect(trigger).toHaveFocus();
  });

  it("keeps an empty Command Center listbox connected to its combobox", async () => {
    const { user } = renderShell();
    await user.click(
      within(screen.getByRole("complementary")).getByRole("button", {
        name: "Command Center",
      }),
    );
    const search = await screen.findByRole("combobox", {
      name: "Search commands and navigation",
    });

    await user.type(search, "no matching destination");

    expect(
      screen.getByText("No commands or destinations match your search."),
    ).toBeVisible();
    const listbox = screen.getByRole("listbox", { name: "Command results" });
    expect(listbox).toBeEmptyDOMElement();
    expect(search).toHaveAttribute("aria-controls", listbox.id);
  });

  it("moves focus to the destination heading after Command Center navigation", async () => {
    const { user } = renderShell();

    await user.click(
      within(screen.getByRole("banner")).getByRole("button", {
        name: "Command Center",
      }),
    );
    const search = await screen.findByRole("combobox", {
      name: "Search commands and navigation",
    });
    await user.type(search, "Settings");
    await user.keyboard("{Enter}");

    const heading = await screen.findByRole("heading", { name: "Settings" });
    await waitFor(() => expect(heading).toHaveFocus());
  });

  it("preserves the original Command Center focus target after a repeated shortcut", async () => {
    const { user } = renderShell();
    const trigger = within(screen.getByRole("complementary")).getByRole(
      "button",
      { name: "Command Center" },
    );

    await user.click(trigger);
    const dialog = await screen.findByRole("dialog", {
      name: "Command Center",
    });
    await user.keyboard("{Control>}k{/Control}");
    await user.click(
      screen.getByRole("button", { name: "Close Command Center" }),
    );

    await waitFor(() => expect(dialog).not.toBeVisible());
    await waitFor(() => expect(trigger).toHaveFocus());
  });

  it("focuses the destination heading after drawer navigation", async () => {
    const { user } = renderShell();

    await user.click(screen.getByRole("button", { name: "Open navigation" }));
    const drawer = await screen.findByRole("dialog", { name: "Navigation" });
    await user.click(within(drawer).getByRole("link", { name: "Settings" }));

    const heading = await screen.findByRole("heading", { name: "Settings" });
    await waitFor(() => expect(heading).toHaveFocus());
  });

  it("preserves the original shortcut-help focus target after repeated help", async () => {
    const { user } = renderShell();
    const trigger = within(screen.getByRole("complementary")).getByRole(
      "button",
      { name: "Keyboard shortcuts" },
    );

    await user.click(trigger);
    const dialog = await screen.findByRole("dialog", {
      name: "Keyboard shortcuts",
    });
    await user.keyboard("?");
    await user.click(
      screen.getByRole("button", { name: "Close keyboard shortcuts" }),
    );

    await waitFor(() => expect(dialog).not.toBeVisible());
    await waitFor(() => expect(trigger).toHaveFocus());
  });

  it("does not open shortcut help from an editable field", async () => {
    const { user } = renderShell("/settings");
    const field = screen.getByRole("textbox", { name: "Draft field" });

    await user.click(field);
    await user.keyboard("?");

    expect(
      screen.queryByRole("dialog", { name: "Keyboard shortcuts" }),
    ).not.toBeInTheDocument();
    expect(field).toHaveValue("?");
  });
});
