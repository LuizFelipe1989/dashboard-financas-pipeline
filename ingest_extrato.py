"""Ingestão de gastos a partir de print de fatura de cartão ou extrato de conta.

Fluxo pretendido: o usuário manda um print (fatura do cartão ou extrato bancário) numa
mensagem; eu (Claude) leio a imagem, transcrevo os lançamentos e chamo append_card_items()
pra inserir as linhas na tabela certa — sem sobrescrever nada que já está lá, sempre
antes da linha TOTAL. Depois disso, rodar daily_update.py normalmente pra propagar pro
dashboard.

Duas tabelas de cartão existem hoje, com layouts de coluna diferentes:
- Contas!Cartão Pessoal  (gastos pessoais + "Obra Apto")     -> CONTAS_CARD_COLS
- Despesas_Casa!Cartão Casa (parcelas ainda pendentes do apto Saúde) -> DESPESAS_CASA_CARD_COLS

Um extrato de CONTA (não de cartão) não tem uma tabela de itens pra inserir — ele
atualiza o saldo disponível (finlib.SALDO_DISPONIVEL_IMEDIATO), que é editado direto no
código quando um novo extrato chega (mesmo padrão já usado desde o início do projeto).

Formato de item esperado por append_card_items(): {"desc": str, "valor": float,
"tipo": str, "banco": str}. Para parcelamentos, inclua "Parcela X/Y" na descrição
(load_card_items já usa isso pra calcular parcelas restantes); para assinatura/gasto
mensal fixo, inclua "Mensal" na descrição ou use Tipo="Assinaturas" — a classificação de
natureza (Fixo Mensal/Parcelado/Discricionário) é automática a partir disso.
"""
from finlib import get_clients, CONTAS_TAB, DESPESAS_CASA_TAB, fmt_brl

# (col_desc, col_valor, col_tipo, col_banco) — 0-indexado, mesma ordem em todo lugar.
CONTAS_CARD_COLS = (9, 10, 11, 12)
CONTAS_CARD_FIRST_ROW = 3
DESPESAS_CASA_CARD_COLS = (7, 8, 9, 10)
DESPESAS_CASA_CARD_FIRST_ROW = 6  # linha 5 é o cabeçalho ("Gasto" | " R$ " | "Tipo" | "Banco")


def find_total_row(ws, col_desc, first_row=3):
    """Primeira linha (1-indexada) onde a coluna de descrição está vazia ou é
    literalmente 'TOTAL' — cuidado: usa igualdade exata, não startswith, porque um
    item de verdade pode começar com a palavra 'Total' (já causou bug antes)."""
    values = ws.get_all_values()
    r = first_row
    while r - 1 < len(values):
        row = values[r - 1]
        desc = row[col_desc].strip() if len(row) > col_desc else ""
        if not desc or desc.upper() == "TOTAL":
            return r
        r += 1
    return r


def append_card_items(ws, items, cols=CONTAS_CARD_COLS, first_row=3):
    """Insere `items` (lista de dicts desc/valor/tipo/banco) na tabela de cartão de
    `ws`, logo antes da linha TOTAL — empurra o TOTAL pra baixo, não sobrescreve nada.
    Retorna a linha (1-indexada) onde a primeira inserção aconteceu."""
    col_desc, col_valor, col_tipo, col_banco = cols
    total_row = find_total_row(ws, col_desc, first_row)

    n_cols = max(cols) + 1
    rows = []
    for it in items:
        row = [""] * n_cols
        row[col_desc] = it["desc"]
        row[col_valor] = it["valor"]
        row[col_tipo] = it.get("tipo", "")
        row[col_banco] = it.get("banco", "")
        rows.append(row)

    ws.insert_rows(rows, row=total_row, value_input_option="USER_ENTERED")
    return total_row


def preview():
    """Mostra as últimas linhas de cada tabela de cartão, pra eu conferir onde a
    próxima inserção vai cair antes de rodar append_card_items de verdade."""
    sh, _ = get_clients()
    for label, tab, cols, first_row in [
        ("Contas", CONTAS_TAB, CONTAS_CARD_COLS, CONTAS_CARD_FIRST_ROW),
        ("Despesas_Casa", DESPESAS_CASA_TAB, DESPESAS_CASA_CARD_COLS, DESPESAS_CASA_CARD_FIRST_ROW),
    ]:
        ws = sh.worksheet(tab)
        total_row = find_total_row(ws, cols[0], first_row)
        values = ws.get_all_values()
        print(f"\n{label} ({tab}): próxima inserção antes da linha {total_row}")
        for r in range(max(1, total_row - 3), total_row + 1):
            row = values[r - 1] if r - 1 < len(values) else []
            desc = row[cols[0]] if len(row) > cols[0] else ""
            valor = row[cols[1]] if len(row) > cols[1] else ""
            print(f"  linha {r}: {desc!r} {valor!r}")


if __name__ == "__main__":
    preview()
