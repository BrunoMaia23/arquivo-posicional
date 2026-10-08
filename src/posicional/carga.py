"""Aplicação da remessa no banco por diferença (SQLite aqui; no projeto real, Oracle).

Cada registro é comparado com o que já existe: insert se não existe, update só com os campos que
mudaram, e nada se veio igual. As participações de uma obra presente na remessa são substituídas
como um bloco, com cópia das antigas no histórico. Exclusão só com registro EX explícito: obra que não
veio na remessa não é apagada, porque a remessa traz só o que mudou.

A remessa inteira é uma transação. --dry-run executa tudo e desfaz, para mostrar o relatório antes.
"""
from __future__ import annotations

import sqlite3
from collections import Counter
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from pathlib import Path

from .leitor import Remessa

ESQUEMA = """
CREATE TABLE IF NOT EXISTS titular (
    codigo INTEGER PRIMARY KEY, nome TEXT NOT NULL, documento TEXT,
    nacional TEXT NOT NULL CHECK (nacional IN ('S', 'N')), falecido_em TEXT);
CREATE TABLE IF NOT EXISTS obra (
    codigo INTEGER PRIMARY KEY, titulo TEXT NOT NULL, genero TEXT,
    nacional TEXT NOT NULL CHECK (nacional IN ('S', 'N')), bloqueada TEXT NOT NULL CHECK (bloqueada IN ('S', 'N')),
    registrada_em TEXT);
CREATE TABLE IF NOT EXISTS participacao (
    obra INTEGER NOT NULL REFERENCES obra (codigo), titular INTEGER NOT NULL REFERENCES titular (codigo),
    papel TEXT NOT NULL, centesimos INTEGER NOT NULL, PRIMARY KEY (obra, titular, papel));
CREATE TABLE IF NOT EXISTS participacao_historico (
    obra INTEGER NOT NULL, titular INTEGER NOT NULL, papel TEXT NOT NULL, centesimos INTEGER NOT NULL,
    remessa INTEGER NOT NULL, arquivado_em TEXT NOT NULL DEFAULT (datetime('now')));
CREATE TABLE IF NOT EXISTS fonograma (
    isrc TEXT PRIMARY KEY, obra INTEGER NOT NULL REFERENCES obra (codigo), titulo TEXT NOT NULL,
    duracao_seg INTEGER, lancado_em TEXT);
CREATE TABLE IF NOT EXISTS remessa_aplicada (
    remessa INTEGER PRIMARY KEY, arquivo TEXT NOT NULL, aplicada_em TEXT NOT NULL DEFAULT (datetime('now')));
"""


@dataclass
class Relatorio:
    acoes: Counter = field(default_factory=Counter)        # (tabela, ação) -> quantidade
    mudancas: list[tuple] = field(default_factory=list)    # (tabela, chave, campo, antes, depois)
    situacao: str = "aplicada"                             # aplicada, simulada, ja_aplicada
    detalhe: str = ""


def conectar(banco: Path | str) -> sqlite3.Connection:
    con = sqlite3.connect(banco, isolation_level=None)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    con.executescript(ESQUEMA)
    return con


def aplicar(con: sqlite3.Connection, remessa: Remessa, arquivo: str, dry_run: bool = False,
            reprocessar: bool = False) -> Relatorio:
    numero = remessa.cabecalho.get("remessa")
    if numero is None:
        raise ValueError("remessa sem cabeçalho: não dá para saber o número")
    feita = con.execute("SELECT aplicada_em FROM remessa_aplicada WHERE remessa = ?", [numero]).fetchone()
    if feita and not reprocessar:
        return Relatorio(situacao="ja_aplicada", detalhe=f"aplicada em {feita[0]}; use --reprocessar")
    rel = Relatorio()
    con.execute("BEGIN")
    try:
        for t in remessa.titulares:
            _upsert(con, "titular", "codigo", _banco(t), rel)
        for o in remessa.obras:
            _upsert(con, "obra", "codigo", _banco(o.dados), rel)
            _participacoes(con, o.dados["codigo"], o.participacoes, numero, rel)
        for f in remessa.fonogramas:
            _upsert(con, "fonograma", "isrc", _banco(f), rel)
        for e in remessa.exclusoes:
            _excluir(con, e["obra"], numero, rel)
        con.execute("INSERT OR REPLACE INTO remessa_aplicada (remessa, arquivo) VALUES (?, ?)", [numero, arquivo])
    except Exception:
        con.execute("ROLLBACK")
        raise
    if dry_run:
        con.execute("ROLLBACK")
        rel.situacao, rel.detalhe = "simulada", "nada foi gravado"
    else:
        con.execute("COMMIT")
    return rel


