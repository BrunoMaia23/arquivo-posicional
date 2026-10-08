"""Layout do arquivo: cada tipo de registro é uma lista de campos com início, tamanho e tipo.

O layout é dado, não código: ler um tipo novo de registro é acrescentar uma entrada aqui. Linhas de
120 posições, em cp1252 (um caractere por byte, então posição de caractere e de byte coincidem).

Tipos de campo:
- texto: corta os espaços das pontas
- inteiro: zeros à esquerda
- decimal2: duas casas implícitas ("05000" -> 50.00)
- data: AAAAMMDD, ou zeros/brancos para vazio
- flag: S ou N, branco vira N. Fica como texto do começo ao fim: converter para booleano no meio do
  caminho é um jeito clássico de gravar T/F onde o banco espera S/N.
"""
from __future__ import annotations

from dataclasses import dataclass

LARGURA = 120
CODIFICACAO = "cp1252"


@dataclass(frozen=True)
class Campo:
    nome: str
    inicio: int      # posição de 1 em diante, como nos manuais de layout
    tamanho: int
    tipo: str = "texto"
    obrigatorio: bool = False

    @property
    def fatia(self) -> slice:
        return slice(self.inicio - 1, self.inicio - 1 + self.tamanho)


LAYOUT: dict[str, list[Campo]] = {
    "HD": [Campo("remessa", 3, 8, "inteiro", True), Campo("gerado_em", 11, 8, "data", True),
           Campo("origem", 19, 30, "texto", True)],
    "TI": [Campo("codigo", 3, 9, "inteiro", True), Campo("nome", 12, 50, "texto", True),
           Campo("documento", 62, 14, "texto"), Campo("nacional", 76, 1, "flag"),
           Campo("falecido_em", 77, 8, "data")],
    "OB": [Campo("codigo", 3, 9, "inteiro", True), Campo("titulo", 12, 60, "texto", True),
           Campo("genero", 72, 3, "texto"), Campo("nacional", 75, 1, "flag"),
           Campo("bloqueada", 76, 1, "flag"), Campo("registrada_em", 77, 8, "data")],
    "OP": [Campo("titular", 3, 9, "inteiro", True), Campo("papel", 12, 2, "texto", True),
           Campo("percentual", 14, 5, "decimal2", True)],
    "FO": [Campo("isrc", 3, 12, "texto", True), Campo("obra", 15, 9, "inteiro", True),
           Campo("titulo", 24, 60, "texto", True), Campo("duracao_seg", 84, 5, "inteiro"),
           Campo("lancado_em", 89, 8, "data")],
    "EX": [Campo("obra", 3, 9, "inteiro", True), Campo("motivo", 12, 40, "texto")],
    "TR": [Campo("qt_ti", 3, 7, "inteiro", True), Campo("qt_ob", 10, 7, "inteiro", True),
           Campo("qt_op", 17, 7, "inteiro", True), Campo("qt_fo", 24, 7, "inteiro", True),
           Campo("qt_ex", 31, 7, "inteiro", True)],
}
PAPEIS = {"CA": "compositor e autor", "CO": "compositor", "AU": "autor", "VE": "versionista", "ED": "editora"}
