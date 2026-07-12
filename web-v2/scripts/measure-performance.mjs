/**
 * Summary: Records deterministic installed-package shell timing and JavaScript size evidence.
 * Why: Establishes the M1 performance baseline without enforcing later milestone budgets.
 */
import { spawnSync } from "node:child_process";
import { mkdirSync, writeFileSync } from "node:fs";
import { cpus, freemem } from "node:os";
import { dirname, resolve } from "node:path";
import process from "node:process";
import { createRequire } from "node:module";
import { chromium } from "@playwright/test";

import { performanceProtocol } from "../performance/config.mjs";

const require = createRequire(import.meta.url);
const playwrightPackage = require("@playwright/test/package.json");
const baseURL = process.env.OMYM2_PERFORMANCE_BASE_URL;

if (baseURL === undefined || baseURL.length === 0) {
  throw new Error(
    "OMYM2_PERFORMANCE_BASE_URL must identify an installed production package server.",
  );
}

const browser = await chromium.launch();
try {
  for (
    let warmupIndex = 0;
    warmupIndex < performanceProtocol.warmupRuns;
    warmupIndex += 1
  ) {
    await runColdNavigation(browser, baseURL);
  }
  const coldResults = [];
  for (
    let runIndex = 0;
    runIndex < performanceProtocol.measuredRuns;
    runIndex += 1
  ) {
    coldResults.push(await runColdNavigation(browser, baseURL));
  }

  const warmContext = await browser.newContext();
  const warmPage = await warmContext.newPage();
  const warmSession = await warmContext.newCDPSession(warmPage);
  await warmSession.send("Network.enable");
  await warmSession.send("Network.setCacheDisabled", { cacheDisabled: false });
  for (
    let warmupIndex = 0;
    warmupIndex < performanceProtocol.warmupRuns;
    warmupIndex += 1
  ) {
    await measureNavigation(warmPage, baseURL);
  }

  const warmResults = [];
  for (
    let runIndex = 0;
    runIndex < performanceProtocol.measuredRuns;
    runIndex += 1
  ) {
    warmResults.push(await measureNavigation(warmPage, baseURL));
  }
  await warmContext.close();

  const javascriptUrls = [
    ...new Set(coldResults.flatMap((result) => result.javascriptUrls)),
  ].sort();
  const javascript = await gzipJavascript(javascriptUrls);
  const cpuList = cpus();
  const chromiumExecutablePath = chromium.executablePath();
  const chromiumRevisionMatch =
    /(?:chromium|chromium_headless_shell)-(\d+)/.exec(chromiumExecutablePath);
  const report = {
    protocol: {
      measuredRuns: performanceProtocol.measuredRuns,
      warmupRuns: performanceProtocol.warmupRuns,
      enforcement: "record-only",
    },
    runner: {
      image: process.env.ImageOS ?? process.platform,
      imageVersion: process.env.ImageVersion ?? "unreported",
      nodeVersion: process.version,
      playwrightVersion: playwrightPackage.version,
      chromiumVersion: browser.version(),
      chromiumExecutablePath,
      chromiumRevision: chromiumRevisionMatch?.[1] ?? "unreported",
      cpuModel: cpuList[0]?.model ?? "unreported",
      logicalCpuCount: cpuList.length,
      availableMemoryBytes: freemem(),
    },
    results: {
      coldMedianMs: median(coldResults.map((result) => result.interactiveMs)),
      warmMedianMs: median(warmResults.map((result) => result.interactiveMs)),
      gzippedJavascriptBytes: javascript.totalBytes,
      javascriptResources: javascript.resources,
    },
  };
  const serialized = `${JSON.stringify(report, null, 2)}\n`;
  const outputPath = process.env.OMYM2_PERFORMANCE_OUTPUT;
  if (outputPath === undefined || outputPath.length === 0) {
    process.stdout.write(serialized);
  } else {
    const absoluteOutputPath = resolve(outputPath);
    mkdirSync(dirname(absoluteOutputPath), { recursive: true });
    writeFileSync(absoluteOutputPath, serialized, "utf8");
  }
} finally {
  await browser.close();
}

async function runColdNavigation(browserInstance, url) {
  const context = await browserInstance.newContext();
  const page = await context.newPage();
  const session = await context.newCDPSession(page);
  await session.send("Network.enable");
  await session.send("Network.setCacheDisabled", { cacheDisabled: true });
  const result = await measureNavigation(page, url);
  await context.close();
  return result;
}

async function measureNavigation(page, url) {
  await page.goto(url, { waitUntil: "domcontentloaded" });
  await page
    .locator("[data-omym2-shell-interactive='true']")
    .waitFor({ state: "attached" });
  return page.evaluate(() => {
    const interactiveMs = performance.now();
    const javascriptUrls = performance
      .getEntriesByType("resource")
      .filter(
        (entry) =>
          entry instanceof PerformanceResourceTiming &&
          entry.initiatorType === "script" &&
          new URL(entry.name).origin === globalThis.location.origin &&
          entry.responseEnd <= interactiveMs,
      )
      .map((entry) => entry.name);
    return { interactiveMs, javascriptUrls };
  });
}

async function gzipJavascript(urls) {
  const resources = [];
  for (const url of urls) {
    const response = await fetch(url);
    if (!response.ok) {
      throw new Error(
        `Unable to retrieve measured JavaScript resource: ${url}`,
      );
    }
    const source = Buffer.from(await response.arrayBuffer());
    const compressed = spawnSync(
      performanceProtocol.gzipCommand,
      performanceProtocol.gzipArguments,
      {
        input: source,
      },
    );
    if (compressed.error) {
      throw compressed.error;
    }
    if (compressed.status !== 0) {
      throw new Error(
        `${performanceProtocol.gzipCommand} exited with status ${String(compressed.status)}`,
      );
    }
    resources.push({ url, bytes: compressed.stdout.length });
  }
  return {
    resources,
    totalBytes: resources.reduce(
      (total, resource) => total + resource.bytes,
      0,
    ),
  };
}

function median(values) {
  const ordered = values.toSorted((left, right) => left - right);
  const middle = Math.floor(ordered.length / 2);
  const value = ordered[middle];
  if (value === undefined) {
    throw new Error("Cannot calculate a median without measurements.");
  }
  return value;
}
