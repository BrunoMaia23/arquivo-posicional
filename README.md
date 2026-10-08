# arquivo-posicional

[![testes](https://github.com/BrunoMaia23/arquivo-posicional/actions/workflows/testes.yml/badge.svg)](https://github.com/BrunoMaia23/arquivo-posicional/actions/workflows/testes.yml)

```
         1         2         3         4         5         6         7         8         9
123456789012345678901234567890123456789012345678901234567890123456789012345678901234567890
HD0000000120260208ENTIDADE PARCEIRA FICTICIA
TI000100001Heloísa Godinho                                   65672633255   S00000000
OB000200001Embolada da Beira-Mar                                       MPBSN20241127
OP000100027CA10000
FOBRZZZ2600001000200020Choro do Vaqueiro                                           0025320260109
TR00000300000040000010300000500000000
```

Arquivo posicional ainda é como muita troca de dados entre instituições acontece: linhas de largura
fixa, um tipo de registro nas duas primeiras posições, cada campo numa coluna combinada num manual.
Trabalhei na migração de um importador desses, de um sistema em Delphi para Python, e escrevi a maior
parte dela. Este repositório refaz as ideias principais do zero, com um layout inventado e dados
fictícios.

*In English: loading a fixed-width, multi-record-type file into a database. A declarative layout,
errors reported by line and field, a trailer check, and a diff-based load (insert, update only the
changed fields, leave identical rows alone, replace child rows with history, explicit deletes), with
dry-run and safe reprocessing. Synthetic data.*

## O layout

Fica em `layout.py`, como dado: cada tipo de registro é uma lista de campos com início, tamanho e tipo.
Ler um tipo novo é acrescentar uma entrada, não escrever um parser.

| Tipo | O que é |
|---|---|
| HD | cabeçalho: número da remessa, data, origem |
| TI | titular |
| OB | obra; as linhas OP logo abaixo são as participações dela |
| OP | participação na obra: titular, papel, percentual com duas casas implícitas (`10000` = 100,00%) |
| FO | fonograma de uma obra |
| EX | exclusão explícita de obra |
| TR | trailer: quantos registros de cada tipo o arquivo tem |

O arquivo é cp1252, um byte por caractere, então o "í" de Heloísa não desloca as colunas seguintes.
Flags ficam como S/N do começo ao fim (o banco tem CHECK para isso): converter para booleano no meio
do caminho é um jeito clássico de acabar gravando T/F onde se esperava S/N.

## Lendo

`leitor.py` corta cada linha pelo layout do seu tipo e anota cada problema com linha e campo: largura
errada, tipo desconhecido, data impossível, número com letra, obrigatório vazio, participação sem obra
antes, registro depois do trailer. No fim, confere as quantidades do trailer, que é o jeito de saber se
o arquivo chegou inteiro. Com qualquer problema, a remessa é recusada inteira; num arquivo posicional,
uma coluna deslocada costuma estar errada em todas as linhas, não só na que deu erro.

## Aplicando

`carga.py` compara cada registro com o que já está no banco: insert se não existe, update só dos
campos que mudaram (e o relatório mostra quais), nada se veio igual. As participações de uma obra
presente na remessa são trocadas em bloco, e as antigas vão para o histórico com o número da remessa.
Obra que não veio na remessa não é apagada, porque a remessa só traz o que mudou; exclusão só com
registro EX, e é recusada se a obra ainda tiver fonograma.

A remessa inteira é uma transação. Remessa já aplicada é recusada, a não ser com `--reprocessar`, e
reprocessar uma remessa tem que dar "igual" em tudo. `--dry-run` aplica, mostra o relatório e desfaz.

## A demo

```bash
python -m venv .venv && source .venv/bin/activate    # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
python -m posicional demo
```

```
[arquivos]  3 remessas fictícias: carga inicial, alterações e uma com defeitos

[remessa_000001]  lida: 120 registros principais, 103 participações, 0 problemas
      aplicada: titular insert 30 | obra insert 40 | participacao insert 103 | fonograma insert 50

[de novo]   a mesma remessa chega outra vez
[remessa_000001]  lida: 120 registros principais, 103 participações, 0 problemas
      já aplicada: aplicada em 2026-10-08 19:13:16; use --reprocessar

[reprocesso] com --reprocessar: tudo tem que vir igual
[remessa_000001]  lida: 120 registros principais, 103 participações, 0 problemas
      aplicada: titular igual 30 | obra igual 40 | participacao igual 103 | fonograma igual 50

[simulação] remessa 2 com --dry-run
[remessa_000002]  lida: 38 registros principais, 65 participações, 0 problemas
      simulada: titular update 3 | obra insert 6 update 5 igual 14 delete 2 | participacao insert 27 igual 38 delete 12 | fonograma insert 8 (nada foi gravado)
        titular 100029: documento '25348800362' -> '87814732318'
        titular 100026: documento '80956916454' -> '95570275211'
        titular 100022: documento '64822243176' -> '34467985411'
        obra 200022: titulo 'Valsa da Serra' -> 'Valsa da Serra (Nova Versão)'
        obra 200019: bloqueada 'N' -> 'S'
        obra 200037: genero 'MPB' -> 'SAM'

[remessa_000002]  lida: 38 registros principais, 65 participações, 0 problemas
      aplicada: titular update 3 | obra insert 6 update 5 igual 14 delete 2 | participacao insert 27 igual 38 delete 12 | fonograma insert 8
        titular 100029: documento '25348800362' -> '87814732318'
        titular 100026: documento '80956916454' -> '95570275211'
        titular 100022: documento '64822243176' -> '34467985411'
        obra 200022: titulo 'Valsa da Serra' -> 'Valsa da Serra (Nova Versão)'
        obra 200019: bloqueada 'N' -> 'S'
        obra 200037: genero 'MPB' -> 'SAM'

[remessa_000003]  lida: 10 registros principais, 14 participações, 6 problemas
      linha 2: participação (OP) sem obra (OB) antes
      linha 5: tem 118 posições, o layout pede 120
      linha 8, registrada_em: data inválida '20261340'
      remessa: o trailer diz 5 registros TI e o arquivo tem 4
      remessa: o trailer diz 99 registros OB e o arquivo tem 6
      remessa: o trailer diz 14 registros OP e o arquivo tem 15
      recusada: nada foi aplicado
```

## No projeto real

O layout tem mais tipos de registro, alguns com subtipos, e o destino é o Oracle. A maior parte do
trabalho foi paridade com o sistema antigo: conferir, tabela por tabela, os inserts, updates e deletes
do Python contra os do Delphi, e manter o log no formato que a equipe já sabia ler. As execuções
manuais rodam com dry-run, e uma trava impede apontar para produção fora do Airflow.

## Testes

`pytest` cobre a conversão de cada tipo de campo, escrita e leitura devolvendo o mesmo conteúdo (com
acento), a remessa com defeitos, o layout sem campos sobrepostos, e a carga: inicial e reprocesso sem
efeito, update por diferença, histórico das participações, dry-run, flag inválida barrada pelo banco e
exclusão recusada.
