# Semente

Educação financeira na prática: um aplicativo web gratuito para aprender finanças vendo o dinheiro crescer, em vez de decorar siglas.

**No ar:** https://semente-simulador.netlify.app

Pode ser instalado no celular como aplicativo (PWA), sempre com o visual escuro, e abre mesmo sem internet. É uma ferramenta educativa: explica e simula, não recomenda investimentos.

## O que o app faz

- **Simulador de juros compostos:** valor inicial, aporte mensal, prazo em anos ou meses e taxa ao ano, ao mês ou em % do CDI (o CDI do dia vem do Banco Central).
- **Imposto de Renda opcional:** aplica a tabela regressiva da renda fixa e mostra o valor líquido.
- **Inflação e custo de esperar:** quanto o resultado vale em dinheiro de hoje e quanto se perde adiando o início.
- **Exemplos prontos** para quem não sabe por onde começar.
- **Aprender:** cinco lições curtas (juros compostos; Selic, CDI e inflação; renda fixa e variável; reserva de emergência; como ler a oferta do banco), cada uma com um botão "Ver na prática".
- **Mercado:** Ibovespa, dólar, Selic e inflação; cotações da bolsa com busca pelo nome da empresa e gráfico; manchetes da Finsiders Brasil. Tudo se atualiza sozinho a cada 5 minutos com a página aberta.
- **Conta sem senha:** entrada por link enviado ao e-mail, para salvar e reabrir simulações. Nesta fase, limitada a 100 contas.

## Estrutura

```
public/                    tudo o que vai ao ar (pasta publicada pelo Netlify)
  semente.html             o aplicativo inteiro (HTML, CSS e JS num arquivo só)
  privacidade.html         política de privacidade
  config.js                URL e chave PÚBLICA do Supabase
  manifest.webmanifest     dados para instalar como app
  sw.js                    service worker (funcionamento offline)
  icons/                   ícones do app (192, 512, maskable, iPhone e 1024 para as lojas)
  og-image.png             imagem de pré-visualização do link (1200 × 630)
netlify/functions/
  cotacao.mjs              busca cotações e lista de ações na brapi.dev (guarda a chave)
  noticias.mjs             lê o feed de notícias da Finsiders Brasil
supabase/
  schema.sql               tabela das simulações e regras de segurança por linha
  limite-de-contas.sql     trava de 100 contas
  emails/link-de-acesso.html   e-mail de acesso em português, para colar no Supabase
divulgacao/                post do LinkedIn e imagens
dev-server.mjs             servidor local com as funções (fora do ar)
simulador-de-celulares.html  vê o app em 6 tamanhos de Android e iPhone (fora do ar)
auditar.py                 auditoria de contraste, meta tags, segurança e acessibilidade (fora do ar)
netlify.toml               configuração de publicação
```

## Rodar no computador

Precisa do Node.js.

```bash
node dev-server.mjs
```

Abre em http://localhost:8770. Para testar todas as ações da bolsa, defina a variável de ambiente `BRAPI_TOKEN` antes de rodar. Nunca escreva a chave dentro de um arquivo do projeto.

## Publicar

```bash
netlify deploy --prod --dir public --functions netlify/functions
```

## Serviços externos

| Serviço | Para quê | Configuração |
|---|---|---|
| Netlify | Hospedagem e funções | Variável de ambiente `BRAPI_TOKEN` |
| Supabase | Contas e simulações salvas | `public/config.js` (só a chave pública); rodar os dois arquivos de `supabase/` no SQL Editor |
| Gmail (`acesso.semente@gmail.com`) | Envio dos e-mails de acesso (SMTP no Supabase, com senha de app; limite de 30 envios/hora) | Supabase > Authentication > Emails > SMTP Settings; modelos em português em `supabase/emails/` |
| brapi.dev | Cotações da bolsa (plano gratuito: 15 mil chamadas/mês, 3 meses de histórico, ~30 min de atraso) | Variável secreta `BRAPI_TOKEN` no Netlify; as respostas ficam 5 min no CDN e são compartilhadas entre visitantes |
| Banco Central | Selic, CDI, inflação, dólar oficial | Sem chave |
| AwesomeAPI | Dólar comercial | Sem chave |
| Finsiders Brasil | Manchetes | Sem chave |

## Identidade visual

Paleta "terra e broto", sempre no tema escuro (em qualquer aparelho, mesmo no modo claro):

| Uso | Cor |
|---|---|
| Verde principal (cartão de resultado, botões) | `#24452c` |
| Juros (folha) | `#6cc07a` |
| O que você plantou (terra) | `#c49a6c` |
| Poder de compra (sol) | `#eab54a` |
| Alerta | `#e37a62` |
| Fundo | `#171512` |
| Cartões | `#211e1a` |

Títulos em serifada do sistema (Iowan Old Style, Palatino, Georgia); textos na fonte do sistema. Nenhuma fonte é baixada, para o app ficar leve.

## Auditoria

```bash
python auditar.py .
```

Relata, sem editar nada, problemas de contraste (WCAG AA, temas claro e escuro), meta tags, compatibilidade com iPhone, segredos, Git e acessibilidade.

## Pendências

- Registrar um domínio próprio (ex.: `sementeapp.com.br`) e trocar o envio de e-mails do Gmail para um serviço transacional com esse domínio.
- Revisão jurídica da política de privacidade.
- Teste em aparelhos reais (Android e iPhone) e empacotamento para as lojas.

## Responsável

Desenvolvido por Ravena Leite. Contato: desenvolvedoraravena@proton.me