def _banco(registro: dict) -> dict:
    """Datas em ISO; o resto como veio (as flags continuam S/N)."""
    return {k: v.isoformat() if isinstance(v, date) else v for k, v in registro.items()}


def _upsert(con: sqlite3.Connection, tabela: str, chave: str, dados: dict, rel: Relatorio) -> None:
    atual = con.execute(f"SELECT * FROM {tabela} WHERE {chave} = ?", [dados[chave]]).fetchone()
    if atual is None:
        colunas = list(dados)
        con.execute(f"INSERT INTO {tabela} ({', '.join(colunas)}) VALUES ({', '.join('?' * len(colunas))})",
                    [dados[c] for c in colunas])
        rel.acoes[(tabela, "insert")] += 1
        return
    mudou = {c: (atual[c], v) for c, v in dados.items() if atual[c] != v}
    if not mudou:
        rel.acoes[(tabela, "igual")] += 1
        return
    con.execute(f"UPDATE {tabela} SET {', '.join(f'{c} = ?' for c in mudou)} WHERE {chave} = ?",
                [v for _, v in mudou.values()] + [dados[chave]])
    rel.acoes[(tabela, "update")] += 1
    rel.mudancas += [(tabela, dados[chave], c, antes, depois) for c, (antes, depois) in mudou.items()]


def _participacoes(con: sqlite3.Connection, obra: int, novas: list[dict], remessa: int, rel: Relatorio) -> None:
    alvo = {(p["titular"], p["papel"], int(Decimal(p["percentual"]) * 100)) for p in novas}
    atuais = {(r["titular"], r["papel"], r["centesimos"]) for r in
              con.execute("SELECT titular, papel, centesimos FROM participacao WHERE obra = ?", [obra])}
    if alvo == atuais:
        rel.acoes[("participacao", "igual")] += len(alvo)
        return
    if atuais:
        con.executemany("INSERT INTO participacao_historico (obra, titular, papel, centesimos, remessa) VALUES (?, ?, ?, ?, ?)",
                        [(obra, t, p, c, remessa) for t, p, c in sorted(atuais)])
        con.execute("DELETE FROM participacao WHERE obra = ?", [obra])
        rel.acoes[("participacao", "delete")] += len(atuais)
    if alvo:
        con.executemany("INSERT INTO participacao VALUES (?, ?, ?, ?)", [(obra, t, p, c) for t, p, c in sorted(alvo)])
        rel.acoes[("participacao", "insert")] += len(alvo)


def _excluir(con: sqlite3.Connection, obra: int, remessa: int, rel: Relatorio) -> None:
    if con.execute("SELECT 1 FROM obra WHERE codigo = ?", [obra]).fetchone() is None:
        rel.acoes[("obra", "exclusao_sem_obra")] += 1
        return
    fonogramas = con.execute("SELECT count(*) FROM fonograma WHERE obra = ?", [obra]).fetchone()[0]
    if fonogramas:
        raise ValueError(f"obra {obra} tem {fonogramas} fonogramas e não pode ser excluída pela remessa")
    _participacoes(con, obra, [], remessa, rel)
    con.execute("DELETE FROM obra WHERE codigo = ?", [obra])
    rel.acoes[("obra", "delete")] += 1
