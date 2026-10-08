"""Remessa em arquivo posicional -> banco, por diferença, com conferência do trailer."""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

from . import carga, gerador, leitor

MARCADOR = ".posicional-demo"
ORDEM = ["titular", "obra", "participacao", "fonograma"]
ACOES = ["insert", "update", "igual", "delete"]


def _acoes(rel: carga.Relatorio) -> str:
    partes = []
    for tabela in ORDEM:
        do_tipo = {acao: n for (t, acao), n in rel.acoes.items() if t == tabela and n}
        if do_tipo:
            partes.append(f"{tabela} " + " ".join(f"{acao} {do_tipo[acao]}" for acao in ACOES if acao in do_tipo))
    return " | ".join(partes) or "nada a fazer"


def processar(arquivo: Path, banco: Path, dry_run: bool = False, reprocessar: bool = False) -> str:
    remessa, problemas = leitor.ler(arquivo)
    registros = len(remessa.titulares) + len(remessa.obras) + len(remessa.fonogramas) + len(remessa.exclusoes)
    print(f"[{arquivo.stem}]  lida: {registros} registros principais, "
          f"{sum(len(o.participacoes) for o in remessa.obras)} participações, {len(problemas)} problemas")
    if problemas:
        for p in problemas:
            print(f"      {p}")
        print("      recusada: nada foi aplicado")
        return "recusada"
    con = carga.conectar(banco)
    try:
        rel = carga.aplicar(con, remessa, arquivo.name, dry_run=dry_run, reprocessar=reprocessar)
    finally:
        con.close()
    if rel.situacao == "ja_aplicada":
        print(f"      já aplicada: {rel.detalhe}")
    else:
        print(f"      {rel.situacao}: {_acoes(rel)}{' (' + rel.detalhe + ')' if rel.detalhe else ''}")
        for tabela, chave, campo, antes, depois in rel.mudancas[:6]:
            print(f"        {tabela} {chave}: {campo} {antes!r} -> {depois!r}")
    return rel.situacao


def demo(base: Path) -> int:
    if base.exists():
        if not (base / MARCADOR).exists():
            print(f"A pasta {base} já existe e não foi criada pela demo; escolha outra com --base.")
            return 2
        shutil.rmtree(base)
    base.mkdir(parents=True)
    (base / MARCADOR).write_text("pasta da demo do arquivo posicional\n", encoding="utf-8")
    r1, r2, r3 = gerador.gerar(base / "entrada")
    banco = base / "banco.sqlite"
    print("[arquivos]  3 remessas fictícias: carga inicial, alterações e uma com defeitos\n")
    s = [processar(r1, banco)]
    print("\n[de novo]   a mesma remessa chega outra vez")
    s.append(processar(r1, banco))
    print("\n[reprocesso] com --reprocessar: tudo tem que vir igual")
    s.append(processar(r1, banco, reprocessar=True))
    print("\n[simulação] remessa 2 com --dry-run")
    s.append(processar(r2, banco, dry_run=True))
    print()
    s.append(processar(r2, banco))
    print()
    s.append(processar(r3, banco))
    return 0 if s == ["aplicada", "ja_aplicada", "aplicada", "simulada", "aplicada", "recusada"] else 1


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(prog="posicional", description=__doc__)
    sub = parser.add_subparsers(dest="comando", required=True)
    p = sub.add_parser("demo", help="gera três remessas fictícias e aplica todas")
    p.add_argument("--base", type=Path, default=Path("demo"))
    p = sub.add_parser("aplicar", help="lê, confere e aplica uma remessa")
    p.add_argument("arquivo", type=Path)
    p.add_argument("--banco", type=Path, default=Path("banco.sqlite"))
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--reprocessar", action="store_true", help="aplica de novo uma remessa já aplicada")
    a = parser.parse_args(argv)
    if a.comando == "demo":
        return demo(a.base)
    situacao = processar(a.arquivo, a.banco, a.dry_run, a.reprocessar)
    return 0 if situacao in ("aplicada", "simulada") else 1
