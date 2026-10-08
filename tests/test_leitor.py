from datetime import date
from decimal import Decimal

import pytest

from posicional import gerador, leitor
from posicional.layout import LARGURA, LAYOUT, Campo


@pytest.mark.parametrize("texto, campo, esperado", [
    ("  Toada  ", Campo("x", 1, 9), "Toada"),
    ("000123", Campo("x", 1, 6, "inteiro"), 123),
    ("05000", Campo("x", 1, 5, "decimal2"), Decimal("50.00")),
    ("20260315", Campo("x", 1, 8, "data"), date(2026, 3, 15)),
    ("00000000", Campo("x", 1, 8, "data"), None),
    (" ", Campo("x", 1, 1, "flag"), "N"),
    ("S", Campo("x", 1, 1, "flag"), "S"),
])
def test_conversao(texto, campo, esperado):
    assert leitor.converter(texto, campo) == esperado


@pytest.mark.parametrize("texto, campo", [
    ("12a4", Campo("x", 1, 4, "inteiro")),
    ("20261340", Campo("x", 1, 8, "data")),
    ("T", Campo("x", 1, 1, "flag")),           # flag nunca vira booleano
])
def test_conversao_invalida(texto, campo):
    with pytest.raises(ValueError):
        leitor.converter(texto, campo)


def test_escrever_e_ler_devolve_o_mesmo(tmp_path):
    registros = [("TI", {"codigo": 100001, "nome": "Clóvis Brandão", "documento": "123", "nacional": "S"}),
                 ("OB", {"codigo": 200001, "titulo": "Seresta da Serra", "genero": "SER", "nacional": "S",
                         "bloqueada": "N", "registrada_em": date(2021, 5, 4)}),
                 ("OP", {"titular": 100001, "papel": "CA", "percentual": "100.00"})]
    gerador.escrever(tmp_path / "r.txt", 7, registros)
    assert all(len(l) == LARGURA for l in (tmp_path / "r.txt").read_text(encoding="cp1252").splitlines())
    remessa, problemas = leitor.ler(tmp_path / "r.txt")
    assert problemas == []
    assert remessa.cabecalho["remessa"] == 7
    assert remessa.titulares[0]["nome"] == "Clóvis Brandão"   # acento em cp1252 não desloca as colunas
    assert remessa.obras[0].participacoes == [{"titular": 100001, "papel": "CA", "percentual": Decimal("100.00")}]


def test_remessa_com_defeitos(tmp_path):
    *_, defeituosa = gerador.gerar(tmp_path)
    _, problemas = leitor.ler(defeituosa)
    textos = [str(p) for p in problemas]
    assert "linha 2: participação (OP) sem obra (OB) antes" in textos
    assert "linha 5: tem 118 posições, o layout pede 120" in textos
    assert any("registrada_em: data inválida" in t for t in textos)
    assert any("o trailer diz 99 registros OB" in t for t in textos)


def test_sem_trailer_e_tipo_desconhecido(tmp_path):
    hd = gerador.linha("HD", {"remessa": 1, "gerado_em": date(2026, 1, 1), "origem": "X"})
    (tmp_path / "r.txt").write_text(hd + "\r\n" + "ZZ".ljust(LARGURA) + "\r\n", encoding="cp1252", newline="")
    _, problemas = leitor.ler(tmp_path / "r.txt")
    assert [str(p) for p in problemas] == ["linha 2: tipo de registro desconhecido: 'ZZ'",
                                           "remessa: sem trailer TR: o arquivo pode ter chegado cortado"]


def test_layout_sem_campos_sobrepostos():
    for tipo, campos in LAYOUT.items():
        ocupadas = set(range(0, 2))
        for c in campos:
            posicoes = set(range(c.inicio - 1, c.inicio - 1 + c.tamanho))
            assert not posicoes & ocupadas, f"{tipo}.{c.nome} sobrepõe outro campo"
            assert max(posicoes) < LARGURA
            ocupadas |= posicoes
