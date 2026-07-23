import { build } from 'esbuild';
import { fileURLToPath } from 'node:url';
import { gzipSync } from 'node:zlib';

const targetBytes = 110 * 1024;
const approvedLimitBytes = 113 * 1024;
const entryPoint = fileURLToPath(
  new URL('../frontend/dashboard/src/visualization/renderer/echartsRenderer.ts', import.meta.url),
);

const result = await build({
  entryPoints: [entryPoint],
  bundle: true,
  format: 'esm',
  minify: true,
  metafile: true,
  outdir: 'visualization-renderer',
  platform: 'browser',
  splitting: true,
  target: ['es2022'],
  treeShaking: true,
  write: false,
});

const kib = (bytes) => `${(bytes / 1024).toFixed(2)} kB`;
const chunks = result.outputFiles
  .filter((output) => output.path.endsWith('.js'))
  .map((output) => ({
    file: output.path.split('/').at(-1),
    minifiedBytes: output.contents.byteLength,
    gzipBytes: gzipSync(output.contents, { level: 9, mtime: 0 }).byteLength,
  }))
  .sort((left, right) => right.gzipBytes - left.gzipBytes);
const forbiddenInputs = Object.keys(result.metafile.inputs)
  .filter((input) => /(?:^|\/)three(?:\/|$)|node_modules\/three\//.test(input));

for (const chunk of chunks) {
  console.log(`${chunk.file}: ${kib(chunk.minifiedBytes)} minified / ${kib(chunk.gzipBytes)} gzip`);
}
const largestChunk = chunks[0];
console.log(
  `largest visualization chunk ${kib(largestChunk?.gzipBytes ?? 0)} gzip ` +
    `(target ${kib(targetBytes)}; ADR limit ${kib(approvedLimitBytes)})`,
);
if (forbiddenInputs.length) {
  for (const input of forbiddenInputs) console.error(`removed Three.js input remains: ${input}`);
  process.exitCode = 1;
}
if (largestChunk && largestChunk.gzipBytes > approvedLimitBytes) {
  console.error(
    `visualization renderer chunk ${largestChunk.file} ${kib(largestChunk.gzipBytes)} exceeds ${kib(approvedLimitBytes)}`,
  );
  const outputEntry = Object.entries(result.metafile.outputs).find(([path]) => path.endsWith(largestChunk.file));
  if (outputEntry) {
    const topInputs = Object.entries(outputEntry[1].inputs)
      .sort((left, right) => right[1].bytesInOutput - left[1].bytesInOutput)
      .slice(0, 12);
    for (const [input, detail] of topInputs) console.error(`  ${kib(detail.bytesInOutput)} ${input}`);
  }
  process.exitCode = 1;
} else if (largestChunk && largestChunk.gzipBytes > targetBytes) {
  console.warn(`visualization renderer uses the measured ADR exception above the ${kib(targetBytes)} target`);
}
