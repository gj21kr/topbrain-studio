import { createHash } from 'node:crypto';
import { lstat, open, readFile, readdir } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const dist = path.join(root, 'dist');
const files = new Set();
const MiB = 1024 * 1024;
const referenceModel = 'reference/bodyparts3d.glb';
const referenceManifest = 'reference/bodyparts3d.json';
const referenceAttribution = 'reference/ATTRIBUTION.txt';
const officialArchiveSha256 = '9fbc713fffeee924a5a657d9813d84d7eb957bded63adb854931dd5e3eb61c97';
// Intentional atlas updates require source/license review and new approved digests.
const approvedReferenceSha256 = new Map([
  [referenceModel, '91e0728981428b0eca88fa9818f3902c39a87a0d35485cc9ecd24aca8ee83b82'],
  [referenceManifest, '7d31bdbed3b0b6795fd4ed36a5324c91829f22cb18b45f43848b1545f2c48094'],
  [referenceAttribution, '07dba8cbad86b5fd09fd821fa1b9d2469b280f80b75f9bec9830724d02e2749b']
]);
const fileLimits = new Map([
  ['index.html', 2 * MiB],
  ['favicon.svg', 2 * MiB],
  [referenceModel, 16 * MiB],
  [referenceManifest, 2 * MiB],
  [referenceAttribution, 64 * 1024]
]);
// The Gaussian-splat renderer (Spark, with its inlined worker and WASM) is a lazily loaded chunk of about 2.5 MiB,
// emitted as assets/spark.module-<hash>.js, so chunk names may carry a dot.
const fileLimit = (name) => fileLimits.get(name) ?? (/^assets\/[A-Za-z0-9_.-]+\.(?:css|js)$/.test(name) ? 4 * MiB : undefined);

async function inspectDirectory(directory) {
  for (const entry of await readdir(directory, { withFileTypes: true })) {
    const fullPath = path.join(directory, entry.name);
    const relativePath = path.relative(dist, fullPath).split(path.sep).join('/');
    const details = await lstat(fullPath);

    if (details.isSymbolicLink()) throw new Error(`Symlink in public build: ${relativePath}`);
    if (details.isDirectory()) {
      if (!['assets', 'reference'].includes(relativePath)) throw new Error(`Unexpected directory in public build: ${relativePath}`);
      await inspectDirectory(fullPath);
    } else if (details.isFile() && fileLimit(relativePath) !== undefined) {
      if (details.nlink !== 1) throw new Error(`Hard link in public build: ${relativePath}`);
      if (details.size === 0 || details.size > fileLimit(relativePath)) throw new Error(`Invalid public file size: ${relativePath}`);
      files.add(relativePath);
    } else {
      throw new Error(`Unexpected file in public build: ${relativePath}`);
    }
  }
}

const distDetails = await lstat(dist);
if (!distDetails.isDirectory() || distDetails.isSymbolicLink()) {
  throw new Error('Public build output must be a real directory');
}
await inspectDirectory(dist);
for (const required of ['index.html', 'favicon.svg', referenceModel, referenceManifest, referenceAttribution]) {
  if (!files.has(required)) throw new Error(`Missing public file: ${required}`);
}
if (![...files].some((file) => /^assets\/[^/]+\.js$/.test(file))) {
  throw new Error('Missing JavaScript bundle');
}

for (const [name, expected] of approvedReferenceSha256) {
  const contents = await readFile(path.join(dist, name));
  // Git may check out text with CRLF on Windows; pin its LF content across platforms.
  const canonical = name === referenceManifest || name === referenceAttribution
    ? contents.toString('utf8').replace(/\r\n/g, '\n')
    : contents;
  const actual = createHash('sha256').update(canonical).digest('hex');
  if (actual !== expected) throw new Error(`Unreviewed public reference asset: ${name}`);
}

const reference = JSON.parse(await readFile(path.join(dist, referenceManifest), 'utf8'));
if (!reference || typeof reference !== 'object' || Array.isArray(reference) ||
    reference.coordinateSystem !== 'glTF-Y-up' || reference.units !== 'm' ||
    !Array.isArray(reference.structures) || reference.structures.length === 0 ||
    reference.structures.some((structure) => /TotalSegmentator/i.test(String(structure?.source ?? ''))) ||
    !String(reference.source ?? '').includes('BodyParts3D') ||
    !/CC (?:BY|Attribution) 4\.0/i.test(String(reference.license ?? '')) ||
    !String(reference.provenance ?? '').includes('partof_BP3D_4.0_obj_99.zip') ||
    !String(reference.provenance ?? '').includes(officialArchiveSha256)) {
  throw new Error('Reference manifest must identify the official BodyParts3D 4.0 PART-OF source and CC BY 4.0 license');
}
if (!Array.isArray(reference.connectionGuides) || reference.connectionGuides.length !== 4 ||
    reference.connectionGuides.some((guide) => guide?.kind !== 'schematic')) {
  throw new Error('Reference gap guides must remain explicitly schematic');
}

const modelPath = path.join(dist, referenceModel);
const modelSize = (await lstat(modelPath)).size;
const model = await open(modelPath, 'r');
try {
  const header = Buffer.alloc(20);
  let offset = 0;
  while (offset < header.length) {
    const { bytesRead } = await model.read(header, offset, header.length - offset, offset);
    if (bytesRead === 0) break;
    offset += bytesRead;
  }
  if (offset !== header.length || header.toString('ascii', 0, 4) !== 'glTF' ||
      header.readUInt32LE(4) !== 2 || header.readUInt32LE(8) !== modelSize ||
      header.readUInt32LE(12) % 4 !== 0 || header.readUInt32LE(12) + 20 > modelSize ||
      header.readUInt32LE(16) !== 0x4e4f534a) {
    throw new Error('Reference model is not a complete GLB 2.0 file');
  }
} finally {
  await model.close();
}

const credit = await readFile(path.join(dist, referenceAttribution), 'utf8');
if (!credit.includes('BodyParts3D, © The Database Center for Life Science licensed under CC Attribution 4.0 International') ||
    !credit.includes('https://dbarchive.biosciencedbc.jp/en/bodyparts3d/lic.html')) {
  throw new Error('Reference attribution must retain the official credit and license link');
}

if (process.env.GITHUB_PAGES === 'true') {
  const base = `/${(process.env.GITHUB_REPOSITORY ?? 'gj21kr/topbrain-studio').split('/')[1]}/`;
  const html = await readFile(path.join(dist, 'index.html'), 'utf8');
  const references = [...html.matchAll(/\b(?:src|href)=["']([^"']+)["']/g)].map((match) => match[1]);
  for (const reference of references) {
    if (!reference.startsWith('/')) continue;
    if (!reference.startsWith(base)) throw new Error(`Root-relative URL bypasses Pages base: ${reference}`);
    const localPath = reference.slice(base.length).split(/[?#]/, 1)[0];
    if (!files.has(localPath)) throw new Error(`Missing Pages asset: ${reference}`);
  }
  if (!references.some((reference) => reference.startsWith(`${base}assets/`))) {
    throw new Error('Pages HTML does not reference a base-prefixed bundle');
  }
}

console.log(`Public build checked: ${[...files].sort().join(', ')}`);
