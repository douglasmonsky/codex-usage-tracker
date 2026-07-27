#!/usr/bin/env node

import { createHash } from "node:crypto";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = dirname(dirname(fileURLToPath(import.meta.url)));
const source = join(root, "frontend", "kernel-console");
const destination = join(
  root,
  "src",
  "codex_usage_tracker",
  "kernel",
  "interfaces",
  "http",
  "console_assets",
);
const names = ["app.js", "index.html", "model.js", "styles.css"];
const check = process.argv.includes("--check");

await mkdir(destination, { recursive: true });
const assets = {};
for (const name of names) {
  const payload = await readFile(join(source, name));
  assets[name] = createHash("sha256").update(payload).digest("hex");
  const target = join(destination, name);
  if (check) {
    const current = await readFile(target).catch(() => null);
    if (!current || !current.equals(payload)) {
      throw new Error(`${name} is not the deterministic source build`);
    }
  } else {
    await writeFile(target, payload);
  }
}
const manifest = `${JSON.stringify({
  schema: "codex-usage-tracker.kernel-console-assets.v1",
  assets,
}, null, 2)}\n`;
const manifestPath = join(destination, "asset-manifest.json");
if (check) {
  const current = await readFile(manifestPath, "utf8").catch(() => "");
  if (current !== manifest) throw new Error("asset-manifest.json is stale");
} else {
  await writeFile(manifestPath, manifest);
}
