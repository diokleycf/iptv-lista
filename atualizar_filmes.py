#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
atualizar_filmes.py — monta as listas de FILMES e SÉRIES (VOD) em português
(dublado ou legendado), a partir da lista Filmes-Series.m3u8 do Ramys
(~316 mil itens: filmes por gênero + séries por provedor).

Saída (pasta "FILMES E SERIES"):
  01 - FILMES - Dublados.m3u    todos os filmes dublados, agrupados por gênero
  02 - FILMES - Legendados.m3u  grupo "Filmes · Legendados"
  SERIES\\NN - Nome.m3u          um arquivo por provedor/grupo de séries

Uso: duplo clique em "ATUALIZAR FILMES.bat".
"""
import argparse
import concurrent.futures
import datetime
import json
import os
import re
import sys
import urllib.request

AQUI = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(AQUI, "FILMES E SERIES")
SERIES_DIR = os.path.join(OUT, "SERIES")
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

def norm(s):
    return " ".join((s or "").split()).casefold()

def chave_filme(s):
    n = re.sub(r"\(\d{4}\)", "", norm(s))          # tira (2020)
    n = re.sub(r"\[l\]", "", n)                     # marcador [L]
    return "".join(n.split())

# ordem e nomes dos grupos de FILMES (todos dublados, exceto Legendados)
FILMES_MAP = [
    ("FILMES | Lançamentos", "Filmes · Lançamentos"),
    ("FILMES | Nacionais", "Filmes · Nacionais"),
    ("FILMES | 4K UHD", "Filmes · 4K UHD"),
    ("FILMES | Ação", "Filmes · Ação"),
    ("FILMES | Aventura", "Filmes · Aventura"),
    ("FILMES | Animação", "Filmes · Animação"),
    ("FILMES | Comédia", "Filmes · Comédia"),
    ("FILMES | Crime", "Filmes · Crime"),
    ("FILMES | Drama", "Filmes · Drama"),
    ("FILMES | Dramas Curtos", "Filmes · Dramas Curtos"),
    ("FILMES | Família", "Filmes · Família"),
    ("FILMES | Fantasia", "Filmes · Fantasia"),
    ("FILMES | Faroeste", "Filmes · Faroeste"),
    ("FILMES | Ficcao", "Filmes · Ficção"),
    ("FILMES | Guerra", "Filmes · Guerra"),
    ("FILMES | Infantis", "Filmes · Infantis"),
    ("FILMES | Natalino", "Filmes · Natal"),
    ("FILMES | Religiosos", "Filmes · Religiosos"),
    ("FILMES | Romance", "Filmes · Romance"),
    ("FILMES | Suspense", "Filmes · Suspense"),
    ("FILMES | Terror", "Filmes · Terror"),
    ("FILMES | Oscar 2025", "Filmes · Oscar 2025"),
    ("FILMES | Oscar 2024", "Filmes · Oscar 2024"),
    ("Cinema", "Filmes · Cinema"),
]
LEGENDADO = "FILMES | Legendados"

# ordem e nomes dos grupos de SÉRIES
SERIES_MAP = [
    ("SÉRIES | NOVELAS", "Séries · Novelas"),
    ("SÉRIES | TURCAS", "Séries · Turcas"),
    ("SÉRIES | MEXICANAS", "Séries · Mexicanas"),
    ("SÉRIES | DORAMA", "Séries · Doramas"),
    ("SÉRIES | INDIANAS", "Séries · Indianas"),
    ("SÉRIES | PORTUGUESAS", "Séries · Portuguesas"),
    ("SÉRIES | NETFLIX", "Séries · Netflix"),
    ("SÉRIES | GLOBOPLAY", "Séries · Globoplay"),
    ("SÉRIES | AMAZON PRIME VIDEO", "Séries · Amazon Prime Video"),
    ("SÉRIES | DISNEY PLUS", "Séries · Disney+"),
    ("SÉRIES | MAX", "Séries · Max"),
    ("SÉRIES | PARAMOUNT", "Séries · Paramount+"),
    ("SÉRIES | APPLE TV PLUS", "Séries · Apple TV+"),
    ("SÉRIES | STAR PLUS", "Séries · Star+"),
    ("SÉRIES | DISCOVERY PLUS", "Séries · Discovery+"),
    ("SÉRIES | SBT", "Séries · SBT"),
    ("SÉRIES | PLUTOTV", "Séries · Pluto TV"),
    ("SÉRIES | CLARO VIDEO", "Séries · Claro Video"),
    ("SÉRIES | LIONSGATE", "Séries · Lionsgate+"),
    ("SÉRIES | AMC PLUS", "Séries · AMC+"),
    ("SÉRIES | DIRECTV", "Séries · DirecTV"),
    ("SÉRIES | CRUNCHYROLL", "Séries · Animes (Crunchyroll)"),
    ("SÉRIES | FUNIMATION NOW", "Séries · Animes (Funimation)"),
    ("SÉRIES | BRASIL PARALELO", "Séries · Brasil Paralelo"),
    ("SÉRIES | OUTRAS PRODUTORAS", "Séries · Outras Produtoras"),
]

def baixar_linhas(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    r = urllib.request.urlopen(req, timeout=300)
    for raw in r:
        yield raw.decode("utf-8", "replace").rstrip("\r\n")

def escrever(caminho, grupos, titulo, data):
    os.makedirs(os.path.dirname(caminho), exist_ok=True)
    out = ["#EXTM3U", "# %s — atualizado %s" % (titulo, data)]
    for nome_grupo, itens in grupos:
        out.append("")
        out.append("# ══════ %s (%d) ══════" % (nome_grupo, len(itens)))
        for nome, logo, url in itens:
            out.append('#EXTINF:-1 tvg-name="%s" tvg-logo="%s" group-title="%s",%s' % (nome.replace(chr(34), chr(39)), logo or "", nome_grupo, nome))
            out.append(url)
    open(caminho, "w", encoding="utf-8", newline="\n").write("\n".join(out) + "\n")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--testar", action="store_true", help="testa cada link VOD e remove os mortos")
    ap.add_argument("--workers", type=int, default=160)
    ap.add_argument("--timeout", type=int, default=5)
    ap.add_argument("--lote", type=int, default=20000)
    a = ap.parse_args()

    t0 = datetime.datetime.now()
    print("Descobrindo branch do repo Ramys...")
    repo = json.loads(urllib.request.urlopen(urllib.request.Request(
        "https://api.github.com/repos/Ramys/Iptv-Brasil-2026",
        headers={"User-Agent": UA}), timeout=60).read().decode("utf-8"))
    url = "https://raw.githubusercontent.com/Ramys/Iptv-Brasil-2026/%s/Filmes-Series.m3u8" % repo["default_branch"]

    print("Baixando Filmes-Series.m3u8 (~90MB)...")
    grupos = {}
    cur = None
    for line in baixar_linhas(url):
        if line.startswith("#EXTINF"):
            cur = {
                "nome": line.rsplit(",", 1)[-1].strip(),
                "logo": re.search(r'tvg-logo="([^"]*)"', line),
                "grupo": re.search(r'group-title="([^"]*)"', line),
            }
            cur["logo"] = cur["logo"].group(1) if cur["logo"] else None
            cur["grupo"] = cur["grupo"].group(1) if cur["grupo"] else "?"
        elif line and not line.startswith("#") and cur:
            grupos.setdefault(cur["grupo"], []).append((cur["nome"], cur["logo"], line.strip()))
            cur = None

    data = t0.strftime("%d/%m/%Y %H:%M")
    total = sum(len(v) for v in grupos.values())
    print("Total de itens baixados:", total, "| grupos:", len(grupos))

    if a.testar:
        print("Testando links VOD (%d workers, timeout %ds)... isso leva um tempo." % (a.workers, a.timeout))
        todos = [(g, nome, logo, u) for g, lst in grupos.items() for nome, logo, u in lst]
        def vivo(item):
            url = item[3]
            try:
                req = urllib.request.Request(url, headers={"User-Agent": UA, "Range": "bytes=0-3"})
                r = urllib.request.urlopen(req, timeout=a.timeout)
                b = r.read(4)
                if r.status in (200, 206) and b:
                    return True
            except Exception:
                pass
            try:
                req = urllib.request.Request(url, headers={"User-Agent": UA})
                r = urllib.request.urlopen(req, timeout=a.timeout)
                b = r.read(4)
                return r.status == 200 and bool(b)
            except Exception:
                return False
        ok_map = {}
        for ini in range(0, len(todos), a.lote):
            lote = todos[ini:ini + a.lote]
            with concurrent.futures.ThreadPoolExecutor(max_workers=a.workers) as ex:
                res = list(ex.map(vivo, lote))
            for item, bom in zip(lote, res):
                ok_map[item[3]] = bom
            print("  %d/%d testados... (%d vivos)" % (min(ini + a.lote, len(todos)), len(todos), sum(ok_map.values())))
        novos, removidos = {}, 0
        for g, nome, logo, u in todos:
            if ok_map.get(u):
                novos.setdefault(g, []).append((nome, logo, u))
            else:
                removidos += 1
        grupos = novos
        total = sum(len(v) for v in grupos.values())
        print("VOD: %d vivos / %d mortos removidos" % (total, removidos))

    # ---------- FILMES ----------
    filmes_dub, filmes_leg = [], []
    seen_dub, seen_leg = set(), set()
    for orig, novo in FILMES_MAP:
        itens, vistos = [], set()
        for nome, logo, u in grupos.get(orig, []):
            k = chave_filme(nome)
            if k in seen_dub or k in vistos:
                continue
            vistos.add(k)
            seen_dub.add(k)
            itens.append((nome, logo, u))
        itens.sort(key=lambda x: norm(x[0]))
        if itens:
            filmes_dub.append((novo, itens))
    for nome, logo, u in grupos.get(LEGENDADO, []):
        k = chave_filme(nome)
        if k in seen_leg:
            continue
        seen_leg.add(k)
        filmes_leg.append((nome, logo, u))
    filmes_leg.sort(key=lambda x: norm(x[0]))
    escrever(os.path.join(OUT, "01 - FILMES - Dublados.m3u"), filmes_dub,
             "FILMES DUBLADOS (PT)", data)
    escrever(os.path.join(OUT, "02 - FILMES - Legendados.m3u"),
             [("Filmes · Legendados", filmes_leg)] if filmes_leg else [],
             "FILMES LEGENDADOS (PT)", data)
    print("\nFILMES dublados: %d | legendados: %d" % (len(seen_dub), len(seen_leg)))

    # ---------- SÉRIES ----------
    seen_url = set()
    total_series = 0
    for i, (orig, novo) in enumerate(SERIES_MAP, 1):
        itens, vistos = [], set()
        for nome, logo, u in grupos.get(orig, []):
            if u in seen_url:
                continue
            k = norm(nome)
            if k in vistos:
                continue
            vistos.add(k)
            seen_url.add(u)
            itens.append((nome, logo, u))
        if not itens:
            continue
        itens.sort(key=lambda x: norm(x[0]))
        arq = "%02d - %s.m3u" % (i, novo.replace(" · ", " - ").replace(":", ""))
        escrever(os.path.join(SERIES_DIR, arq), [(novo, itens)], "SÉRIES — " + novo, data)
        total_series += len(itens)
    print("SÉRIES: %d episódios em %d arquivos" % (total_series, len(SERIES_MAP)))
    print("\nConcluído em %.0fs. Arquivos em: %s" % ((datetime.datetime.now() - t0).total_seconds(), OUT))

if __name__ == "__main__":
    main()
