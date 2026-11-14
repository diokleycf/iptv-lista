# iptv-lista 🇧🇷

Listas IPTV geradas **automaticamente a cada 6h** (canais) e 1x/dia (filmes/séries) via GitHub Actions.
Só canais brasileiros (ou dublados/legendados). Notícias internacionais ficam em pastas separadas por país.

## Links diretos (use no seu player)

| Conteúdo | URL |
|---|---|
| Tudo ao vivo | https://raw.githubusercontent.com/diokleycf/iptv-lista/main/LISTA_COMPLETA.m3u |
| Brasil (por seção) | https://raw.githubusercontent.com/diokleycf/iptv-lista/main/BRASIL/ |
| Notícias internacionais | https://raw.githubusercontent.com/diokleycf/iptv-lista/main/INTERNACIONAIS/ |
| Filmes dublados | https://raw.githubusercontent.com/diokleycf/iptv-lista/main/FILMES%20E%20SERIES/01%20-%20FILMES%20-%20Dublados.m3u |
| Filmes legendados | https://raw.githubusercontent.com/diokleycf/iptv-lista/main/FILMES%20E%20SERIES/02%20-%20FILMES%20-%20Legendados.m3u |
| Séries (por plataforma) | https://raw.githubusercontent.com/diokleycf/iptv-lista/main/FILMES%20E%20SERIES/SERIES/ |

## Como funciona
`atualizar.py` junta Saimo TV + iptv-org + Free-TV + iptv-com + Ramys, deduplica, testa os streams
e organiza por seção. `atualizar_filmes.py` gera os ~309 mil itens de VOD (filmes por gênero,
séries por plataforma). A Action roda os dois e publica num commit único.
