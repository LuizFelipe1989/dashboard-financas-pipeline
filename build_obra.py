from collections import OrderedDict

from finlib import get_clients, br_to_float, fmt_brl, red_negative_rule

SRC_TAB = "Fluxo_Apto_Realizado"
OUT_TAB = "Obra_Consolidado"

HEADER_ROW = 3       # row with "Itens", "Modalidade", ... labels
FIRST_ITEM_ROW = 4
LAST_ITEM_ROW = 80  # limite superior generoso — o fim real é achado dinamicamente (primeira linha com "Itens" vazio), pra não truncar quando linhas são inseridas na aba
MONTH_COL_START = "J"
MONTH_COL_END = "V"
COL_ITENS, COL_MODALIDADE, COL_CLASSIFICACAO, COL_TIPO, COL_EMPRESA = "B", "C", "D", "E", "F"
COL_TOTAL_PREVISTO = "I"

GREEN = (0.85, 0.92, 0.83)   # pago
PINK = (0.92, 0.82, 0.86)    # pendente / próximo


def classify_color(bg):
    rgb = (round(bg.get("red", 1), 2), round(bg.get("green", 1), 2), round(bg.get("blue", 1), 2))
    if rgb == GREEN:
        return "PAGO"
    if rgb == PINK:
        return "PENDENTE"
    return "FUTURO"


def load_items_and_colors(sh, sheets_api, ws):
    values = ws.get_all_values()

    def row(idx):  # 1-indexed sheet row -> 0-indexed list
        return values[idx - 1]

    items = []
    for r in range(FIRST_ITEM_ROW, LAST_ITEM_ROW + 1):
        vals = row(r)
        itens = vals[1].strip() if len(vals) > 1 else ""
        if not itens:
            continue
        modalidade = vals[2] if len(vals) > 2 else ""
        classificacao = vals[3] if len(vals) > 3 else ""
        tipo = vals[4] if len(vals) > 4 else ""
        empresa = vals[5] if len(vals) > 5 else ""
        previsto = br_to_float(vals[8]) if len(vals) > 8 else 0.0
        items.append({
            "row": r, "item": itens, "modalidade": modalidade,
            "classificacao": classificacao, "tipo": tipo, "empresa": empresa,
            "previsto": previsto,
        })

    range_a1 = f"{SRC_TAB}!{MONTH_COL_START}{FIRST_ITEM_ROW}:{MONTH_COL_END}{LAST_ITEM_ROW}"
    resp = sheets_api.spreadsheets().get(
        spreadsheetId=sh.id,
        ranges=[range_a1],
        fields="sheets.data.rowData.values(formattedValue,userEnteredFormat.backgroundColor)",
    ).execute()
    grid = resp["sheets"][0]["data"][0].get("rowData", [])

    for offset, item in enumerate(items):
        row_cells = grid[item["row"] - FIRST_ITEM_ROW].get("values", []) if item["row"] - FIRST_ITEM_ROW < len(grid) else []
        pago = pendente = futuro = 0.0
        for cell in row_cells:
            val = br_to_float(cell.get("formattedValue", ""))
            if val == 0.0:
                continue
            status = classify_color(cell.get("userEnteredFormat", {}).get("backgroundColor", {}))
            if status == "PAGO":
                pago += val
            elif status == "PENDENTE":
                pendente += val
            else:
                futuro += val
        item["pago"] = pago
        item["pendente"] = pendente
        item["futuro"] = futuro
        item["realizado_lancado"] = pago + pendente + futuro

    return items


