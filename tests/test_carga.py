import sqlite3

import pytest

from posicional import carga, gerador, leitor


@pytest.fixture
def ambiente(tmp_path):
    arquivos = gerador.gerar(tmp_path / "entrada")
    con = carga.conectar(tmp_path / "banco.sqlite")
    yield con, [leitor.ler(a)[0] for a in arquivos[:2]]
    con.close()


def _n(con, tabela):
    return con.execute(f"SELECT count(*) FROM {tabela}").fetchone()[0]


def test_carga_inicial_e_reprocesso_sem_efeito(ambiente):
    con, (r1, _) = ambiente
    rel = carga.aplicar(con, r1, "r1")
    assert rel.acoes[("obra", "insert")] == len(r1.obras) == _n(con, "obra")
    assert carga.aplicar(con, r1, "r1").situacao == "ja_aplicada"
    de_novo = carga.aplicar(con, r1, "r1", reprocessar=True)
    assert {acao for (_, acao) in de_novo.acoes} == {"igual"}
    assert de_novo.mudancas == []


def test_alteracoes_por_diferenca(ambiente):
    con, (r1, r2) = ambiente
    carga.aplicar(con, r1, "r1")
    obras_antes = _n(con, "obra")
    rel = carga.aplicar(con, r2, "r2")
    assert rel.acoes[("obra", "update")] == 5 and rel.acoes[("obra", "insert")] == 6
    assert rel.acoes[("obra", "delete")] == 2 and rel.acoes[("titular", "update")] == 3
    assert _n(con, "obra") == obras_antes + 6 - 2
    campos = {campo for t, _, campo, _, _ in rel.mudancas if t == "obra"}
    assert campos == {"titulo", "bloqueada", "genero", "registrada_em"}


def test_participacoes_substituidas_vao_para_o_historico(ambiente):
    con, (r1, r2) = ambiente
    carga.aplicar(con, r1, "r1")
    rel = carga.aplicar(con, r2, "r2")
    assert _n(con, "participacao_historico") == rel.acoes[("participacao", "delete")] > 0
    remessas = {r[0] for r in con.execute("SELECT DISTINCT remessa FROM participacao_historico")}
    assert remessas == {2}
    soma = con.execute("SELECT obra, sum(centesimos) FROM participacao GROUP BY obra "
                       "HAVING sum(centesimos) <> 10000").fetchall()
    assert soma == []


def test_dry_run_desfaz_tudo(ambiente):
    con, (r1, r2) = ambiente
    carga.aplicar(con, r1, "r1")
    antes = (_n(con, "obra"), _n(con, "participacao"), _n(con, "remessa_aplicada"))
    rel = carga.aplicar(con, r2, "r2", dry_run=True)
    assert rel.situacao == "simulada" and rel.acoes[("obra", "insert")] == 6
    assert (_n(con, "obra"), _n(con, "participacao"), _n(con, "remessa_aplicada")) == antes


def test_flag_que_nao_e_s_ou_n_nem_chega_no_banco(ambiente):
    con, (r1, _) = ambiente
    r1.obras[0].dados["bloqueada"] = "T"
    with pytest.raises(sqlite3.IntegrityError):
        carga.aplicar(con, r1, "r1")
    assert _n(con, "obra") == 0       # a remessa inteira voltou


def test_exclusao_de_obra_com_fonograma_e_recusada(ambiente):
    con, (r1, r2) = ambiente
    carga.aplicar(con, r1, "r1")
    com_fonograma = con.execute("SELECT obra FROM fonograma LIMIT 1").fetchone()[0]
    r2.exclusoes.append({"obra": com_fonograma, "motivo": "teste"})
    with pytest.raises(ValueError, match="fonogramas"):
        carga.aplicar(con, r2, "r2")
    assert _n(con, "remessa_aplicada") == 1
