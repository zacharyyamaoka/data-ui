// npm run serve: the docs site (dist/site/) on 127.0.0.1, on PORT, else 4610, else the next free port.
// Build first (npm run build). Stop it with Ctrl-C. DATA_UI_SITE serves another folder (the unit test's fixture).
import { createServer } from 'node:http';
import { createReadStream, existsSync, statSync } from 'node:fs';
import { extname, join, normalize, dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = process.env.DATA_UI_SITE ? resolve(process.env.DATA_UI_SITE) : join(dirname(fileURLToPath(import.meta.url)), '..', 'dist', 'site');
const TYPES = { '.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8', '.mjs': 'text/javascript; charset=utf-8', '.css': 'text/css; charset=utf-8',
  '.json': 'application/json; charset=utf-8', '.map': 'application/json', '.base': 'text/yaml; charset=utf-8', '.md': 'text/markdown; charset=utf-8',
  '.csv': 'text/csv; charset=utf-8', '.jsonl': 'application/x-ndjson', '.svg': 'image/svg+xml', '.png': 'image/png', '.jpg': 'image/jpeg', '.webp': 'image/webp', '.pmtiles': 'application/octet-stream' };
// WHY: Open in Rerun's hosted viewer (app.rerun.io) fetches the dashboard's .rrd from this origin (docs/RERUN.md); the
// deployed site grants the same through dist/site/_headers (site/build-site.mjs SITE_HEADERS)
const RERUN = 'https://app.rerun.io';

if (!existsSync(join(ROOT, 'index.html'))) {
  console.error('dist/site/ is not built: run  npm --prefix ~/data-ui run build');
  process.exit(1);
}

const server = createServer((req, res) => {
  const path = decodeURIComponent(new URL(req.url, 'http://x').pathname);
  let file = normalize(join(ROOT, path));
  if (!file.startsWith(ROOT)) { res.writeHead(403).end(); return; }
  const cors = extname(file) === '.rrd' ? { 'access-control-allow-origin': RERUN, vary: 'origin' } : {};
  if (req.method === 'OPTIONS') {
    // the preflight a viewer's fetch may send (a Range header); Access-Control-Allow-Private-Network answers older
    // Chrome's Private Network Access preflight from a public page to 127.0.0.1 (Chrome 142+ asks the reader instead)
    const asked = req.headers['access-control-request-headers'];
    const pna = req.headers['access-control-request-private-network'] === 'true';
    res.writeHead(204, extname(file) === '.rrd' ? { ...cors, 'access-control-allow-methods': 'GET, HEAD',
      ...(asked ? { 'access-control-allow-headers': asked } : {}), ...(pna ? { 'access-control-allow-private-network': 'true' } : {}),
      'access-control-max-age': '600' } : {}).end();
    return;
  }
  if (existsSync(file) && statSync(file).isDirectory()) file = join(file, 'index.html');
  if (!existsSync(file)) { res.writeHead(404, { 'content-type': 'text/plain' }).end('not found'); return; }
  res.writeHead(200, { 'content-type': TYPES[extname(file)] || 'application/octet-stream', 'cache-control': 'no-cache', ...cors });
  createReadStream(file).pipe(res);
});

const wanted = Number(process.env.PORT || 4610);
let port = wanted;
server.on('error', (err) => {
  if (err.code === 'EADDRINUSE' && !process.env.PORT && port < wanted + 50) { port++; server.listen(port, '127.0.0.1'); return; }
  console.error(err.message);
  process.exit(1);
});
server.on('listening', () => console.log(`data-ui site: http://127.0.0.1:${server.address().port}/`));
server.listen(port, '127.0.0.1');
