import { gzipSync } from 'node:zlib';
import { readFile, readdir } from 'node:fs/promises';

const outputDir = new URL('../src/codex_usage_tracker/plugin_data/dashboard/react/', import.meta.url);
const budgets = {
  currentInitialJs: 168 * 1024,
  currentInitialCss: 10 * 1024,
  targetInitialJs: 85 * 1024,
  targetInitialCss: 12 * 1024,
  routeJs: 65 * 1024,
  visualizationRouteJs: 110 * 1024,
  routeCss: 20 * 1024
};

const html = await readFile(new URL('index.html', outputDir), 'utf8');
const initialFiles = new Set(
  [...html.matchAll(/(?:src|href)="[^"]*\/(assets\/[^"?]+)(?:\?[^"\s]*)?"/g)].map((match) => match[1])
);

const assetDir = new URL('assets/', outputDir);
const assets = (await readdir(assetDir)).filter((file) => /\.(css|js)$/.test(file)).sort();
const rows = [];
for (const file of assets) {
  const content = await readFile(new URL(file, assetDir));
  const outputPath = `assets/${file}`;
  rows.push({
    file: outputPath,
    gzipBytes: gzipSync(content, { level: 9, mtime: 0 }).byteLength,
    kind: initialFiles.has(outputPath) ? 'initial' : 'route'
  });
}

const kib = (bytes) => `${(bytes / 1024).toFixed(2)} kB`;
for (const row of rows) console.log(`${row.kind.padEnd(7)} ${kib(row.gzipBytes).padStart(10)}  ${row.file}`);
const initialJsBytes = rows
  .filter((row) => row.kind === 'initial' && row.file.endsWith('.js'))
  .reduce((sum, row) => sum + row.gzipBytes, 0);
const initialCssBytes = rows
  .filter((row) => row.kind === 'initial' && row.file.endsWith('.css'))
  .reduce((sum, row) => sum + row.gzipBytes, 0);
console.log(
  `initial javascript ${kib(initialJsBytes)} ` +
    `(current-state budget ${kib(budgets.currentInitialJs)}; redesign target ${kib(budgets.targetInitialJs)})`
);
console.log(
  `initial css ${kib(initialCssBytes)} ` +
    `(current-state budget ${kib(budgets.currentInitialCss)}; redesign target ${kib(budgets.targetInitialCss)})`
);

const failures = [];
if (initialJsBytes > budgets.currentInitialJs) {
  failures.push(`initial javascript ${kib(initialJsBytes)} exceeds ${kib(budgets.currentInitialJs)}`);
}
if (initialCssBytes > budgets.currentInitialCss) {
  failures.push(`initial css ${kib(initialCssBytes)} exceeds ${kib(budgets.currentInitialCss)}`);
}
for (const row of rows.filter((item) => item.kind === 'route' && item.file.endsWith('.js'))) {
  const limit = /visualization|chart/i.test(row.file) ? budgets.visualizationRouteJs : budgets.routeJs;
  if (row.gzipBytes > limit) failures.push(`${row.file} ${kib(row.gzipBytes)} exceeds ${kib(limit)}`);
}
for (const row of rows.filter((item) => item.kind === 'route' && item.file.endsWith('.css'))) {
  if (row.gzipBytes > budgets.routeCss) failures.push(`${row.file} ${kib(row.gzipBytes)} exceeds ${kib(budgets.routeCss)}`);
}
if (failures.length) {
  for (const failure of failures) console.error(`bundle budget exceeded: ${failure}`);
  process.exitCode = 1;
}
