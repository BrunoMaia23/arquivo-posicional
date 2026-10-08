"""Escrita no layout (usada para gerar as remessas fictícias) e as três remessas da demo."""
from __future__ import annotations

import random
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

from .layout import CODIFICACAO, LARGURA, LAYOUT

NOMES = ["Ademar", "Beatriz", "Clóvis", "Dalva", "Everaldo", "Fátima", "Gilberto", "Heloísa", "Ivone", "Jurandir",
         "Lourdes", "Moacir", "Nair", "Orlando", "Penha", "Rosângela", "Severino", "Terezinha", "Valdir", "Zuleica"]
SOBRENOMES = ["Amaral", "Brandão", "Castilho", "Dorneles", "Ferraz", "Godinho", "Lobato", "Magalhães", "Novaes",
              "Prates", "Quintela", "Sarmento", "Toledo", "Varela"]
PALAVRAS = ["Toada", "Baião", "Modinha", "Serenata", "Lamento", "Seresta", "Aboio", "Xote", "Marcha", "Rancho",
            "Frevo", "Choro", "Valsa", "Coco", "Cateretê", "Embolada"]
COMPLEMENTOS = ["da Saudade", "do Interior", "de Lua Cheia", "da Beira-Mar", "do Vaqueiro", "da Fogueira",
                "da Madrugada", "de Inverno", "do Cais", "da Serra"]
GENEROS = ["MPB", "SAM", "FOR", "SER", "CHO", "INS"]


def linha(tipo: str, valores: dict) -> str:
    texto = [" "] * LARGURA
    texto[0:2] = tipo
    for campo in LAYOUT[tipo]:
        v = valores.get(campo.nome)
        if campo.tipo == "texto":
            celula = (v or "")[:campo.tamanho].ljust(campo.tamanho)
        elif campo.tipo == "flag":
            celula = (v or " ")[:1]
        elif campo.tipo == "data":
            celula = v.strftime("%Y%m%d") if v else "0" * campo.tamanho
        elif campo.tipo == "decimal2":
            celula = str(int(Decimal(v) * 100)).zfill(campo.tamanho)
        else:
            celula = str(v).zfill(campo.tamanho) if v is not None else " " * campo.tamanho
        texto[campo.fatia] = celula
    return "".join(texto)


def escrever(caminho: Path, remessa: int, registros: list[tuple[str, dict]], quebrar=None) -> None:
    contagem = {t: sum(1 for tipo, _ in registros if tipo == t) for t in ("TI", "OB", "OP", "FO", "EX")}
    linhas = [linha("HD", {"remessa": remessa, "gerado_em": date(2026, 2, 1) + timedelta(days=7 * remessa),
                           "origem": "ENTIDADE PARCEIRA FICTICIA"})]
    linhas += [linha(tipo, valores) for tipo, valores in registros]
    linhas.append(linha("TR", {f"qt_{t.lower()}": n for t, n in contagem.items()}))
    if quebrar:
        linhas = quebrar(linhas)
    caminho.write_text("\r\n".join(linhas) + "\r\n", encoding=CODIFICACAO, newline="")


def _participacoes(rng: random.Random, titulares: list[int]) -> list[dict]:
    escolhidos = rng.sample(titulares, rng.randint(1, 4))
    partes = {1: ["100.00"], 2: ["50.00", "50.00"], 3: ["40.00", "30.00", "30.00"],
              4: ["33.34", "33.33", "16.67", "16.66"]}[len(escolhidos)]
    return [{"titular": t, "papel": rng.choice(["CA", "CO", "AU", "VE"]), "percentual": p}
            for t, p in zip(escolhidos, partes)]


