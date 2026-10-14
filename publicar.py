#!/usr/bin/env python3
"""Publicação automática no Instagram da campanha "Apadrinhe a Educação".

Uso:
  python3 publicar.py --dry-run            mostra o calendário, sem publicar nada
  python3 publicar.py                      publica o post de hoje (se ainda não foi publicado)
  python3 publicar.py --data 2026-10-16    publica o post dessa data agora (adiantar)
  python3 publicar.py --verificar-token    só confere se o token está válido
  python3 publicar.py --converter PASTA    converte os PNG da PASTA para JPEG em posts/ (Mac)

Variáveis de ambiente (vêm dos Secrets do GitHub, nunca do código):
  IG_TOKEN    token de acesso (token de Página do Facebook)
  IG_USER_ID  ID da conta do Instagram
"""
import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

RAIZ = Path(__file__).resolve().parent
POSTS = RAIZ / "posts"
LEGENDAS = POSTS / "legendas.md"
CALENDARIO = RAIZ / "calendario.json"
PUBLICADOS = RAIZ / "publicados.json"
LOG = RAIZ / "log.txt"

FUSO = ZoneInfo("America/Sao_Paulo")
ANO = 2026
INICIO = "2026-10-15"  # nada antes disso é publicado
API = "https://graph.facebook.com/v26.0"
TENTATIVAS = 3
INTERVALO_TENTATIVAS = 5 * 60
VALOR_ERRADO = re.compile(r"R\$\s*35\b")

ARQUIVO = re.compile(r"^(\d{4}-\d{2}-\d{2})_(.+?)(?:_slide(\d+))?\.jpg$", re.IGNORECASE)
TITULO = re.compile(r"^##\s+(?:RESERVA\s*[–-]\s*)?(\d{2})/(\d{2})\b")


def agora():
    return datetime.now(FUSO)


