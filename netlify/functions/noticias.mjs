// Função de servidor (Netlify Functions) que lê o feed público de notícias da
// Finsiders Brasil e devolve só as manchetes: título, link e data.
// O navegador não consegue ler o feed direto (o site não libera CORS), por isso passa por aqui.
//
// Uso pela página: /api/noticias

const FEED = 'https://finsidersbrasil.com.br/feed/';
const ORIGIN = 'https://finsidersbrasil.com.br/';

const json = (status, body, cache = 'no-store') =>
  new Response(JSON.stringify(body), {
    status,
    headers: {
      'content-type': 'application/json; charset=utf-8',
      'cache-control': cache,
      // Guardado no CDN do Netlify e compartilhado entre visitantes, para poupar o site de origem.
      ...(status === 200 ? { 'netlify-cdn-cache-control': 'public, s-maxage=900, stale-while-revalidate=300, durable' } : {}),
    },
  });

const decode = (s) =>
  s
    .replace(/<!\[CDATA\[([\s\S]*?)\]\]>/g, '$1')
    .replace(/&#x([0-9a-f]+);/gi, (_, n) => String.fromCodePoint(parseInt(n, 16)))
    .replace(/&#(\d+);/g, (_, n) => String.fromCodePoint(Number(n)))
    .replace(/&quot;/g, '"')
    .replace(/&apos;/g, "'")
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/&amp;/g, '&')
    .replace(/<[^>]*>/g, '')
    .trim();

const tag = (xml, name) => {
  const m = xml.match(new RegExp(`<${name}>([\\s\\S]*?)</${name}>`));
  return m ? decode(m[1]) : '';
};

export default async () => {
  try {
    const res = await fetch(FEED, { headers: { 'user-agent': 'Mozilla/5.0 (compatible; leitor-de-feed)' } });
    if (!res.ok) throw new Error('feed');
    const xml = await res.text();
    const items = xml
      .split('<item>')
      .slice(1)
      .map((chunk) => {
        const date = new Date(tag(chunk, 'pubDate'));
        return {
          title: tag(chunk, 'title'),
          link: tag(chunk, 'link'),
          date: Number.isNaN(date.getTime()) ? null : date.toISOString(),
        };
      })
      // Só aceita links do próprio site de origem.
      .filter((it) => it.title && it.link.startsWith(ORIGIN))
      .slice(0, 6);
    if (!items.length) throw new Error('vazio');
    // 15 minutos de cache: manchetes não mudam a cada minuto e o site de origem é poupado.
    return json(200, { source: 'Finsiders Brasil', items }, 'public, max-age=900');
  } catch {
    return json(502, { error: true, code: 'UPSTREAM', message: 'Não foi possível buscar as notícias agora.' });
  }
};

export const config = { path: '/api/noticias' };
