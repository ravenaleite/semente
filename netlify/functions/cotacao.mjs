// Função de servidor (Netlify Functions) que busca cotações na brapi.dev.
// A chave fica na variável de ambiente BRAPI_TOKEN, configurada no painel do
// Netlify, e por isso nunca aparece no código da página.
//
// Uso pela página:
//   /api/cotacao?ticker=PETR4&range=3mo   cotação e histórico de uma ação
//   /api/cotacao?busca=petrobras          lista de ações pelo nome ou código

const RANGES = { '1mo': '1d', '3mo': '1d', '6mo': '1d', '1y': '1d', '5y': '1wk' };

const json = (status, body, extra = {}) =>
  new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json; charset=utf-8', ...extra },
  });

// Chamada à brapi. Devolve a resposta original (status e corpo) ou null se a rede falhar.
const chamar = async (url) => {
  const token = process.env.BRAPI_TOKEN;
  try {
    const res = await fetch(url, { headers: token ? { Authorization: `Bearer ${token}` } : {} });
    return { ok: res.ok, status: res.status, body: await res.text() };
  } catch {
    return null;
  }
};

// Respostas de sucesso ficam guardadas no CDN do Netlify e são compartilhadas por todos os
// visitantes: assim cada cotação custa uma chamada a cada 5 minutos, não uma por pessoa.
// O plano gratuito da brapi tem 15 mil chamadas por mês.
const responder = (r, maxAge, extra = {}) => {
  if (!r) return json(502, { error: true, code: 'UPSTREAM', message: 'Não foi possível consultar as cotações agora.' });
  return new Response(r.body, {
    status: r.status,
    headers: {
      'content-type': 'application/json; charset=utf-8',
      'cache-control': r.ok ? `public, max-age=${maxAge}` : 'no-store',
      ...(r.ok ? {
        'netlify-cdn-cache-control': `public, s-maxage=${maxAge}, stale-while-revalidate=60, durable`,
        'netlify-vary': 'query',
      } : {}),
      ...extra,
    },
  });
};

export default async (req) => {
  const params = new URL(req.url).searchParams;

  // Busca por nome da empresa ou código: /api/cotacao?busca=petrobras
  const busca = (params.get('busca') || '').trim();
  if (busca) {
    if (busca.length < 2 || busca.length > 40) {
      return json(400, { error: true, code: 'INVALID_SEARCH', message: 'Busca inválida.' });
    }
    return responder(await chamar(`https://brapi.dev/api/quote/list?search=${encodeURIComponent(busca)}&limit=12`), 3600);
  }

  const ticker = (params.get('ticker') || '').trim().toUpperCase();
  const range = params.get('range') || '3mo';

  if (!/^\^?[A-Z0-9]{3,8}$/.test(ticker)) {
    return json(400, { error: true, code: 'INVALID_TICKER', message: 'Código de ação inválido.' });
  }
  if (!RANGES[range]) {
    return json(400, { error: true, code: 'INVALID_RANGE', message: 'Período inválido.' });
  }

  const url = (r) => `https://brapi.dev/api/quote/${encodeURIComponent(ticker)}?range=${r}&interval=${RANGES[r]}`;
  const r = await chamar(url(range));
  // O plano gratuito da brapi só entrega 3 meses de histórico. Se um período maior for recusado,
  // devolve 3 meses e avisa a página pelo cabeçalho, em vez de mostrar erro.
  if (r && !r.ok && ['6mo', '1y', '5y'].includes(range)) {
    const curto = await chamar(url('3mo'));
    if (curto && curto.ok) return responder(curto, 300, { 'x-semente-range': '3mo' });
  }
  return responder(r, 300, { 'x-semente-range': range });
};

export const config = { path: '/api/cotacao' };
