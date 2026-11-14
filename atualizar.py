#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
atualizar.py — monta a lista IPTV SUPER COMPLETA.

Base ("mãe"): catálogo SAIMO TV (canais-saimo.pages.dev) — canais pagos/fechados + testados.
Complemento: iptv-org BR, iptv-com BR, Free-TV BR, Ramys Iptv-Brasil (Canais.m3u8/CanaisBR03/CanaisIPTV).

Regras do dono:
  - SÓ canais brasileiros (ou feeds dublados/legendados do Brasil).
  - Nenhum canal gringo, EXCETO notícias internacionais famosas
    (CNN/ABC/CBS/CNBC dos EUA, BBC/Sky do Reino Unido, RTP/SIC de Portugal,
     France 24/TV5Monde da França, DW da Alemanha, Al Jazeera, NHK, CGTN...).
  - Gringos vão em arquivos SEPARADOS, um por país, na pasta INTERNACIONAIS.
  - Brasileiros organizados por seção, um .m3u por seção, na pasta BRASIL.
  - LISTA_COMPLETA.m3u junta tudo (grupos "BR · X" e "INT · País").

Uso: duplo clique em ATUALIZAR.bat (ou: python atualizar.py).
"""
import concurrent.futures
import datetime
import json
import os
import re
import sys
import urllib.request

AQUI = os.path.dirname(os.path.abspath(__file__))
BRASIL = os.path.join(AQUI, "BRASIL")
INTER = os.path.join(AQUI, "INTERNACIONAIS")
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"

CATALOGO = "https://canais-saimo.pages.dev/catalogo.txt"
IPTVORG_CC = "https://iptv-org.github.io/iptv/countries/{cc}.m3u"
FREETV_BR = "https://raw.githubusercontent.com/Free-TV/IPTV/master/playlists/playlist_brazil.m3u8"
IPTVCOM_BR = "https://raw.githubusercontent.com/iptv-com/iptv/main/lists/brazil.m3u"

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# ----------------------------------------------------------------------
def norm(s):
    return " ".join((s or "").split()).casefold()

def get(url, timeout=60):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")

def limpar_nome(s):
    s = re.sub(r"\s*[\(\[](480p|576p|540p|288p|720p|1080p|360p|576i|1080i|2160p|Full ?HD|Ultra ?HD|HD|SD|Not 24/7|Geo-blocked|Offline)[\)\]]\s*$", "", s, flags=re.I)
    s = re.sub(r"\s+(FHD|HD|SD|UHD|4K|H\.264|H\.265|HEVC)+\s*[¹²³⁴]*$", "", s, flags=re.I)
    return s.strip()

def parse_m3u(txt):
    out, cur = [], None
    for line in txt.splitlines():
        line = line.rstrip()
        if line.startswith("#EXTM3U"):
            continue
        if line.startswith("#EXTINF"):
            cur = {
                "nome": limpar_nome(line.rsplit(",", 1)[-1].strip() if "," in line else ""),
                "tvg_id": re.search(r'tvg-id="([^"]*)"', line),
                "tvg_logo": re.search(r'tvg-logo="([^"]*)"', line),
                "group": re.search(r'group-title="([^"]*)"', line),
            }
            cur["tvg_id"] = cur["tvg_id"].group(1) if cur["tvg_id"] else None
            cur["tvg_logo"] = cur["tvg_logo"].group(1) if cur["tvg_logo"] else None
            cur["group"] = cur["group"].group(1) if cur["group"] else None
        elif line and not line.startswith("#") and cur:
            cur["url"] = line.strip()
            if cur.get("nome"):
                out.append(cur)
            cur = None
    return out

def parse_saimo(txt):
    canais, cur = [], None
    for raw in txt.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            continue
        k, _, v = line.partition(":")
        k, v = k.strip(), v.strip()
        if k == "canal":
            cur = {"nome": v, "categoria": None, "logo": None, "fontes": []}
            canais.append(cur)
        elif cur is None:
            continue
        elif k == "categoria":
            cur["categoria"] = v
        elif k == "logo":
            cur["logo"] = v
        elif k == "fonte":
            cur["fontes"].append({"url": v, "qualidade": None, "referer": None, "agente": None})
        elif k == "qualidade" and cur["fontes"]:
            cur["fontes"][-1]["qualidade"] = v
        elif k == "referer" and cur["fontes"]:
            cur["fontes"][-1]["referer"] = v
        elif k == "agente" and cur["fontes"]:
            cur["fontes"][-1]["agente"] = v
    return canais

def parece_video(b):
    if len(b) < 100:
        return False
    if b[0] == 0x47 or (len(b) > 4 and b[4] == 0x47):
        return True
    if b"ftyp" in b[:16] or b[4:8] == b"ftyp":
        return True
    if b[:3] == b"ID3" or b[:2] in (b"\xff\xfb", b"\xff\xf1"):
        return True
    return b[:4] == b"OggS"

def resolver(url, alvo):
    if alvo.startswith("http"):
        return alvo
    if alvo.startswith("//"):
        return "https:" + alvo
    if alvo.startswith("/"):
        from urllib.parse import urlparse
        p = urlparse(url)
        return p.scheme + "://" + p.netloc + alvo
    return url.rsplit("/", 1)[0] + "/" + alvo

def testar_fonte(f, timeout=7):
    """Teste profundo: a playlist precisa entregar um segmento de video de verdade."""
    h = {"User-Agent": f.get("agente") or UA}
    if f.get("referer"):
        h["Referer"] = f["referer"]
    try:
        url = f["url"]
        if re.search(r"\.(ts|mp4|m4v|mkv|ogg|mp3|aac)(\?|$)", url, re.I):
            r = urllib.request.urlopen(urllib.request.Request(url, headers={**h, "Range": "bytes=0-3000"}), timeout=timeout)
            return r.status in (200, 206) and parece_video(r.read(3000))
        r = urllib.request.urlopen(urllib.request.Request(url, headers=h), timeout=timeout)
        b = r.read(60000)
        if r.status != 200 or not b.startswith(b"#EXTM3U"):
            return False
        atual = url
        for _ in range(3):
            alvos = [l.strip() for l in b.decode("utf-8", "replace").splitlines() if l and not l.startswith("#")]
            if not alvos:
                return False
            prox = resolver(atual, alvos[0])
            r2 = urllib.request.urlopen(urllib.request.Request(prox, headers={**h, "Range": "bytes=0-3000"}), timeout=timeout)
            b2 = r2.read(3000)
            if r2.status not in (200, 206):
                return False
            if b2.startswith(b"#EXTM3U"):
                atual, b = prox, b2
                continue
            return parece_video(b2)
        return False
    except Exception:
        return False

# ----------------------------------------------------------------------
# Seções brasileiras (arquivo, título)
SECOES = [
    ("01 - TV Aberta Nacional", "TV Aberta Nacional"),
    ("02 - TV Aberta Regional", "TV Aberta Regional"),
    ("03 - Notícias", "Notícias"),
    ("04 - Esportes", "Esportes"),
    ("05 - Filmes e Séries (dublados)", "Filmes e Séries (dublados)"),
    ("06 - Documentários (dublados)", "Documentários (dublados)"),
    ("07 - Infantil (dublado)", "Infantil (dublado)"),
    ("08 - Variedades", "Variedades"),
    ("09 - Músicas", "Músicas"),
    ("10 - Religiosos", "Religiosos"),
    ("11 - Educação e Cultura", "Educação e Cultura"),
    ("12 - Legislativo e Governo", "Legislativo e Governo"),
    ("13 - Agro e Rural", "Agro e Rural"),
    ("14 - Canais Locais", "Canais Locais"),
    ("15 - 24 Horas", "24 Horas"),
    ("16 - PPV e Eventos", "PPV e Eventos"),
    ("17 - Streamings e Plataformas", "Streamings e Plataformas"),
    ("18 - Shop e Outros", "Shop e Outros"),
]

SAIMO_CAT = {
    "Esportes": 3, "Filmes e Séries": 4, "Notícias": 2, "Documentários": 5,
    "Infantil": 6, "Variedades": 7, "Músicas": 8, "24 Horas": 14, "PPV": 15,
}

AFILIADAS = ["globo", "sbt", "record", "band", "rede amazônica", "intertv", "tv tem",
             "tv tribuna", "tv vanguarda", "tv integração", "tv morena", "tv liberal",
             "tv mirante", "tv fronteira", "tv anhang", "tv catarinense", "tv bahia",
             "tv verdes mares", "tv clube", "tv rio sul", "tv itapoan", "tv arapuan",
             "tv pampa", "tv atlântico", "tv brasil central", "tve"]
NACIONAIS = ["globo", "rede globo", "sbt", "record", "record tv", "band", "bandeirantes",
             "redetv!", "rede tv!", "tv cultura", "tv gazeta", "tv brasil", "cnt",
             "rede brasil", "canal brasil"]

def alias_norm(s):
    n = norm(s)
    for a, b in [("tv globo", "globo"), ("rede globo", "globo"), ("rede record", "record"),
                 ("record tv", "record"), ("tv record", "record"), ("rede bandeirantes", "band"),
                 ("bandeirantes", "band"), ("tv band", "band"), ("tv sbt", "sbt")]:
        if n.startswith(a + " "):
            n = b + n[len(a):]
    return n

def parece_gringo(nome):
    n = norm(nome)
    if re.match(r"^(es|pt|fr|it|us|uk|mx|ar|cl|co|pe|de|uy|ve|do)\s*[:\-|] ", n):
        return True
    if re.search(r"\((france|usa|uk|spain|españa|italia|italy|mexico|argentina|chile|peru|colombia|portugal|germany|russia|canada)\)", n):
        return True
    return False

def chave(s):
    n = alias_norm(s)
    n = re.sub(r"\b(fhd|hd|sd|uhd|4k|h\.264|h\.265|hevc)\b", " ", n, flags=re.I)
    n = re.sub(r"[¹²³⁴]", "", n)
    return "".join(n.split())

RE = {
    "religioso": re.compile(r"aparecida|canação|cancao|gospel|evangelizar|pai eterno|igreja|deus|novo tempo|imaculada|adventista|shalom|século 21|seculo 21|apostólica|apostolica|missionária|missionaria|oração|oracao|católica|catolica|cristã|crista|jesus|igreja universal|mundial da|evangeli", re.I),
    "legislativo": re.compile(r"câmara|camara|senado|assembleia|assemblea|prefeitura|legislat|alesp|alerj|tvcamara", re.I),
    "noticia": re.compile(r"news|notícia|noticia|jornal|metrópoles|metropoles|money|mynews|uol", re.I),
    "esporte": re.compile(r"esporte|sport|premiere|combate|ufc|futebol|fifa|dazn|gol|race|moto|surf|fish tv|n sports|x sports|canal off|fox sports|band sports", re.I),
    "filme": re.compile(r"telecine|hbo|megapix|warner|tnt|space|cinemax|axn|sony channel|sony movies|tcm|universal tv|amc|studio universal|cinema|filme|prime box|star channel|\bfx\b|fox premium", re.I),
    "doc": re.compile(r"discovery|history|nat geo|national geographic|animal planet|curta|investigação|investigacao|science|planet", re.I),
    "infantil": re.compile(r"kids|infantil|criança|crianca|gloob|cartoon|nickelodeon|tooncast|rá tim bum|ra tim bum|senninha|zoomo|baby|boomerang|disney channel|disney jr", re.I),
    "musica": re.compile(r"música|musica|sertanejo|pagode|funk|trace|top tv|\bmtv\b|play hit", re.I),
    "educa": re.compile(r"escola|universit|educa|futura|sesc|univesp|senac|senai", re.I),
    "agro": re.compile(r"agro|rural|campo|cana?l do boi|terra viva|cultiva", re.I),
    "shop": re.compile(r"polishop|shopping|compras", re.I),
}

GRUPO_IPTVORG = {
    "News": 2, "Sports": 3, "Movies": 4, "Documentary": 5, "Kids": 6,
    "Entertainment": 7, "Music": 8, "Religious": 9, "Education": 10, "Culture": 10,
    "Legislative": 11, "Local": 13, "Shop": 17, "Comedy": 7, "Family": 7,
}

def classify_br(nome, saimo_cat=None, group=None):
    """Retorna índice da seção em SECOES."""
    n = norm(nome)
    if saimo_cat in SAIMO_CAT:
        if saimo_cat == "TV Aberta":
            return 1 if (n not in NACIONAIS and any(n.startswith(p) for p in AFILIADAS)) else 0
        if saimo_cat in ("Eventos / Streamings",):
            return 16
        return SAIMO_CAT[saimo_cat]
    if n in NACIONAIS:
        return 0
    if RE["noticia"].search(n):
        return 2
    if RE["esporte"].search(n):
        return 3
    if RE["filme"].search(n):
        return 4
    if RE["doc"].search(n):
        return 5
    if RE["infantil"].search(n):
        return 6
    if RE["religioso"].search(n):
        return 9
    if RE["musica"].search(n):
        return 8
    if n.startswith("pluto"):
        return 14
    if any(n.startswith(p) for p in AFILIADAS):
        return 1
    if RE["legislativo"].search(n):
        return 11
    if RE["educa"].search(n):
        return 10
    if RE["agro"].search(n):
        return 12
    if RE["shop"].search(n):
        return 17
    g = (group or "").lower()
    if g in ("radio",):
        return -1
    if g.startswith("canais:"):
        g2 = g.split(":", 1)[1]
        for kw, idx in [("filme", 4), ("esporte", 3), ("infantil", 6), ("document", 5),
                        ("notícia", 2), ("noticia", 2), ("variedade", 7), ("música", 8),
                        ("musica", 8), ("religio", 9), ("aberta", 0), ("rural", 12),
                        ("agro", 12), ("shop", 17)]:
            if kw in g2:
                return idx
        return 17
    if group in GRUPO_IPTVORG:
        return GRUPO_IPTVORG[group]
    if g == "general":
        return 0
    return 17

# ----------------------------------------------------------------------
# Notícias internacionais famosas (por país)
PAISES = [
    ("Estados Unidos", [r"^cnn\b", r"^abc news$", r"abc news live", r"^cbs news$", r"cbs news 24/7", r"nbc news now", r"^bloomberg\b", r"^cnbc\b", r"^fox news\b"], [r"español", r"espanol", r"brasil", r"chile", r"radio", r"mongolia", r"indonesia", r"^cnbc uk", r"cnn international (latin|north america|south asia)"]),
    ("Reino Unido", [r"^bbc news$", r"bbc news uk", r"bbc world news", r"^sky news$"], [r"radio"]),
    ("Portugal", [r"rtp 3", r"rtp internacional", r"sic notícias", r"sic noticias", r"euronews portug"], []),
    ("França", [r"^france 24", r"franceinfo", r"bfm tv", r"^lci$", r"tv5monde", r"euronews french"], [r"radio"]),
    ("Alemanha", [r"^dw english$", r"^dw news$", r"^deutsche welle$", r"tagesschau24", r"euronews german"], [r"arabic", r"espanol", r"russian", r"radio"]),
    ("Espanha", [r"^24 horas$", r"rtve", r"euronews spanish", r"euronews espanol"], [r"canarias", r"catalunya", r"radio"]),
    ("Global", [r"^euronews$"], []),
    ("Catar", [r"al jazeera english", r"aljazeera english"], []),
    ("Japão", [r"nhk world"], []),
    ("China", [r"^cgtn$"], []),
    ("Singapura", [r"^cna$", r"cna international", r"channel newsasia"], [r"albania"]),
    ("Coreia do Sul", [r"^arirang\b"], [r"un$", r"radio"]),
    ("Turquia", [r"trt world"], []),
    ("Itália", [r"rai news"], [r"radio"]),
    ("Rússia", [r"^rt$", r"russia today", r"^rt news"], []),
]

# ----------------------------------------------------------------------
def main():
    t0 = datetime.datetime.now()
    os.makedirs(BRASIL, exist_ok=True)
    os.makedirs(INTER, exist_ok=True)

    print("=== Colhendo fontes BR ===")
    saimo = parse_saimo(get(CATALOGO))
    print("SAIMO:", len(saimo), "canais")

    iptvorg = parse_m3u(get(IPTVORG_CC.format(cc="br"), timeout=120))
    print("iptv-org br.m3u:", len(iptvorg), "canais")

    iptvcom, freetv = [], []
    try:
        iptvcom = parse_m3u(get(IPTVCOM_BR))
        print("iptv-com brazil.m3u:", len(iptvcom), "canais")
    except Exception as e:
        print("iptv-com: ERRO", str(e)[:60])
    try:
        freetv = parse_m3u(get(FREETV_BR))
        print("Free-TV brazil:", len(freetv), "canais")
    except Exception as e:
        print("Free-TV: ERRO", str(e)[:60])

    ramys = []
    try:
        repo = json.loads(get("https://api.github.com/repos/Ramys/Iptv-Brasil-2026"))
        branch = repo.get("default_branch", "main")
        base = "https://raw.githubusercontent.com/Ramys/Iptv-Brasil-2026/%s/" % branch
        for f in ["Canais.m3u8", "CanaisBR03.m3u8"]:
            try:
                t = get(base + f, timeout=120)
                antes = len(ramys)
                for e in parse_m3u(t):
                    if re.search(r"\.(mkv|mp4|avi)$", e["url"], re.I):
                        continue
                    ramys.append(e)
                print("Ramys %s: +%d canais" % (f, len(ramys) - antes))
            except Exception as e:
                print("Ramys %s: ERRO %s" % (f, str(e)[:50]))
    except Exception as e:
        print("Ramys repo: ERRO", str(e)[:60])
    print("Ramys total:", len(ramys), "canais")

    mortos_anteriores = set()
    try:
        for line in open(os.path.join(AQUI, "fora-do-ar.txt"), encoding="utf-8"):
            parts = line.rstrip("\n").split("\t")
            if len(parts) >= 2 and parts[1].startswith("http"):
                mortos_anteriores.add(parts[1])
    except Exception:
        pass

    # ---- montar candidatos BR (todas as fontes) ----
    print("\n=== Montando candidatos BR ===")
    itens = []
    for c in saimo:
        if parece_gringo(c["nome"]):
            continue
        itens.append({"nome": c["nome"], "logo": c["logo"],
                      "sec": classify_br(c["nome"], c["categoria"]),
                      "tvg_id": None, "origem": "saimo",
                      "fontes": [x for x in c["fontes"] if x["url"]]})
    for origem, lista in [("iptv-com", iptvcom), ("freetv", freetv), ("iptv-org", iptvorg), ("ramys", ramys)]:
        for e in lista:
            if parece_gringo(e["nome"]) or not e["url"]:
                continue
            itens.append({"nome": e["nome"], "logo": e["tvg_logo"],
                          "sec": classify_br(e["nome"], None, e["group"]),
                          "tvg_id": e["tvg_id"], "origem": origem,
                          "fontes": [{"url": e["url"], "referer": None, "agente": None}]})

    seen_chave, unicos = set(), []
    for it in itens:
        k = chave(it["nome"])
        if k in seen_chave or it["sec"] < 0:
            continue
        seen_chave.add(k)
        unicos.append(it)
    print("candidatos unicos:", len(unicos))

    # ---- testar sinal de TODOS (profundo: playlist -> segmento de video) ----
    print("\n=== Testando sinal (video real) de %d canais ===" % len(unicos))
    def escanear(item):
        for f in item["fontes"]:
            if testar_fonte(f):
                return item, f
        return item, None

    with concurrent.futures.ThreadPoolExecutor(max_workers=24) as ex:
        res = list(ex.map(escanear, unicos))

    br, mortos, suspeitos, seen_url = [], [], [], set()
    for it, fonte in res:
        if fonte is None:
            url0 = it["fontes"][0]["url"] if it["fontes"] else ""
            if url0 and url0 in mortos_anteriores:
                mortos.append((it["nome"], url0, it["origem"]))
                continue
            suspeitos.append((it["nome"], url0, it["origem"]))
            fonte = it["fontes"][0] if it["fontes"] else None
        if fonte is None or fonte["url"] in seen_url:
            continue
        seen_url.add(fonte["url"])
        br.append({"nome": it["nome"], "url": fonte["url"], "logo": it["logo"], "sec": it["sec"],
                   "tvg_id": it["tvg_id"], "referer": fonte.get("referer"),
                   "agente": fonte.get("agente"), "origem": it["origem"]})
    print("BR testados: %d com video / %d confirmados mortos removidos / %d suspeitos (sai se falhar de novo)" % (len(br), len(mortos), len(suspeitos)))

    # ---- gringos ----
    print("\n=== Notícias internacionais ===")
    def familia(n):
        s = re.sub(r"[（(][^）)]*[）)]", " ", norm(n))
        s = re.sub(r"\b(fhd|hd|sd|uhd|4k|h\.264|h\.265|hevc)\b", " ", s, flags=re.I)
        s = re.sub(r"\s+\d+$", "", s)
        return " ".join(s.split())

    try:
        news_global = parse_m3u(get("https://iptv-org.github.io/iptv/categories/news.m3u", timeout=120))
        print("notícias globais (iptv-org):", len(news_global), "canais")
    except Exception as e:
        news_global = []
        print("news.m3u ERRO:", str(e)[:60])

    inter = {}
    for pais, inclui, exclui in PAISES:
        escolhidos, vistos = [], set()
        for e in news_global:
            n = norm(e["nome"])
            if not n:
                continue
            if any(re.search(x, n) for x in exclui):
                continue
            if any(re.search(x, n) for x in inclui):
                fam = familia(n)
                if fam in vistos or e["url"] in seen_url:
                    continue
                vistos.add(fam)
                escolhidos.append(e)
        inter[pais] = escolhidos[:12]
        print("  %-16s %d canais %s" % (pais, len(escolhidos), [e["nome"] for e in escolhidos[:8]]))

    print("\nTestando sinal das noticias internacionais...")
    todos_g = [(pais, e) for pais, es in inter.items() for e in es]
    def tst_g(pe):
        return testar_fonte({"url": pe[1]["url"], "referer": None, "agente": None})
    with concurrent.futures.ThreadPoolExecutor(max_workers=16) as ex:
        ok_g = list(ex.map(tst_g, todos_g))
    for (pais, e), ok in zip(todos_g, ok_g):
        if not ok:
            if e["url"] in mortos_anteriores:
                inter[pais] = [x for x in inter[pais] if x["url"] != e["url"]]
                mortos.append((e["nome"], e["url"], "int-" + pais))
            else:
                suspeitos.append((e["nome"], e["url"], "int-" + pais))

    # Portugal: RTP 3 / RTP Internacional ficam na categoria General do país
    try:
        extras_pt = parse_m3u(get(IPTVORG_CC.format(cc="pt"), timeout=60))
        fams = [familia(x["nome"]) for x in inter.get("Portugal", [])]
        for e in extras_pt:
            n = norm(e["nome"])
            if re.search(r"rtp notícias|rtp noticias|rtp 3|rtp internacional", n) and e["url"] not in seen_url and familia(n) not in fams:
                inter["Portugal"].append(e)
                fams.append(familia(n))
        print("  Portugal +RTP: %d canais %s" % (len(inter["Portugal"]), [e["nome"] for e in inter["Portugal"]]))
    except Exception as e:
        print("  Portugal extra: ERRO", str(e)[:50])

    # ---- escrever arquivos ----
    print("\n=== Gravando arquivos ===")
    data = t0.strftime("%d/%m/%Y %H:%M")
    contagem = {}

    for arq, titulo in SECOES:
        itens = [b for b in br if SECOES[b["sec"]][0] == arq]
        if titulo == "TV Aberta Nacional":
            pref = ["Globo", "SBT", "Record", "Band", "RedeTV!", "TV Cultura", "TV Gazeta", "TV Brasil", "CNT"]
            itens.sort(key=lambda x: (pref.index(x["nome"]) if x["nome"] in pref else 99, norm(x["nome"])))
        else:
            itens.sort(key=lambda x: norm(x["nome"]))
        if not itens:
            continue
        contagem[titulo] = len(itens)
        linhas = ["#EXTM3U", "# " + titulo + " — " + str(len(itens)) + " canais — atualizado " + data]
        for b in itens:
            linhas.append('#EXTINF:-1 tvg-id="%s" tvg-name="%s" tvg-logo="%s" group-title="%s",%s' % (
                b["tvg_id"] or b["nome"], b["nome"].replace(chr(34), chr(39)), b["logo"] or "", titulo, b["nome"]))
            if b["referer"]:
                linhas.append("#EXTVLCOPT:http-referrer=" + b["referer"])
            if b["agente"]:
                linhas.append("#EXTVLCOPT:http-user-agent=" + b["agente"])
            linhas.append(b["url"])
        open(os.path.join(BRASIL, arq + ".m3u"), "w", encoding="utf-8", newline="\n").write("\n".join(linhas) + "\n")

    for pais, entradas in inter.items():
        if not entradas:
            continue
        contagem["INT · " + pais] = len(entradas)
        linhas = ["#EXTM3U", "# Notícias — " + pais + " — atualizado " + data]
        for e in sorted(entradas, key=lambda x: norm(x["nome"])):
            linhas.append('#EXTINF:-1 tvg-id="%s" tvg-name="%s" tvg-logo="%s" group-title="%s",%s' % (
                e["tvg_id"] or e["nome"], e["nome"].replace(chr(34), chr(39)), e["tvg_logo"] or "", "Notícias · " + pais, e["nome"]))
            linhas.append(e["url"])
        open(os.path.join(INTER, pais + ".m3u"), "w", encoding="utf-8", newline="\n").write("\n".join(linhas) + "\n")

    # ---- master ----
    linhas = ["#EXTM3U", "# IPTV COMPLETA — BR + notícias internacionais — atualizado " + data]
    for arq, titulo in SECOES:
        path = os.path.join(BRASIL, arq + ".m3u")
        if os.path.exists(path):
            for line in open(path, encoding="utf-8").read().splitlines()[2:]:
                if line.startswith("#EXTINF"):
                    line = re.sub(r'group-title="[^"]*"', 'group-title="BR · %s"' % titulo, line)
                linhas.append(line)
    for pais, entradas in inter.items():
        path = os.path.join(INTER, pais + ".m3u")
        if os.path.exists(path):
            for line in open(path, encoding="utf-8").read().splitlines()[2:]:
                if line.startswith("#EXTINF"):
                    line = re.sub(r'group-title="[^"]*"', 'group-title="INT · %s"' % pais, line)
                linhas.append(line)
    open(os.path.join(AQUI, "LISTA_COMPLETA.m3u"), "w", encoding="utf-8", newline="\n").write("\n".join(linhas) + "\n")

    # ---- registro de canais sem sinal (2 passadas) ----
    with open(os.path.join(AQUI, "fora-do-ar.txt"), "w", encoding="utf-8") as fh:
        fh.write("Falharam em %s:\n\n" % data)
        fh.write("# CONFIRMADOS (falharam 2 rodadas seguidas -> REMOVIDOS)\n")
        for n, u, o in sorted(mortos, key=lambda x: norm(x[0])):
            fh.write("%s\t%s\t%s\n" % (n, u, o))
        fh.write("\n# SUSPEITOS (falharam 1 rodada -> mantidos; saem se falharem de novo)\n")
        for n, u, o in sorted(suspeitos, key=lambda x: norm(x[0])):
            fh.write("%s\t%s\t%s\n" % (n, u, o))

    # ---- relatório ----
    print("\n=== RELATÓRIO FINAL ===")
    total = 0
    for k, v in contagem.items():
        total += v
        print("  %-28s %d" % (k, v))
    print("  %-28s %d canais" % ("TOTAL", total))
    print("Arquivos em:", AQUI)
    print("Tempo:", (datetime.datetime.now() - t0).total_seconds().__round__(1), "s")

if __name__ == "__main__":
    main()
