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

const brapi = async (url, maxAge) => {
  const token = process.env.BRAPI_TOKEN;
  try {
    const res = await fetch(url, { headers: token ? { Authorization: `Bearer ${token}` } : {} });
    return new Response(await res.text(), {
      status: res.status,
      headers: {
        'content-type': 'application/json; charset=utf-8',
        'cache-control': res.ok ? `public, max-age=${maxAge}` : 'no-store',
      },
    });
  } catch {
    return json(502, { error: true, code: 'UPSTREAM', message: 'Não foi possível consultar as cotações agora.' });
  }
};

export default async (req) => {
  const params = new URL(req.url).searchParams;

  // Busca por nome da empresa ou código: /api/cotacao?busca=petrobras
  const busca = (params.get('busca') || '').trim();
  if (busca) {
    if (busca.length < 2 || busca.length > 40) {
      return json(400, { error: true, code: 'INVALID_SEARCH', message: 'Busca inválida.' });
    }
    return brapi(`https://brapi.dev/api/quote/list?search=${encodeURIComponent(busca)}&limit=12`, 3600);
  }

  const ticker = (params.get('ticker') || '').trim().toUpperCase();
  const range = params.get('range') || '3mo';

  if (!/^\^?[A-Z0-9]{3,8}$/.test(ticker)) {
    return json(400, { error: true, code: 'INVALID_TICKER', message: 'Código de ação inválido.' });
  }
  if (!RANGES[range]) {
    return json(400, { error: true, code: 'INVALID_RANGE', message: 'Período inválido.' });
  }

  // Cotações mudam devagar para este uso: 5 minutos de cache poupam o limite da chave.
  return brapi(`https://brapi.dev/api/quote/${encodeURIComponent(ticker)}?range=${range}&interval=${RANGES[range]}`, 300);
};

export const config = { path: '/api/cotacao' };