def load_month_window(sh, sheets_api, ws, month_label):
    """Janela de pagamento de um mês específico do item table — cada item com valor
    lançado nesse mês, com status (Pago/Pendente/Futuro), classificação e modalidade.
    Dá a visão linha a linha do que é esperado sair naquele mês (não só o agregado),
    pra apoiar decisão antecipada."""
    values = ws.get_all_values()
    header_row = values[HEADER_ROW - 1]
    month_names = [c.strip() for c in header_row[9:22]]
    if month_label not in month_names:
        return []
    month_offset = month_names.index(month_label)

    range_a1 = f"{SRC_TAB}!{MONTH_COL_START}{FIRST_ITEM_ROW}:{MONTH_COL_END}{LAST_ITEM_ROW}"
    resp = sheets_api.spreadsheets().get(
        spreadsheetId=sh.id,
        ranges=[range_a1],
        fields="sheets.data.rowData.values(formattedValue,userEnteredFormat.backgroundColor)",
    ).execute()
    grid = resp["sheets"][0]["data"][0].get("rowData", [])

    window = []
    for r in range(FIRST_ITEM_ROW, LAST_ITEM_ROW + 1):
        vals = values[r - 1]
        itens = vals[1].strip() if len(vals) > 1 else ""
        if not itens:
            continue
        row_cells = grid[r - FIRST_ITEM_ROW].get("values", []) if r - FIRST_ITEM_ROW < len(grid) else []
        if month_offset >= len(row_cells):
            continue
        cell = row_cells[month_offset]
        val = br_to_float(cell.get("formattedValue", ""))
        if val == 0.0:
            continue
        status = classify_color(cell.get("userEnteredFormat", {}).get("backgroundColor", {}))
        window.append({
            "item": itens,
            "modalidade": vals[2].strip() if len(vals) > 2 else "",
            "classificacao": vals[3].strip() if len(vals) > 3 else "",
            "valor": abs(val),
            "status": status,
        })
    window.sort(key=lambda it: -it["valor"])
    return window


def payment_summary(items):
    """Cross-tab pago/pendente/futuro by Modalidade (Pix vs Cartão) — answers:
    quanto já foi pago (Pix+Cartão), quanto falta em Pix pendente, e quanto ainda
    vai vencer no cartão (parcelas futuras)."""
    pago_total = sum(i["pago"] for i in items)
    pendente_total = sum(i["pendente"] for i in items)
    pix_pendente = sum(i["pendente"] for i in items if i["modalidade"].strip().lower() == "pix")
    cartao_pendente = sum(i["pendente"] for i in items if i["modalidade"].strip().lower() == "cartão")
    cartao_futuro = sum(i["futuro"] for i in items if i["modalidade"].strip().lower() == "cartão")
    pix_futuro = sum(i["futuro"] for i in items if i["modalidade"].strip().lower() == "pix")
    return {
        "pago_total": pago_total,
        "pendente_total": pendente_total,
        "pix_pendente": pix_pendente,
        "cartao_pendente": cartao_pendente,
        "cartao_futuro": cartao_futuro,
        "pix_futuro": pix_futuro,
    }


def load_realizado_totais_mensais(ws):
    """Read the Cartão / Pix / Total monthly breakdown just below the item table
    (own month labels, e.g. Junho..Junho) — the sheet's own realized+scheduled
    obra cash-out per month, used to track it against the initial investment."""
    values = ws.get_all_values()
    header_row_idx = None
    for i, row in enumerate(values):
        if i > 50 and len(row) > 9 and row[9].strip() == "Junho":
            header_row_idx = i
            break
    if header_row_idx is None:
        return [], {}
    months = [c.strip() for c in values[header_row_idx][9:22] if c.strip()]
    n = len(months)

    def find_row(label):
        for row in values[header_row_idx:header_row_idx + 6]:
            if len(row) > 8 and row[8].strip() == label:
                return [br_to_float(c) for c in row[9:9 + n]]
        return [0.0] * n

    return months, {"cartao": find_row("Cartão"), "pix": find_row("Pix"), "total": find_row("Total")}


