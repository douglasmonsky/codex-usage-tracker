#!/usr/bin/env node

import { readFile, stat } from "node:fs/promises";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = dirname(dirname(fileURLToPath(import.meta.url)));
const source = join(root, "frontend", "kernel-console");
const assets = ["app.js", "index.html", "model.js", "styles.css"];
const contents = Object.fromEntries(
  await Promise.all(assets.map(async (name) => [name, await readFile(join(source, name), "utf8")])),
);
const totalBytes = (await Promise.all(assets.map((name) => stat(join(source, name)))))
  .reduce((total, item) => total + item.size, 0);
const failures = [];

function luminance(hex) {
  const channels = hex.match(/[a-f\d]{2}/gi).map((value) => {
    const channel = Number.parseInt(value, 16) / 255;
    return channel <= 0.04045 ? channel / 12.92 : ((channel + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2];
}

function contrast(foreground, background) {
  const values = [luminance(foreground), luminance(background)].sort((a, b) => b - a);
  return (values[0] + 0.05) / (values[1] + 0.05);
}

if (totalBytes > 90_000) failures.push(`console bundle ${totalBytes} exceeds 90000 bytes`);
for (const required of [
  '<html lang="en">',
  'class="skip-link"',
  '<nav aria-label="Primary navigation">',
  'aria-live="polite"',
  '<main id="workspace"',
]) {
  if (!contents["index.html"].includes(required)) failures.push(`missing accessibility contract: ${required}`);
}
for (const route of ["live", "explore", "evidence", "limits", "settings"]) {
  if (!contents["index.html"].includes(`href="/${route}"`)) failures.push(`missing approved route ${route}`);
}
for (const retired of ["insights", "reports", "diagnostics", "compression-lab"]) {
  if (contents["index.html"].includes(`href="/${retired}"`)) failures.push(`retired route restored: ${retired}`);
}
for (const prohibited of ["usage_analyze", "findings", "recommendation engine", "OpenTelemetry"]) {
  if (Object.values(contents).some((payload) => payload.includes(prohibited))) {
    failures.push(`prohibited product dependency: ${prohibited}`);
  }
}
if (!contents["app.js"].includes('method: "POST", body: "{}"')) {
  failures.push("explicit refresh action is missing");
}
if (contents["app.js"].match(/boot\(\)[\s\S]{0,300}\/refresh/)) {
  failures.push("browser boot must not trigger refresh");
}
if (!contents["styles.css"].includes("@media (prefers-reduced-motion: reduce)")) {
  failures.push("reduced-motion support is missing");
}
if (!contents["styles.css"].includes("--callout-ink: #dbeafe")) {
  failures.push("dark-mode callout contrast token is missing");
}
if (contrast("#dbeafe", "#172d59") < 4.5) {
  failures.push("dark-mode callout contrast is below 4.5:1");
}
if (!contents["app.js"].includes("const COPY = Object.freeze")) {
  failures.push("localizable copy catalog is missing");
}

if (failures.length) {
  console.error(failures.join("\n"));
  process.exitCode = 1;
} else {
  console.log(`Kernel Console checks passed (${totalBytes} bytes).`);
}