def registrar(msg):
    linha = f"[{agora():%Y-%m-%d %H:%M:%S}] {msg}"
    print(linha, flush=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(linha + "\n")


def aviso(msg):
    # No GitHub Actions, "::warning::" aparece em destaque no resumo da execução.
    prefixo = "::warning::" if os.environ.get("GITHUB_ACTIONS") else "AVISO: "
    print(prefixo + msg, flush=True)


# ---------------------------------------------------------------- calendário

def ler_legendas():
    legendas, atual, linhas = {}, None, []
    for linha in LEGENDAS.read_text(encoding="utf-8").splitlines():
        if linha.startswith("## "):
            if atual:
                legendas[atual] = "\n".join(linhas).strip("\n")
            m = TITULO.match(linha)
            if not m:
                raise SystemExit(f"Título de legenda sem data reconhecível: {linha!r}")
            atual = f"{ANO}-{m.group(2)}-{m.group(1)}"
            if atual in legendas:
                raise SystemExit(f"Duas legendas para a mesma data: {atual}")
            linhas = []
        elif atual:
            linhas.append(linha)
    if atual:
        legendas[atual] = "\n".join(linhas).strip("\n")
    return legendas


def montar_calendario():
    imagens = {}
    for arq in sorted(POSTS.glob("*.jpg")):
        m = ARQUIVO.match(arq.name)
        if not m:
            raise SystemExit(f"Nome de imagem fora do padrão: {arq.name}")
        data, _, slide = m.groups()
        imagens.setdefault(data, []).append((int(slide) if slide else 0, arq.name))

    legendas = ler_legendas()
    problemas, entradas = [], []
    for data in sorted(set(imagens) | set(legendas)):
        if data < INICIO:
            continue
        arquivos = [nome for _, nome in sorted(imagens.get(data, []))]
        legenda = legendas.get(data)
        if not arquivos:
            problemas.append(f"{data}: tem legenda mas NÃO tem imagem")
        if legenda is None:
            problemas.append(f"{data}: tem imagem mas NÃO tem legenda")
        elif VALOR_ERRADO.search(legenda):
            problemas.append(f"{data}: legenda com 'R$ 35' (o valor correto é R$ 20)")
        if len(arquivos) > 10:
            problemas.append(f"{data}: carrossel com mais de 10 imagens")
        if legenda and (len(legenda) > 2200 or legenda.count("#") > 30):
            problemas.append(f"{data}: legenda passa do limite do Instagram (2.200 caracteres / 30 hashtags)")
        slides = [n for n, _ in sorted(imagens.get(data, []))]
        if len(arquivos) > 1 and slides != list(range(1, len(arquivos) + 1)):
            problemas.append(f"{data}: slides fora de ordem ou faltando ({slides})")
        entradas.append({
            "data": data,
            "horario": "18:00",
            "tipo": "carrossel" if len(arquivos) > 1 else "post único",
            "arquivos": arquivos,
            "legenda": legenda,
        })

    CALENDARIO.write_text(json.dumps(entradas, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return entradas, problemas


def ler_publicados():
    if PUBLICADOS.exists():
        return json.loads(PUBLICADOS.read_text(encoding="utf-8"))
    return {}


def salvar_publicado(data, media_id, permalink):
    publicados = ler_publicados()
    publicados[data] = {"media_id": media_id, "link": permalink, "publicado_em": agora().isoformat(timespec="seconds")}
    PUBLICADOS.write_text(json.dumps(publicados, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def pausados():
    arq = RAIZ / "pausar.txt"
    if not arq.exists():
        return set()
    return {l.strip() for l in arq.read_text(encoding="utf-8").splitlines() if l.strip() and not l.startswith("#")}


# ---------------------------------------------------------------- API da Meta

def chamar(metodo, caminho, **params):
    params["access_token"] = os.environ["IG_TOKEN"]
    dados = urllib.parse.urlencode(params).encode()
    url = f"{API}/{caminho}"
    if metodo == "GET":
        url, dados = f"{url}?{dados.decode()}", None
    try:
        with urllib.request.urlopen(urllib.request.Request(url, data=dados, method=metodo), timeout=60) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        corpo = e.read().decode(errors="replace")
        try:
            erro = json.loads(corpo)["error"]
            corpo = f"{erro.get('message')} (código {erro.get('code')}/{erro.get('error_subcode')})"
        except Exception:
            pass
        raise RuntimeError(f"Meta respondeu {e.code}: {corpo}") from None


def url_publica(nome):
    repo = os.environ.get("GITHUB_REPOSITORY")
    ramo = os.environ.get("GITHUB_REF_NAME", "main")
    if not repo:
        raise SystemExit("GITHUB_REPOSITORY não definido: a publicação real só roda no GitHub Actions.")
    return f"https://raw.githubusercontent.com/{repo}/{ramo}/posts/{urllib.parse.quote(nome)}"


def esperar_container(cid):
    for _ in range(10):
        status = chamar("GET", cid, fields="status_code,status").get("status_code")
        if status == "FINISHED":
            return
        if status in ("ERROR", "EXPIRED"):
            raise RuntimeError(f"Container {cid} com status {status}")
        time.sleep(30)
    raise RuntimeError(f"Container {cid} não ficou pronto a tempo")


def ja_esta_no_instagram(ig, legenda):
    """Proteção extra contra post duplicado: procura a mesma legenda nos últimos posts."""
    recentes = chamar("GET", f"{ig}/media", fields="id,caption,permalink", limit=10).get("data", [])
    for m in recentes:
        if (m.get("caption") or "").strip() == legenda.strip():
            return m
    return None


def publicar(entrada):
    ig = os.environ["IG_USER_ID"]
    existente = ja_esta_no_instagram(ig, entrada["legenda"])
    if existente:
        registrar(f"{entrada['data']}: já estava no Instagram ({existente['id']}); só registrei.")
        return existente["id"], existente.get("permalink")

    if entrada["tipo"] == "post único":
        cid = chamar("POST", f"{ig}/media", image_url=url_publica(entrada["arquivos"][0]),
                     caption=entrada["legenda"])["id"]
    else:
        filhos = []
        for nome in entrada["arquivos"]:
            filho = chamar("POST", f"{ig}/media", image_url=url_publica(nome), is_carousel_item="true")["id"]
            esperar_container(filho)
            filhos.append(filho)
        cid = chamar("POST", f"{ig}/media", media_type="CAROUSEL", children=",".join(filhos),
                     caption=entrada["legenda"])["id"]
    esperar_container(cid)
    media_id = chamar("POST", f"{ig}/media_publish", creation_id=cid)["id"]
    permalink = chamar("GET", media_id, fields="permalink").get("permalink")
    return media_id, permalink


def publicar_com_tentativas(entrada):
    for tentativa in range(1, TENTATIVAS + 1):
        try:
            registrar(f"{entrada['data']}: publicando ({entrada['tipo']}, {len(entrada['arquivos'])} imagem(ns)), tentativa {tentativa}")
            media_id, permalink = publicar(entrada)
            salvar_publicado(entrada["data"], media_id, permalink)
            registrar(f"{entrada['data']}: PUBLICADO. ID {media_id} {permalink or ''}")
            return True
        except Exception as e:
            registrar(f"{entrada['data']}: FALHOU na tentativa {tentativa}: {e}")
            if tentativa < TENTATIVAS:
                time.sleep(INTERVALO_TENTATIVAS)
    return False


def verificar_token():
    """Falha se o token não funcionar; avisa se ele for expirar em menos de 15 dias."""
    token = os.environ["IG_TOKEN"]
    conta = chamar("GET", os.environ["IG_USER_ID"], fields="username")
    print(f"Token OK. Conta: @{conta.get('username')}")
    info = chamar("GET", "debug_token", input_token=token).get("data", {})
    expira = info.get("expires_at", 0)
    if expira:
        dias = (expira - time.time()) / 86400
        print(f"O token expira em {dias:.0f} dias.")
        if dias < 15:
            aviso(f"O token do Instagram expira em {dias:.0f} dias. Gere um novo e atualize o Secret IG_TOKEN (veja o README).")
            return dias > 0
    else:
        print("O token não tem data de expiração.")
    return True


# ---------------------------------------------------------------- comandos

def converter(pasta):
    for png in sorted(Path(pasta).rglob("*.png")):
        destino = POSTS / (png.stem + ".jpg")
        subprocess.run(["sips", "-s", "format", "jpeg", "-s", "formatOptions", "95", str(png), "--out", str(destino)],
                       check=True, capture_output=True)
        print(f"{png.name} -> posts/{destino.name}")


def dry_run(entradas, problemas):
    hoje = agora().date().isoformat()
    publicados, pausa = ler_publicados(), pausados()
    print(f"{'Data':<11} {'Tipo':<11} {'Slides':>6}  {'Situação':<15} Início da legenda")
    print("-" * 100)
    for e in entradas:
        if e["data"] in publicados:
            sit = "publicado"
        elif e["data"] in pausa:
            sit = "pausado"
        elif e["data"] < hoje:
            sit = "DATA PASSOU"
        elif e["data"] == hoje:
            sit = "hoje às 18h"
        else:
            sit = "agendado"
        inicio = (e["legenda"] or "(SEM LEGENDA)").split("\n")[0][:55]
        print(f"{e['data']:<11} {e['tipo']:<11} {len(e['arquivos']):>6}  {sit:<15} {inicio}")
    print(f"\n{len(entradas)} publicações, {sum(len(e['arquivos']) for e in entradas)} imagens. Nada foi publicado (--dry-run).")
    for p in problemas:
        aviso(p)


def principal():
    p = argparse.ArgumentParser()
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--data", help="publica agora o post desta data (AAAA-MM-DD)")
    p.add_argument("--verificar-token", action="store_true")
    p.add_argument("--converter", metavar="PASTA")
    a = p.parse_args()

    if a.converter:
        return converter(a.converter)

    entradas, problemas = montar_calendario()
    if a.dry_run:
        return dry_run(entradas, problemas)
    if a.verificar_token:
        sys.exit(0 if verificar_token() else 1)

    hoje = agora().date().isoformat()
    alvo = a.data or hoje
    publicados, pausa = ler_publicados(), pausados()
    falhou = False

    for e in entradas:
        if e["data"] < hoje and e["data"] not in publicados and e["data"] not in pausa:
            aviso(f"{e['data']} já passou e não foi publicado. Não vou publicar sozinho; se quiser, publique à mão.")

    entrada = next((e for e in entradas if e["data"] == alvo), None)
    if alvo < hoje:
        aviso(f"{alvo} já passou. Nada publicado.")
    elif entrada is None:
        print(f"Nenhum post agendado para {alvo}.")
    elif alvo in publicados:
        print(f"{alvo} já foi publicado em {publicados[alvo]['publicado_em']}. Nada a fazer.")
    elif alvo in pausa:
        print(f"{alvo} está pausado (pausar.txt). Nada publicado.")
    elif any(p.startswith(alvo) for p in problemas):
        falhou = True
        registrar(f"{alvo}: NÃO publicado por problema no conteúdo: " + "; ".join(p for p in problemas if p.startswith(alvo)))
    elif a.data is None and agora().hour < 17:
        print("Ainda não são 18h em Brasília. Nada publicado.")
    else:
        falhou = not publicar_com_tentativas(entrada)

    for prob in problemas:
        aviso(prob)
    if falhou or problemas:
        sys.exit(1)


if __name__ == "__main__":
    principal()
