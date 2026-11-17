#!/usr/bin/env python3
"""
Auditoria pré-entrega de site estático. Não edita nada: só relata.

Uso:
    python auditar.py [pasta-do-projeto]

Verifica contraste WCAG AA (temas claro e escuro, inclusive :hover), meta tags,
compatibilidade com iPhone, segredos, higiene de Git, estilos inline e !important,
cores fora das variáveis, semântica/acessibilidade, CDN sem integridade e sintaxe do JS.

Convenções:
  * Respeita o .gitignore: arquivo ignorado não vai para o cliente, logo não é auditado.
  * Se houver netlify.toml com "publish", as verificações de página valem só para essa pasta
    (é o que vai ao ar); a busca por segredos varre o projeto inteiro.
  * Comentários do CSS são removidos antes da análise.
  * Uma regra CSS com "--contraste: grafico;" (botão só com ícone) é cobrada em 3:1 (WCAG 1.4.11).
"""
import fnmatch
import html.parser
import os
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else ".")
achados = {"critico": [], "importante": [], "percepcao": []}
ok = []


def add(nivel, texto):
    achados[nivel].append(texto)


def rel(p):
    return os.path.relpath(p, ROOT).replace("\\", "/")


# ---------------------------------------------------------------- arquivos
def carregar_gitignore():
    pad = [".git/", ".netlify/", "node_modules/", "__pycache__/"]
    gi = os.path.join(ROOT, ".gitignore")
    if os.path.exists(gi):
        for linha in open(gi, encoding="utf-8", errors="ignore"):
            linha = linha.strip()
            if linha and not linha.startswith("#"):
                pad.append(linha)
    return pad


IGNORAR = carregar_gitignore()


def ignorado(caminho_rel):
    partes = caminho_rel.split("/")
    for p in IGNORAR:
        alvo = p.rstrip("/")
        if p.endswith("/"):
            if alvo in partes[:-1] or any(fnmatch.fnmatch(x, alvo) for x in partes[:-1]):
                return True
        elif fnmatch.fnmatch(caminho_rel, alvo) or fnmatch.fnmatch(partes[-1], alvo):
            return True
    return False


def listar(base):
    for raiz, pastas, arquivos in os.walk(base):
        pastas[:] = [d for d in pastas if not ignorado(rel(os.path.join(raiz, d)) + "/x")]
        for a in arquivos:
            p = os.path.join(raiz, a)
            if not ignorado(rel(p)):
                yield p


def ler(p):
    return open(p, encoding="utf-8", errors="ignore").read()


TODOS = list(listar(ROOT))

# Pasta publicada (Netlify)
PUBLICA = ROOT
toml = os.path.join(ROOT, "netlify.toml")
if os.path.exists(toml):
    m = re.search(r'publish\s*=\s*"([^"]+)"', ler(toml))
    if m:
        PUBLICA = os.path.normpath(os.path.join(ROOT, m.group(1)))
PUB = [p for p in TODOS if os.path.abspath(p).startswith(PUBLICA + os.sep) or os.path.abspath(p) == PUBLICA]
HTMLS = [p for p in PUB if p.endswith(".html")]
JSS = [p for p in PUB if p.endswith((".js", ".mjs"))] + [p for p in TODOS if "netlify/functions/" in rel(p)]

# ---------------------------------------------------------------- CSS
def sem_comentarios(css):
    return re.sub(r"/\*.*?\*/", "", css, flags=re.S)


def parse_css(css):
    """Devolve [(contexto_de_media, seletor, {propriedade: valor})]."""
    regras, pilha, buf = [], [], ""
    for ch in css:
        if ch == "{":
            pilha.append(buf.strip())
            buf = ""
        elif ch == "}":
            if not pilha:
                buf = ""
                continue
            prel = pilha.pop()
            if not prel.startswith("@") and not any(x.startswith("@keyframes") for x in pilha):
                decl = {}
                for d in buf.split(";"):
                    if ":" in d:
                        k, v = d.split(":", 1)
                        decl[k.strip().lower()] = v.strip()
                regras.append((" ".join(x for x in pilha if x.startswith("@")), prel, decl))
            buf = ""
        else:
            buf += ch
    return regras


NOMES = {"white": "#ffffff", "black": "#000000", "#fff": "#ffffff", "#000": "#000000"}


def resolver(valor, vars_, prof=0):
    if prof > 10 or valor is None:
        return valor
    def troca(m):
        nome, fb = m.group(1), m.group(2)
        v = vars_.get(nome)
        if v is None and fb is not None:
            v = fb.strip()
        return resolver(v, vars_, prof + 1) if v is not None else m.group(0)
    return re.sub(r"var\(\s*(--[\w-]+)\s*(?:,\s*([^)]*))?\)", troca, valor)