def gerar(destino: Path | str, semente: int = 8) -> list[Path]:
    destino = Path(destino)
    destino.mkdir(parents=True, exist_ok=True)
    rng = random.Random(semente)
    titulares = {100000 + i: {"codigo": 100000 + i, "nome": f"{rng.choice(NOMES)} {rng.choice(SOBRENOMES)}",
                              "documento": f"{rng.randint(10**10, 10**11 - 1)}", "nacional": rng.choice("SSSN")}
                 for i in range(1, 31)}
    obras = {}
    for i in range(1, 41):
        obras[200000 + i] = {"codigo": 200000 + i, "titulo": f"{rng.choice(PALAVRAS)} {rng.choice(COMPLEMENTOS)}",
                             "genero": rng.choice(GENEROS), "nacional": "S", "bloqueada": "N",
                             "registrada_em": date(2020, 1, 1) + timedelta(days=rng.randint(0, 2000))}
    participacoes = {o: _participacoes(rng, list(titulares)) for o in obras}
    fonogramas = {f"BRZZZ26{i:05d}": {"isrc": f"BRZZZ26{i:05d}", "obra": rng.choice(list(obras)),
                                      "titulo": None, "duracao_seg": rng.randint(120, 360),
                                      "lancado_em": date(2026, 1, 1) + timedelta(days=rng.randint(0, 30))}
                  for i in range(1, 51)}
    for f in fonogramas.values():
        f["titulo"] = obras[f["obra"]]["titulo"]

    def registros(cod_titulares, cod_obras, isrcs, exclusoes=()):
        r = [("TI", titulares[t]) for t in cod_titulares]
        for o in cod_obras:
            r.append(("OB", obras[o]))
            r += [("OP", p) for p in participacoes[o]]
        r += [("FO", fonogramas[i]) for i in isrcs]
        r += [("EX", {"obra": o, "motivo": "pedido do titular"}) for o in exclusoes]
        return r

    arquivos = [destino / "remessa_000001.txt", destino / "remessa_000002.txt", destino / "remessa_000003.txt"]
    escrever(arquivos[0], 1, registros(titulares, obras, fonogramas))

    # remessa 2: alterações de verdade no meio de registros que vêm repetidos sem mudança
    alterados = rng.sample(sorted(titulares), 3)
    for t in alterados:
        titulares[t]["documento"] = f"{rng.randint(10**10, 10**11 - 1)}"
    mudam_obra = rng.sample(sorted(obras), 5)
    obras[mudam_obra[0]]["titulo"] += " (Nova Versão)"
    obras[mudam_obra[1]]["bloqueada"] = "S"
    obras[mudam_obra[2]]["genero"] = "SAM"
    obras[mudam_obra[3]]["titulo"] = obras[mudam_obra[3]]["titulo"].upper()
    obras[mudam_obra[4]]["registrada_em"] += timedelta(days=1)
    mudam_partes = rng.sample(sorted(set(obras) - set(mudam_obra)), 4)
    for o in mudam_partes:
        participacoes[o] = _participacoes(rng, list(titulares))
    novas = []
    for i in range(41, 47):
        obras[200000 + i] = {"codigo": 200000 + i, "titulo": f"{rng.choice(PALAVRAS)} {rng.choice(COMPLEMENTOS)}",
                             "genero": rng.choice(GENEROS), "nacional": "N", "bloqueada": "N", "registrada_em": None}
        participacoes[200000 + i] = _participacoes(rng, list(titulares))
        novas.append(200000 + i)
    novos_fono = []
    for i in range(51, 59):
        fonogramas[f"BRZZZ26{i:05d}"] = {"isrc": f"BRZZZ26{i:05d}", "obra": rng.choice(novas),
                                         "titulo": None, "duracao_seg": rng.randint(120, 360), "lancado_em": None}
        fonogramas[f"BRZZZ26{i:05d}"]["titulo"] = obras[fonogramas[f"BRZZZ26{i:05d}"]["obra"]]["titulo"]
        novos_fono.append(f"BRZZZ26{i:05d}")
    sem_fonograma = sorted(set(obras) - {f["obra"] for f in fonogramas.values()} - set(novas))
    excluir = sem_fonograma[:2]
    repetidas = rng.sample(sorted(set(obras) - set(mudam_obra) - set(mudam_partes) - set(novas) - set(excluir)), 10)
    escrever(arquivos[1], 2, registros(alterados, mudam_obra + mudam_partes + novas + repetidas, novos_fono, excluir))

    # remessa 3: defeitos de arquivo posicional de verdade
    def quebrar(linhas):
        linhas[3] = linhas[3][:-2]                              # linha cortada
        i = next(k for k, l in enumerate(linhas) if l.startswith("OB"))
        linhas[i] = linhas[i][:76] + "20261340" + linhas[i][84:]  # mês 13
        j = next(k for k, l in enumerate(linhas) if l.startswith("OP"))
        linhas.insert(1, linhas[j])                              # participação antes de qualquer obra
        linhas[-1] = linhas[-1][:9] + "0000099" + linhas[-1][16:]  # trailer com a contagem errada
        return linhas
    escrever(arquivos[2], 3, registros(list(titulares)[:5], list(obras)[:6], []), quebrar=quebrar)
    return arquivos