def main():
    sh, sheets_api = get_clients()
    ws = sh.worksheet(SRC_TAB)
    items = load_items_and_colors(sh, sheets_api, ws)

    header = ["Item", "Modalidade", "Classificação", "Empresa", "Previsto", "Pago", "Pendente", "Futuro", "% Pago"]
    out_values = [header]
    row_kinds = ["HEADER"]

    for it in items:
        pct_pago = (it["pago"] / it["previsto"] * 100) if it["previsto"] else 0.0
        out_values.append([
            it["item"], it["modalidade"], it["classificacao"], it["empresa"],
            fmt_brl(it["previsto"]), fmt_brl(it["pago"]), fmt_brl(it["pendente"]), fmt_brl(it["futuro"]),
            f"{pct_pago:.1f}%",
        ])
        row_kinds.append("ITEM")

    grand_previsto = sum(i["previsto"] for i in items)
    grand_pago = sum(i["pago"] for i in items)
    grand_pendente = sum(i["pendente"] for i in items)
    grand_futuro = sum(i["futuro"] for i in items)
    grand_pct = (grand_pago / grand_previsto * 100) if grand_previsto else 0.0
    out_values.append([
        "TOTAL GERAL", "", "", "",
        fmt_brl(grand_previsto), fmt_brl(grand_pago), fmt_brl(grand_pendente), fmt_brl(grand_futuro),
        f"{grand_pct:.1f}%",
    ])
    row_kinds.append("TOTAL")

    # rollup by Classificação
    out_values.append(["", "", "", "", "", "", "", "", ""])
    row_kinds.append("BLANK")
    out_values.append(["Rollup por Classificação", "", "", "Previsto", "Pago", "Pendente", "Futuro", "% Pago", ""])
    row_kinds.append("HEADER")

    by_class = OrderedDict()
    for it in items:
        c = it["classificacao"] or "(sem classificação)"
        acc = by_class.setdefault(c, {"previsto": 0.0, "pago": 0.0, "pendente": 0.0, "futuro": 0.0})
        acc["previsto"] += it["previsto"]
        acc["pago"] += it["pago"]
        acc["pendente"] += it["pendente"]
        acc["futuro"] += it["futuro"]

    for c, acc in sorted(by_class.items(), key=lambda kv: -kv[1]["previsto"]):
        pct = (acc["pago"] / acc["previsto"] * 100) if acc["previsto"] else 0.0
        out_values.append([
            c, "", "", fmt_brl(acc["previsto"]), fmt_brl(acc["pago"]), fmt_brl(acc["pendente"]), fmt_brl(acc["futuro"]), f"{pct:.1f}%", "",
        ])
        row_kinds.append("CLASS")

    try:
        out_ws = sh.worksheet(OUT_TAB)
        out_ws.clear()
    except Exception:
        out_ws = sh.add_worksheet(title=OUT_TAB, rows=len(out_values) + 5, cols=len(header) + 2)

    out_ws.update(values=out_values, range_name="A1")

    sheet_id = out_ws.id
    requests = []
    for r_idx, kind in enumerate(row_kinds):
        if kind == "HEADER":
            requests.append({
                "repeatCell": {
                    "range": {"sheetId": sheet_id, "startRowIndex": r_idx, "endRowIndex": r_idx + 1},
                    "cell": {"userEnteredFormat": {"textFormat": {"bold": True}, "backgroundColor": {"red": 0.9, "green": 0.9, "blue": 0.95}}},
                    "fields": "userEnteredFormat(textFormat,backgroundColor)",
                }
            })
        elif kind in ("TOTAL", "CLASS"):
            requests.append({
                "repeatCell": {
                    "range": {"sheetId": sheet_id, "startRowIndex": r_idx, "endRowIndex": r_idx + 1},
                    "cell": {"userEnteredFormat": {"textFormat": {"bold": True}}},
                    "fields": "userEnteredFormat.textFormat",
                }
            })
    # color the Pago (col F, idx5) and Pendente (col G, idx6) columns for item rows
    item_row_indices = [i for i, k in enumerate(row_kinds) if k == "ITEM"]
    if item_row_indices:
        start = min(item_row_indices)
        end = max(item_row_indices) + 1
        requests.append({
            "repeatCell": {
                "range": {"sheetId": sheet_id, "startRowIndex": start, "endRowIndex": end, "startColumnIndex": 5, "endColumnIndex": 6},
                "cell": {"userEnteredFormat": {"backgroundColor": {"red": GREEN[0], "green": GREEN[1], "blue": GREEN[2]}}},
                "fields": "userEnteredFormat.backgroundColor",
            }
        })
        requests.append({
            "repeatCell": {
                "range": {"sheetId": sheet_id, "startRowIndex": start, "endRowIndex": end, "startColumnIndex": 6, "endColumnIndex": 7},
                "cell": {"userEnteredFormat": {"backgroundColor": {"red": PINK[0], "green": PINK[1], "blue": PINK[2]}}},
                "fields": "userEnteredFormat.backgroundColor",
            }
        })
    requests.append(red_negative_rule(sheet_id, len(out_values), len(header)))
    if requests:
        sheets_api.spreadsheets().batchUpdate(spreadsheetId=sh.id, body={"requests": requests}).execute()

    print(f"Obra_Consolidado escrito: {len(out_values)} linhas")
    print(f"TOTAL GERAL -> Previsto: {fmt_brl(grand_previsto)} | Pago: {fmt_brl(grand_pago)} | Pendente: {fmt_brl(grand_pendente)} | Futuro: {fmt_brl(grand_futuro)} | %Pago: {grand_pct:.1f}%")


if __name__ == "__main__":
    main()
