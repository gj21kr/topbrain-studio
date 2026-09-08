import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import type { Connect, Plugin } from 'vite';
const root = path.dirname(fileURLToPath(import.meta.url));
const localCase: Connect.NextHandleFunction = (request, response, next) => {
  const files: Record<string, [string, string]> = { '/local-case/manifest.json': ['topbrain-cta-001.json', 'application/json'], '/local-case/model.glb': ['topbrain-cta-001.glb', 'model/gltf-binary'] };
  const file = files[request.url ?? ''];
  if (!file) return next();
  const local = new Set(['127.0.0.1', '::1', '::ffff:127.0.0.1']);
  if (!local.has(request.socket.remoteAddress ?? '') || (request.headers['sec-fetch-site'] && !['same-origin', 'none'].includes(String(request.headers['sec-fetch-site'])))) { response.statusCode = 403; response.end(); return; }
  if (request.method !== 'GET' && request.method !== 'HEAD') { response.statusCode = 405; response.end(); return; }
  const target = path.join(root, 'private-assets', file[0]);
  if (!fs.existsSync(target)) { response.statusCode = 404; response.end('Local case not prepared.'); return; }
  response.setHeader('Content-Type', file[1]); response.setHeader('Cache-Control', 'no-store'); response.setHeader('Cross-Origin-Resource-Policy', 'same-origin');
  response.setHeader('Content-Length', fs.statSync(target).size);
  if (request.method === 'HEAD') { response.end(); return; }
  const stream = fs.createReadStream(target); stream.on('error', () => { response.destroy(); }); stream.pipe(response);
};
const localCasePlugin: Plugin = { name: 'loopback-local-case', configureServer(server) { server.middlewares.use(localCase); }, configurePreviewServer(server) { server.middlewares.use(localCase); } };
export default defineConfig({ plugins: [react(), localCasePlugin], server: { host: '127.0.0.1', port: 5181, strictPort: true, fs: { deny: ['.env', '.env.*', '*.{crt,pem}', '**/.git/**', '**/private-assets/**', '**/data/**'] } }, preview: { host: '127.0.0.1', port: 5181, strictPort: true } });
