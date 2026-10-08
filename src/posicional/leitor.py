"""Leitura da remessa: corta cada linha pelo layout do seu tipo e confere a estrutura e o trailer.

Todo problema guarda a linha e o campo. A remessa com qualquer problema não é aplicada: um arquivo
posicional com uma coluna deslocada costuma estar errado inteiro, não só numa linha.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from pathlib import Path

from .layout import CODIFICACAO, LARGURA, LAYOUT, Campo


@dataclass(frozen=True)
class Problema:
    linha: int
    campo: str
    mensagem: str

    def __str__(self) -> str:
        onde = f"linha {self.linha}" if self.linha else "remessa"
        return f"{onde}{', ' + self.campo if self.campo else ''}: {self.mensagem}"


@dataclass
class Obra:
    dados: dict
    linha: int
    participacoes: list[dict] = field(default_factory=list)


@dataclass
class Remessa:
    cabecalho: dict = field(default_factory=dict)
    titulares: list[dict] = field(default_factory=list)
    obras: list[Obra] = field(default_factory=list)
    fonogramas: list[dict] = field(default_factory=list)
    exclusoes: list[dict] = field(default_factory=list)
    trailer: dict | None = None


def converter(texto: str, campo: Campo):
    limpo = texto.strip()
    if campo.tipo == "texto":
        return limpo
    if campo.tipo == "flag":
        if limpo not in ("", "S", "N"):
            raise ValueError(f"flag deve ser S ou N, veio {texto!r}")
        return limpo or "N"
    if not limpo or (campo.tipo == "data" and set(limpo) == {"0"}):
        return None
    if not limpo.isdigit():
        raise ValueError(f"esperava só dígitos, veio {texto!r}")
    if campo.tipo == "inteiro":
        return int(limpo)
    if campo.tipo == "decimal2":
        return Decimal(int(limpo)) / 100
    if campo.tipo == "data":
        try:
            return date(int(limpo[:4]), int(limpo[4:6]), int(limpo[6:8]))
        except ValueError:
            raise ValueError(f"data inválida {texto!r}") from None
    raise ValueError(f"tipo de campo desconhecido no layout: {campo.tipo}")


def ler(caminho: Path | str) -> tuple[Remessa, list[Problema]]:
    remessa, problemas = Remessa(), []
    contagem: Counter = Counter()
    with open(caminho, encoding=CODIFICACAO, newline="") as arquivo:
        linhas = [l.rstrip("\r\n") for l in arquivo]
    for n, linha in enumerate(linhas, start=1):
        if not linha.strip():
            continue
        if len(linha) != LARGURA:
            problemas.append(Problema(n, "", f"tem {len(linha)} posições, o layout pede {LARGURA}"))
            continue
        tipo = linha[:2]
        if tipo not in LAYOUT:
            problemas.append(Problema(n, "", f"tipo de registro desconhecido: {tipo!r}"))
            continue
        registro = {}
        for campo in LAYOUT[tipo]:
            try:
                registro[campo.nome] = converter(linha[campo.fatia], campo)
            except ValueError as exc:
                problemas.append(Problema(n, campo.nome, str(exc)))
                registro[campo.nome] = None
                continue
            if campo.obrigatorio and registro[campo.nome] in (None, ""):
                problemas.append(Problema(n, campo.nome, "obrigatório e veio vazio"))
        contagem[tipo] += 1
        problemas += _encaixar(remessa, tipo, registro, n, primeira=(contagem.total() == 1))
    problemas += _conferir_trailer(remessa, contagem)
    return remessa, problemas


def _encaixar(remessa: Remessa, tipo: str, registro: dict, n: int, primeira: bool) -> list[Problema]:
    if tipo == "HD":
        if not primeira:
            return [Problema(n, "", "cabeçalho fora da primeira linha")]
        remessa.cabecalho = registro
        return []
    if primeira:
        return [Problema(n, "", "a remessa precisa começar pelo cabeçalho HD")]
    if remessa.trailer is not None:
        return [Problema(n, "", "registro depois do trailer")]
    if tipo == "TI":
        remessa.titulares.append(registro)
    elif tipo == "OB":
        remessa.obras.append(Obra(registro, n))
    elif tipo == "OP":
        if not remessa.obras:
            return [Problema(n, "", "participação (OP) sem obra (OB) antes")]
        remessa.obras[-1].participacoes.append(registro)
    elif tipo == "FO":
        remessa.fonogramas.append(registro)
    elif tipo == "EX":
        remessa.exclusoes.append(registro)
    elif tipo == "TR":
        remessa.trailer = registro
    return []


def _conferir_trailer(remessa: Remessa, contagem: Counter) -> list[Problema]:
    if remessa.trailer is None:
        return [Problema(0, "", "sem trailer TR: o arquivo pode ter chegado cortado")]
    problemas = []
    for tipo in ("TI", "OB", "OP", "FO", "EX"):
        declarado = remessa.trailer.get(f"qt_{tipo.lower()}")
        if declarado is not None and declarado != contagem[tipo]:
            problemas.append(Problema(0, "", f"o trailer diz {declarado} registros {tipo} e o arquivo tem {contagem[tipo]}"))
    return problemas
