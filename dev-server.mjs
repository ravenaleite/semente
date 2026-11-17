// Servidor local para testar o site com as funções de servidor, sem precisar publicar.
//
//   node dev-server.mjs
//
// Abre em http://localhost:8770. Para testar com a chave da brapi, defina a variável
// de ambiente BRAPI_TOKEN antes de rodar (nunca escreva a chave dentro deste arquivo).

import { createServer } from 'node:http';
import { readFile } from 'node:fs/promises';
import { extname, join, normalize } from 'node:path';
import { fileURLToPath } from 'node:url';
import cotacao from './netlify/functions/cotacao.mjs';
import noticias from './netlify/functions/noticias.mjs';

const ROOT = fileURLToPath(new URL('./public/', import.meta.url)); // só a pasta public é servida, como no Netlify
const PORT = Number(process.env.PORT) || 8770;
const API = { '/api/cotacao': cotacao, '/api/noticias': noticias };
const TYPES = {
  '.html': 'text/html; charset=utf-8', '.css': 'text/css; charset=utf-8', '.js': 'text/javascript; charset=utf-8',
  '.mjs': 'text/javascript; charset=utf-8', '.json': 'application/json; charset=utf-8', '.svg': 'image/svg+xml',
  '.webmanifest': 'application/manifest+json; charset=utf-8', '.png': 'image/png', '.jpg': 'image/jpeg', '.webp': 'image/webp', '.ico': 'image/x-icon',
};

createServer(async (req, res) => {
  const url = new URL(req.url, `http://localhost:${PORT}`);
  try {
    const fn = API[url.pathname];
    if (fn) {
      const out = await fn(new Request(url));
      res.writeHead(out.status, Object.fromEntries(out.headers));
      res.end(await out.text());
      return;
    }
    const rel = url.pathname === '/' ? 'semente.html' : decodeURIComponent(url.pathname.slice(1));
    const file = normalize(join(ROOT, rel));
    // Não serve nada fora da pasta do projeto, nem arquivos ocultos (como .env).
    if (!file.startsWith(ROOT) || rel.split(/[\\/]/).some((p) => p.startsWith('.'))) throw new Error('fora');
    const body = await readFile(file);
    res.writeHead(200, { 'content-type': TYPES[extname(file)] || 'application/octet-stream', 'cache-control': 'no-store' });
    res.end(body);
  } catch {
    res.writeHead(404, { 'content-type': 'text/plain; charset=utf-8' });
    res.end('Não encontrado');
  }
}).listen(PORT, '127.0.0.1', () => console.log(`Semente em http://localhost:${PORT}`));
