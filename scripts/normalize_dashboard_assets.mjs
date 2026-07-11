import { readdir, readFile, writeFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const repositoryRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const assetsRoot = path.join(
  repositoryRoot,
  'src',
  'codex_usage_tracker',
  'plugin_data',
  'dashboard',
  'react',
  'assets',
);

for (const filePath of await assetFiles(assetsRoot)) {
  const source = await readFile(filePath, 'utf8');
  const normalized = source
    .replace(/[\t ]+$/gm, '')
    .replace(/^ +(?=\t)/gm, '');
  if (normalized !== source) await writeFile(filePath, normalized);
}

async function assetFiles(directory) {
  const entries = await readdir(directory, { withFileTypes: true });
  const files = await Promise.all(entries.map(async entry => {
    const entryPath = path.join(directory, entry.name);
    if (entry.isDirectory()) return assetFiles(entryPath);
    return /\.(?:css|js)$/.test(entry.name) ? [entryPath] : [];
  }));
  return files.flat();
}
