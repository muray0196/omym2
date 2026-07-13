/**
 * Summary: Emulates deterministic 200% desktop browser zoom through layout metrics.
 * Why: Proves reflow accessibility without substituting pinch-zoom behavior.
 */
import type { Page } from "@playwright/test";

export const DESKTOP_ZOOM_FACTOR = 2;
export const DESKTOP_ZOOM_PHYSICAL_VIEWPORT = {
  height: 800,
  width: 1280,
} as const;
export const DESKTOP_ZOOM_LAYOUT_VIEWPORT = {
  height: DESKTOP_ZOOM_PHYSICAL_VIEWPORT.height / DESKTOP_ZOOM_FACTOR,
  width: DESKTOP_ZOOM_PHYSICAL_VIEWPORT.width / DESKTOP_ZOOM_FACTOR,
} as const;
export const DESKTOP_ZOOM_DEVICE_PIXEL_RATIO = DESKTOP_ZOOM_FACTOR;
export const DESKTOP_ZOOM_VISUAL_VIEWPORT_SCALE = 1;
export const DESKTOP_ZOOM_EXPECTED_METRICS = {
  devicePixelRatio: DESKTOP_ZOOM_DEVICE_PIXEL_RATIO,
  layoutHeight: DESKTOP_ZOOM_LAYOUT_VIEWPORT.height,
  layoutWidth: DESKTOP_ZOOM_LAYOUT_VIEWPORT.width,
  physicalHeight: DESKTOP_ZOOM_PHYSICAL_VIEWPORT.height,
  physicalWidth: DESKTOP_ZOOM_PHYSICAL_VIEWPORT.width,
  visualViewportScale: DESKTOP_ZOOM_VISUAL_VIEWPORT_SCALE,
} as const;

export async function applyDesktopZoom(page: Page) {
  await page.setViewportSize(DESKTOP_ZOOM_PHYSICAL_VIEWPORT);
  const session = await page.context().newCDPSession(page);
  await session.send("Emulation.setDeviceMetricsOverride", {
    deviceScaleFactor: DESKTOP_ZOOM_DEVICE_PIXEL_RATIO,
    height: DESKTOP_ZOOM_LAYOUT_VIEWPORT.height,
    mobile: false,
    width: DESKTOP_ZOOM_LAYOUT_VIEWPORT.width,
  });
  return session;
}

export function readDesktopZoomMetrics(page: Page) {
  return page.evaluate(() => ({
    devicePixelRatio: globalThis.devicePixelRatio,
    layoutHeight: globalThis.innerHeight,
    layoutWidth: globalThis.innerWidth,
    physicalHeight: globalThis.outerHeight,
    physicalWidth: globalThis.outerWidth,
    visualViewportScale: globalThis.visualViewport?.scale ?? null,
  }));
}
