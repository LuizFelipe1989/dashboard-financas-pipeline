"""Log append-only de Gastos_Por_Tipo. Gastos_Por_Tipo é sempre reescrita (snapshot
do estado atual de Contas!Cartão Pessoal); esta aba nunca é limpa — cada rodada
acrescenta uma nova leva de linhas com a data de registro, preservando o histórico
de como os gastos por tipo evoluíram mês a mês. Relevante a partir de agora porque
os próximos preenchimentos passam a ser feitos a partir de prints do app do banco
(entrada manual, sujeita a granularidade menor) em vez da tabela Contas mantida à mão.
"""
from datetime import datetime, timezone

from finlib import get_clients, fmt_brl, CONTAS_TAB, load_card_items
from build_gastos_tipo import group_by_natureza, NATUREZA_ORDEM

OUT_TAB = "Gastos_Historico"
HEADER = ["Data de Registro", "Competência", "Natureza", "Tipo", "Total", "% do Total", "Itens", "Fonte"]


def main(fonte="Contas!Cartão Pessoal", competencia=None):
    sh, sheets_api = get_clients()
    contas_ws = sh.worksheet(CONTAS_TAB)
    items = load_card_items(contas_ws)
    by_natureza = group_by_natureza(items)
    grand_total = sum(it["valor_parcela"] for it in items) or 1.0

    ts = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M")
    comp = competencia or ""

    new_rows = []
    for nat in NATUREZA_ORDEM:
        tipos = by_natureza[nat]
        for tipo, acc in sorted(tipos.items(), key=lambda kv: -kv[1]["total"]):
            pct = acc["total"] / grand_total * 100
            new_rows.append([ts, comp, nat, tipo, fmt_brl(acc["total"]), f"{pct:.1f}%", "; ".join(acc["itens"]), fonte])

    try:
        out_ws = sh.worksheet(OUT_TAB)
        existing = out_ws.get_all_values()
        if not existing:
            out_ws.append_row(HEADER)
    except Exception:
        out_ws = sh.add_worksheet(title=OUT_TAB, rows=len(new_rows) + 50, cols=len(HEADER) + 2)
        out_ws.append_row(HEADER)
        sheets_api.spreadsheets().batchUpdate(spreadsheetId=sh.id, body={"requests": [{
            "repeatCell": {
                "range": {"sheetId": out_ws.id, "startRowIndex": 0, "endRowIndex": 1},
                "cell": {"userEnteredFormat": {"textFormat": {"bold": True}, "backgroundColor": {"red": 0.9, "green": 0.9, "blue": 0.95}}},
                "fields": "userEnteredFormat(textFormat,backgroundColor)",
            }
        }]}).execute()

    out_ws.append_rows(new_rows, value_input_option="USER_ENTERED")
    print(f"Gastos_Historico: {len(new_rows)} linhas registradas em {ts} (fonte: {fonte}).")


if __name__ == "__main__":
    main()
