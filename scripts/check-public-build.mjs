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
// The one published dataset case: TopBrain 2025 CTA subject topcow_ct_001 (attribution required, non-commercial),
// approved by the maintainer for this non-commercial demo. A different case, transfer function or splat budget
// needs a new license review and new approved digests.
const caseDirectory = 'cases/topbrain-ct-001';
const caseModel = `${caseDirectory}/case.glb`;
const caseManifest = `${caseDirectory}/case.json`;
const caseSplats = `${caseDirectory}/case.context.ply`;
const caseContext = `${caseDirectory}/case.context.json`;
const caseAttribution = `${caseDirectory}/ATTRIBUTION.txt`;
const caseImageSha256 = '9dea5c8138e6884bdd9480d16ac4ed05f6a61ed9cccde658b2052d4d627030b3';
const approvedCaseSha256 = new Map([
  [caseModel, 'c8c619d75c3e30850bcb5bb4532e05b5aeadf983ffffaffb9de643f16925b9e2'],
  [caseManifest, '42b2cdc16fcabbc5dda05cfc5160cb12852cac821571d7bc37490559adb26add'],
  [caseSplats, 'b0167fc8c3a299d6db591aac1c824ee3a9d501c26ed175d2ac0c871f707457f8'],
  [caseContext, 'eea4d991fe0d6310c01fcc7b7406cb32bc72559e877b83fd67a4b5092b5acfb9'],
  [caseAttribution, 'afa9221b8238ed671a53080368cb372dd9c5215b4d77618122f2afda5b41a4f5']
]);
const textFiles = new Set([referenceManifest, referenceAttribution, caseManifest, caseContext, caseAttribution]);
const fileLimits = new Map([
  ['index.html', 2 * MiB],
  ['favicon.svg', 2 * MiB],
  [referenceModel, 16 * MiB],
  [referenceManifest, 2 * MiB],
  [referenceAttribution, 64 * 1024],
  [caseModel, 8 * MiB],
  [caseManifest, 2 * MiB],
  [caseSplats, 40 * MiB],
  [caseContext, 2 * MiB],
  [caseAttribution, 64 * 1024]
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
      if (!['assets', 'reference', 'cases', caseDirectory].includes(relativePath)) throw new Error(`Unexpected directory in public build: ${relativePath}`);
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
for (const required of ['index.html', 'favicon.svg', ...approvedReferenceSha256.keys(), ...approvedCaseSha256.keys()]) {
  if (!files.has(required)) throw new Error(`Missing public file: ${required}`);
}
if (![...files].some((file) => /^assets\/[^/]+\.js$/.test(file))) {
  throw new Error('Missing JavaScript bundle');
}

for (const [name, expected] of [...approvedReferenceSha256, ...approvedCaseSha256]) {
  const contents = await readFile(path.join(dist, name));
  // Git may check out text with CRLF on Windows; pin its LF content across platforms.
  const canonical = textFiles.has(name) ? contents.toString('utf8').replace(/\r\n/g, '\n') : contents;
  const actual = createHash('sha256').update(canonical).digest('hex');
  if (actual !== expected) throw new Error(`Unreviewed public asset: ${name}`);
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

async function checkGlb(name) {
  const modelPath = path.join(dist, name);
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
      throw new Error(`Not a complete GLB 2.0 file: ${name}`);
    }
  } finally {
    await model.close();
  }
}
await checkGlb(referenceModel);
await checkGlb(caseModel);

const topBrain = /TopBrain 2025/;
const topBrainRecord = 'https://doi.org/10.5281/zenodo.21972006';
const topBrainTerms = /attribution required[\s\S]*non-commercial use is free[\s\S]*commercial use requires permission of the data owner, University Hospital Zurich/i;
const demoCase = JSON.parse(await readFile(path.join(dist, caseManifest), 'utf8'));
const demoContext = JSON.parse(await readFile(path.join(dist, caseContext), 'utf8'));
if (!demoCase || typeof demoCase !== 'object' || Array.isArray(demoCase) ||
    demoCase.coordinateSystem !== 'glTF-Y-up' || demoCase.units !== 'm' ||
    !Array.isArray(demoCase.structures) || demoCase.structures.length !== 23 ||
    !topBrain.test(String(demoCase.source ?? '')) || !String(demoCase.source ?? '').includes(topBrainRecord) ||
    !topBrainTerms.test(String(demoCase.license ?? '')) ||
    demoCase.metadata?.modality !== 'CTA' || demoCase.metadata?.subject !== 'topcow_ct_001' ||
    demoCase.metadata?.ctSha256 !== caseImageSha256 || demoCase.metadata?.datasetUrl !== topBrainRecord) {
  throw new Error('Case manifest must identify the TopBrain 2025 CTA subject, its Zenodo record and its attribution / non-commercial terms');
}
if (!demoContext || typeof demoContext !== 'object' || Array.isArray(demoContext) ||
    demoContext.kind !== 'gaussian-splat-context' || demoContext.modality !== 'CTA' ||
    demoContext.subject !== 'topcow_ct_001' || demoContext.ctSha256 !== caseImageSha256 ||
    JSON.stringify(demoContext.voxelToGltfM) !== JSON.stringify(demoCase.metadata?.voxelToGltfM) ||
    !topBrain.test(String(demoContext.source ?? '')) || !topBrainTerms.test(String(demoContext.license ?? '')) ||
    !Number.isInteger(demoContext.splats) || demoContext.splats > 650000 || demoContext.splatBudget !== 650000 ||
    !Array.isArray(demoContext.transferFunction) || demoContext.transferFunction.some((band) => !Number.isInteger(band?.stride) || band.stride < band.strideRequested)) {
  throw new Error('Case context layer must belong to the same TopBrain CTA image and record its splat budget and strides');
}
const splatHeader = (await readFile(path.join(dist, caseSplats))).subarray(0, 4096).toString('ascii');
if (!splatHeader.startsWith('ply\nformat binary_little_endian 1.0\n') || !splatHeader.includes(`element vertex ${demoContext.splats}\n`)) {
  throw new Error('Case splat PLY must hold the splat count its context JSON declares');
}
const caseCredit = await readFile(path.join(dist, caseAttribution), 'utf8');
if (!topBrain.test(caseCredit) || !caseCredit.includes(topBrainRecord) || !caseCredit.includes('https://opendata.swiss/en/terms-of-use') ||
    !caseCredit.includes('University Hospital Zurich') || !caseCredit.includes(caseImageSha256) || !/non-commercial/i.test(caseCredit)) {
  throw new Error('Case attribution must retain the TopBrain source, record, owner, terms and image checksum');
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
