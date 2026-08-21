from collections import OrderedDict

from finlib import get_clients, fmt_brl, CONTAS_TAB, load_card_items, red_negative_rule

OUT_TAB = "Gastos_Por_Tipo"


def group_by_tipo(items):
    by_tipo = OrderedDict()
    for it in items:
        acc = by_tipo.setdefault(it["tipo"] or "(sem tipo)", {"total": 0.0, "itens": []})
        acc["total"] += it["valor_parcela"]
        acc["itens"].append(it["desc"])
    return by_tipo


def main():
    sh, sheets_api = get_clients()
    contas_ws = sh.worksheet(CONTAS_TAB)
    items = load_card_items(contas_ws)
    by_tipo = group_by_tipo(items)

    grand_total = sum(acc["total"] for acc in by_tipo.values()) or 1.0
    rows = sorted(by_tipo.items(), key=lambda kv: -kv[1]["total"])

    header = ["Tipo", "Total", "% do Total", "Itens"]
    out_values = [header]
    for tipo, acc in rows:
        pct = acc["total"] / grand_total * 100
        out_values.append([tipo, fmt_brl(acc["total"]), f"{pct:.1f}%", "; ".join(acc["itens"])])
    out_values.append(["TOTAL GERAL", fmt_brl(grand_total), "100.0%", f"{len(items)} itens"])

    try:
        out_ws = sh.worksheet(OUT_TAB)
        out_ws.clear()
    except Exception:
        out_ws = sh.add_worksheet(title=OUT_TAB, rows=len(out_values) + 5, cols=len(header) + 2)

    out_ws.update(values=out_values, range_name="A1")

    sheet_id = out_ws.id
    requests = [
        {
            "repeatCell": {
                "range": {"sheetId": sheet_id, "startRowIndex": 0, "endRowIndex": 1},
                "cell": {"userEnteredFormat": {"textFormat": {"bold": True}, "backgroundColor": {"red": 0.9, "green": 0.9, "blue": 0.95}}},
                "fields": "userEnteredFormat(textFormat,backgroundColor)",
            }
        },
        {
            "repeatCell": {
                "range": {"sheetId": sheet_id, "startRowIndex": len(out_values) - 1, "endRowIndex": len(out_values)},
                "cell": {"userEnteredFormat": {"textFormat": {"bold": True}}},
                "fields": "userEnteredFormat.textFormat",
            }
        },
    ]
    requests.append(red_negative_rule(sheet_id, len(out_values), len(header)))
    sheets_api.spreadsheets().batchUpdate(spreadsheetId=sh.id, body={"requests": requests}).execute()

    print(f"Gastos_Por_Tipo escrito: {len(out_values)} linhas")
    for tipo, acc in rows:
        print(f"  {tipo}: {fmt_brl(acc['total'])} ({acc['total']/grand_total*100:.1f}%) — {len(acc['itens'])} itens")


if __name__ == "__main__":
    main()