def cor(valor):
    """Converte para (r, g, b) se for cor sólida; None se transparente, gradiente, mistura etc."""
    if not valor:
        return None
    v = valor.strip().lower()
    if any(x in v for x in ("gradient", "url(", "color-mix", "var(", "currentcolor", "transparent", "inherit", "none")):
        return None
    v = NOMES.get(v, v)
    m = re.search(r"#([0-9a-f]{3}|[0-9a-f]{6})\b", v)
    if m:
        h = m.group(1)
        if len(h) == 3:
            h = "".join(c * 2 for c in h)
        return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))
    m = re.search(r"rgba?\(\s*(\d+)[ ,]+(\d+)[ ,]+(\d+)(?:\s*[,/]\s*([\d.]+%?))?", v)
    if m:
        if m.group(4) and float(m.group(4).rstrip("%")) < (100 if m.group(4).endswith("%") else 1):
            return None  # semitransparente: depende do que está por baixo
        return tuple(int(m.group(i)) for i in (1, 2, 3))
    return NOMES.get(v.split()[0]) and cor(NOMES[v.split()[0]])


def lum(rgb):
    def lin(c):
        c /= 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (lin(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def razao(a, b):
    la, lb = sorted((lum(a), lum(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def px(valor):
    if not valor:
        return None
    m = re.search(r"clamp\(\s*([\d.]+)(px|rem|em)", valor)  # clamp: vale o mínimo
    m = m or re.search(r"([\d.]+)(px|rem|em)\b", valor)
    if not m:
        return None
    n = float(m.group(1))
    return n if m.group(2) == "px" else n * 16


def texto_grande(decl):
    tam = px(decl.get("font-size")) or px(decl.get("font"))
    peso = decl.get("font-weight", "") + " " + decl.get("font", "")
    negrito = re.search(r"\b(bold|[7-9]00)\b", peso) is not None
    return tam is not None and (tam >= 24 or (negrito and tam >= 18.66))


def fundo(decl):
    return decl.get("background-color") or decl.get("background")


def auditar_css(css, origem):
    css = sem_comentarios(css)
    regras = parse_css(css)
    claro, escuro = {}, {}
    for media, sel, decl in regras:
        if sel.strip() == ":root" and "prefers-color-scheme: dark" not in media:
            claro.update({k: v for k, v in decl.items() if k.startswith("--")})
    escuro.update(claro)
    for media, sel, decl in regras:
        if ":root" in sel and "prefers-color-scheme: dark" in media and "not(" not in sel:
            escuro.update({k: v for k, v in decl.items() if k.startswith("--")})

    falhas = []
    for nome_tema, vars_, tema in (("claro", claro, "light"), ("escuro", escuro, "dark")):
        # mapa de fundos por seletor, para herdar o fundo do ancestral citado no próprio seletor
        fundos = {}
        for media, sel, decl in regras:
            if "prefers-color-scheme" in media and tema not in media:
                continue
            f = cor(resolver(fundo(decl), vars_))
            if f:
                for s in sel.split(","):
                    fundos[s.strip()] = f
        base = fundos.get("body") or (255, 255, 255)
        for media, sel, decl in regras:
            if "prefers-color-scheme" in media and tema not in media:
                continue
            if "color" not in decl or ":root" in sel:
                continue
            fg = cor(resolver(decl["color"], vars_))
            if not fg:
                continue
            for s in sel.split(","):
                s = s.strip()
                bg = cor(resolver(fundo(decl), vars_))
                origem_bg = "própria regra"
                if not bg:
                    partes = re.split(r"\s*[>+~ ]\s*", s)
                    for anc in reversed(partes[:-1]):
                        anc_sem_estado = re.sub(r":(hover|focus|focus-visible|active)\b", "", anc)
                        if anc in fundos or anc_sem_estado in fundos:
                            bg = fundos.get(anc) or fundos.get(anc_sem_estado)
                            origem_bg = f"fundo de {anc}"
                            break
                if not bg:
                    bg, origem_bg = base, "fundo da página (suposto)"
                r = razao(fg, bg)
                grafico = decl.get("--contraste", "").strip() == "grafico"
                minimo = 3.0 if (grafico or texto_grande(decl)) else 4.5
                if r + 1e-9 < minimo:
                    falhas.append((r, minimo, nome_tema, s, origem_bg))
    vistos = set()
    for r, minimo, tema, s, ob in sorted(falhas):
        chave = (tema, s)
        if chave in vistos:
            continue
        vistos.add(chave)
        suposto = "suposto" in ob
        # Sem o fundo citado no próprio seletor, o script não sabe o que está por trás do texto:
        # o achado vira "a confirmar" e nunca sobe para crítico (o fundo real pode ser outro).
        nivel = "importante" if suposto else ("critico" if (r < 3 and minimo == 4.5) else "importante")
        nota = " (fundo suposto: confirmar no navegador)" if suposto else ""
        add(nivel, f"Contraste {r:.2f}:1 (mínimo {minimo:g}:1) no tema {tema}: `{s}` sobre {ob}{nota} [{origem}]")
    if not falhas:
        ok.append(f"Contraste: nenhuma combinação reprovada em {origem}")

    # iPhone
    if "backdrop-filter" in css and "-webkit-backdrop-filter" not in css:
        add("importante", f"`backdrop-filter` sem `-webkit-backdrop-filter`: o desfoque não acontece no Safari [{origem}]")
    if "-webkit-tap-highlight-color" not in css:
        add("percepcao", f"`-webkit-tap-highlight-color` não zerado: retângulo cinza ao tocar nos botões no iPhone [{origem}]")
    if re.search(r"(?<![\w-])100vh", css):
        add("importante", f"`100vh` em uso: no iPhone a barra do Safari corta o conteúdo; prefira `100dvh` [{origem}]")

    # !important e cores fora das variáveis
    imp = len(re.findall(r"!important", css))
    if imp:
        add("percepcao", f"{imp} uso(s) de `!important` [{origem}]")
    soltas = []
    for media, sel, decl in regras:
        if ":root" in sel:
            continue
        for k, v in decl.items():
            if k.startswith("--"):
                continue
            for c in re.findall(r"#[0-9a-fA-F]{3,8}\b|rgba?\([^)]*\)", v):
                if not re.match(r"rgba?\(\s*(0\s*,\s*0\s*,\s*0|255\s*,\s*255\s*,\s*255)\b", c):
                    soltas.append(f"{sel.strip()[:40]} {k}: {c}")
    if soltas:
        add("percepcao", f"{len(soltas)} cor(es) fora das variáveis do :root, ex.: " + "; ".join(soltas[:4]) + f" [{origem}]")
    return css


# ---------------------------------------------------------------- HTML
class Leitor(html.parser.HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tags, self.estilos, self.scripts, self.ids, self.ancoras = [], [], [], set(), []
        self.titulos, self.pilha, self.em_style, self.em_script, self.buf = [], [], False, False, ""
        self.nav_links, self.nav_aberto, self.main = [], 0, 0

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        self.tags.append((tag, a, self.getpos()[0]))
        if "id" in a:
            self.ids.add(a["id"])
        if tag == "style":
            self.em_style, self.buf = True, ""
        if tag == "script":
            self.em_script, self.buf = True, ""
        if tag == "nav":
            self.nav_aberto += 1
            self.nav_links.append(0)
        if tag in ("a", "button") and self.nav_aberto:
            self.nav_links[-1] += 1
        if tag == "main":
            self.main += 1
        if re.fullmatch(r"h[1-6]", tag):
            self.titulos.append((int(tag[1]), self.getpos()[0]))

    def handle_endtag(self, tag):
        if tag == "style" and self.em_style:
            self.estilos.append(self.buf)
            self.em_style = False
        if tag == "script" and self.em_script:
            self.scripts.append(self.buf)
            self.em_script = False
        if tag == "nav":
            self.nav_aberto -= 1

    def handle_data(self, d):
        if self.em_style or self.em_script:
            self.buf += d


def auditar_html(p):
    nome = rel(p)
    fonte = ler(p)
    L = Leitor()
    L.feed(fonte)
    metas = {}
    for tag, a, _ in L.tags:
        if tag == "meta":
            chave = a.get("name") or a.get("property")
            if chave:
                metas[chave.lower()] = a.get("content", "")
    links = [(a.get("rel", ""), a.get("href", "")) for tag, a, _ in L.tags if tag == "link"]

    principal = not any(t == "meta" and a.get("name") == "robots" and "noindex" in a.get("content", "") for t, a, _ in L.tags)
    html_tag = next((a for t, a, _ in L.tags if t == "html"), {})
    if not html_tag.get("lang"):
        add("importante", f"`<html>` sem `lang` [{nome}]")
    faltam = [m for m in ("description", "og:title", "og:description", "og:image", "og:url", "twitter:card", "theme-color") if m not in metas]
    if not any("canonical" in r for r, _ in links):
        faltam.append("canonical")
    if faltam and principal:
        nivel = "importante" if "og:image" in faltam else "percepcao"
        add(nivel, f"Meta tags ausentes: {', '.join(faltam)}. Sem og:image o link chega sem pré-visualização no WhatsApp e no LinkedIn [{nome}]")
    if not any("apple-touch-icon" in r for r, _ in links):
        add("percepcao", f"Sem `apple-touch-icon`: ícone genérico ao salvar na tela de início do iPhone [{nome}]")

    # semântica
    h1 = [l for n, l in L.titulos if n == 1]
    if len(h1) > 1:
        add("importante", f"{len(h1)} elementos `<h1>` (linhas {h1}) [{nome}]")
    ant = 0
    for n, l in L.titulos:
        if ant and n > ant + 1:
            add("percepcao", f"Hierarquia de títulos pula de h{ant} para h{n} (linha {l}) [{nome}]")
        ant = n
    if not L.main and len(L.titulos) > 2:
        add("importante", f"Sem `<main>` [{nome}]")
    for i, qtd in enumerate(L.nav_links):
        if qtd == 0:
            add("importante", f"`<nav>` sem nenhum link ou botão [{nome}]")
    inline = 0
    for tag, a, linha in L.tags:
        if tag == "img" and "alt" not in a:
            add("importante", f"`<img>` sem `alt` (linha {linha}) [{nome}]")
        if a.get("role") == "button" and "tabindex" not in a and tag not in ("button", "a"):
            add("importante", f"`role=\"button\"` sem `tabindex` (linha {linha}) [{nome}]")
        if a.get("aria-hidden") == "true" and tag in ("a", "button", "input", "select", "textarea"):
            add("critico", f"Elemento interativo com `aria-hidden` (linha {linha}) [{nome}]")
        if a.get("target") == "_blank" and "noopener" not in a.get("rel", ""):
            add("importante", f"`target=\"_blank\"` sem `rel=\"noopener\"` (linha {linha}) [{nome}]")
        href = a.get("href", "")
        if tag == "a" and href.startswith("#") and len(href) > 1 and href[1:] not in L.ids:
            add("importante", f"Âncora `{href}` aponta para id inexistente (linha {linha}) [{nome}]")
        if "style" in a and tag not in ("div",) or ("style" in a and tag == "div"):
            inline += 1
        if tag == "script" and a.get("src", "").startswith("http") and "integrity" not in a:
            add("importante", f"Script de CDN sem `integrity`: {a['src']} (linha {linha}) [{nome}]")
        if tag in ("img", "script") and a.get("src") and not a["src"].startswith(("http", "data:", "{{")):
            alvo = os.path.normpath(os.path.join(os.path.dirname(p), a["src"].split("?")[0].lstrip("/")))
            if a["src"].startswith("/"):
                alvo = os.path.normpath(os.path.join(PUBLICA, a["src"].lstrip("/")))
            if not os.path.exists(alvo):
                add("critico", f"Arquivo referenciado não existe: {a['src']} (linha {linha}) [{nome}]")
    if inline:
        add("percepcao", f"{inline} elemento(s) com estilo inline (`style=`) [{nome}]")

    # CDN carregado dinamicamente pelo JavaScript
    for s in L.scripts:
        for url in re.findall(r"""['"](https://(?:cdn\.jsdelivr\.net|unpkg\.com|cdnjs\.cloudflare\.com)[^'"]+)['"]""", s):
            if "integrity" not in s:  # aceita script criado pelo JS com .integrity definido
                add("importante", f"Biblioteca de CDN carregada pelo JavaScript sem verificação de integridade: {url} [{nome}]")

    # classes usadas no HTML sem regra no CSS
    css = "\n".join(sem_comentarios(e) for e in L.estilos)
    for e in L.estilos:
        auditar_css(e, nome)
    usadas = set()
    for tag, a, _ in L.tags:
        usadas.update(a.get("class", "").split())
    js = "\n".join(L.scripts)
    sem_regra = sorted(c for c in usadas if not re.search(r"\." + re.escape(c) + r"(?![\w-])", css) and not re.search(r"['\"`.]" + re.escape(c) + r"['\"`\s]", js))
    if sem_regra and L.estilos:
        add("percepcao", f"Classes sem regra no CSS: {', '.join(sem_regra[:10])} [{nome}]")
    return L.scripts


# ---------------------------------------------------------------- JS
def checar_js(trechos):
    node = shutil.which("node")
    if not node:
        ok.append("Sintaxe JS: node não encontrado, verificação pulada")
        return
    erros = 0
    with tempfile.TemporaryDirectory() as tmp:
        for i, (origem, codigo, modulo) in enumerate(trechos):
            arq = os.path.join(tmp, f"t{i}.{'mjs' if modulo else 'js'}")
            open(arq, "w", encoding="utf-8").write(codigo)
            r = subprocess.run([node, "--check", arq], capture_output=True, text=True)
            if r.returncode:
                erros += 1
                linha = (r.stderr.strip().splitlines() or ["?"])[-1]
                add("critico", f"Erro de sintaxe JavaScript em {origem}: {linha}")
    if not erros:
        ok.append(f"Sintaxe JS: {len(trechos)} trecho(s) aprovados em `node --check`")


# ---------------------------------------------------------------- segredos e Git
PADROES = {
    "chave AWS": r"AKIA[0-9A-Z]{16}",
    "chave OpenAI/Anthropic": r"\bsk-(?:ant-)?[A-Za-z0-9_-]{20,}",
    "token GitHub": r"\bghp_[A-Za-z0-9]{30,}",
    "chave Google": r"\bAIza[0-9A-Za-z_-]{35}",
    "chave secreta Supabase": r"\bsb_secret_[A-Za-z0-9_-]{10,}",
    "JWT (possível service_role)": r"\beyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}",
    "senha em texto": r"""(?i)\b(password|senha)\s*[:=]\s*['"][^'"]{4,}['"]""",
}


def segredos():
    achou = False
    for p in TODOS:
        if p.endswith((".png", ".jpg", ".jpeg", ".webp", ".ico", ".pdf")) or p.endswith("auditar.py"):
            continue
        txt = ler(p)
        for nome, rx in PADROES.items():
            for m in re.finditer(rx, txt):
                if "service_role" in nome and "service_role" not in txt:
                    pass
                achou = True
                add("critico", f"Possível {nome} em {rel(p)}: `{m.group(0)[:12]}…`")
        if os.path.basename(p).startswith(".env"):
            achou = True
            add("critico", f"Arquivo de ambiente no projeto: {rel(p)}")
    if not achou:
        ok.append("Segredos: nenhuma chave secreta, token ou senha encontrada")
    if any("sb_publishable_" in ler(p) for p in PUB if p.endswith(".js")):
        ok.append("Chave do Supabase publicada é a pública (sb_publishable_), como deve ser")


def git():
    if not os.path.isdir(os.path.join(ROOT, ".git")):
        add("importante", "Projeto sem Git: não há histórico, ponto de volta nem como mostrar processo a um avaliador")
        return
    def g(*a):
        return subprocess.run(["git", "-C", ROOT, *a], capture_output=True, text=True).stdout
    if not os.path.exists(os.path.join(ROOT, ".gitignore")):
        add("importante", "Sem `.gitignore`")
    pend = [l for l in g("status", "--porcelain").splitlines() if l.strip()]
    if pend:
        add("percepcao", f"{len(pend)} alteração(ões) não commitada(s)")
    n = len(g("log", "--oneline").splitlines())
    if n <= 1:
        add("percepcao", f"Só {n} commit: o histórico não mostra processo")
    vagas = [l for l in g("log", "--format=%s").splitlines() if l.strip().lower() in ("fix", "update", "final", "wip", "ajustes", "teste")]
    if vagas:
        add("percepcao", f"{len(vagas)} mensagem(ns) de commit vagas, ex.: {vagas[0]!r}")


# ---------------------------------------------------------------- execução
def main():
    if PUBLICA != ROOT:
        ok.append(f"Só a pasta `{rel(PUBLICA)}` é publicada (netlify.toml); ferramentas de desenvolvimento ficam fora do ar")
    trechos = []
    for p in HTMLS:
        for i, s in enumerate(auditar_html(p)):
            if s.strip():
                trechos.append((f"{rel(p)} (script {i + 1})", s, False))
    for p in JSS:
        trechos.append((rel(p), ler(p), p.endswith(".mjs")))
    checar_js(trechos)
    segredos()
    git()

    titulos = {"critico": "🔴 CRÍTICO", "importante": "🟠 IMPORTANTE", "percepcao": "🟡 PERCEPÇÃO"}
    print(f"Auditoria de {ROOT}\nPáginas auditadas: {', '.join(rel(p) for p in HTMLS) or 'nenhuma'}\n")
    for k, t in titulos.items():
        print(f"{t} ({len(achados[k])})")
        for a in achados[k]:
            print(f"  - {a}")
        print()
    print("✅ OK")
    for o in ok:
        print(f"  - {o}")
    return 1 if achados["critico"] else 0


if __name__ == "__main__":
    sys.exit(main())
