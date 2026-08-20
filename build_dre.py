from finlib import (
    get_clients, fmt_brl, GROUPS, PROJ_TAB, CONTAS_TAB, REF_MONTH_INDEX,
    load_projecao, load_card_items, cartao_por_tipo, compute_totals,
)

OUT_TAB = "DRE_Mensal"


def build_rows(months, data, cartao_tipo, totals):
    n = len(months)
    group_sums = {}
    for _, group in GROUPS:
        if group is not None and group not in group_sums:
            group_sums[group] = [0.0] * n
    for label, group in GROUPS:
        if group is None:
            continue
        vals = data.get(label, [0.0] * n)
        group_sums[group] = [a + b for a, b in zip(group_sums[group], vals)]

    final_rows = []
    i = 0
    while i < len(GROUPS):
        label, group = GROUPS[i]
        if group is None:
            final_rows.append(("HEADER", label, None))
            j = i + 1
            grp_key = None
            while j < len(GROUPS) and GROUPS[j][1] is not None:
                sub_label, sub_group = GROUPS[j]
                grp_key = sub_group
                vals = data.get(sub_label, [0.0] * n)
                display_label = sub_label.replace("#2", "")
                final_rows.append(("LINE", display_label, vals))
                j += 1
            if grp_key == "VARIAVEL":
                for tipo, vals in sorted(cartao_tipo.items(), key=lambda kv: -sum(kv[1])):
                    final_rows.append(("LINE", f"Cartão Pessoal — {tipo}", vals))
                final_rows.append(("SUBTOTAL", "Subtotal", totals["variavel"]))
            elif grp_key is not None:
                final_rows.append(("SUBTOTAL", "Subtotal", group_sums[grp_key]))
            i = j
        else:
            i += 1

    final_rows.append(("HEADER", "(=) RECEITA LÍQUIDA", None))
    final_rows.append(("SUBTOTAL", "Receita Líquida", totals["receita_liquida"]))
    final_rows.append(("HEADER", "(=) MARGEM LÍQUIDA", None))
    final_rows.append(("SUBTOTAL", "Margem Líquida (Resultado do Mês)", totals["margem_liquida"]))

    return final_rows


def main():
    sh, sheets_api = get_clients()
    src_ws = sh.worksheet(PROJ_TAB)
    contas_ws = sh.worksheet(CONTAS_TAB)
    months, data = load_projecao(src_ws)
    card_items = load_card_items(contas_ws)
    ctipo = cartao_por_tipo(card_items, len(months))
    totals = compute_totals(months, data, ctipo)
    rows = build_rows(months, data, ctipo, totals)

    base_receita = sum(abs(v) for v in totals["receita_liquida"]) or 1.0

    header_row = ["Linha"] + months + ["TOTAL", "% peso (sobre Receita Líquida)"]
    out_values = [header_row]
    row_types = ["HEADER"]
    for kind, label, vals in rows:
        if kind == "HEADER":
            out_values.append([label] + [""] * (len(months) + 2))
        else:
            total = sum(vals)
            pct = abs(total) / base_receita * 100
            out_values.append([label] + [fmt_brl(v) for v in vals] + [fmt_brl(total), f"{pct:.1f}%"])
        row_types.append(kind)

    try:
        out_ws = sh.worksheet(OUT_TAB)
        out_ws.clear()
    except Exception:
        out_ws = sh.add_worksheet(title=OUT_TAB, rows=len(out_values) + 5, cols=len(header_row) + 2)

    out_ws.update(values=out_values, range_name="A1")

    requests = []
    sheet_id = out_ws.id
    for r_idx, kind in enumerate(row_types):
        if kind == "HEADER":
            requests.append({
                "repeatCell": {
                    "range": {"sheetId": sheet_id, "startRowIndex": r_idx, "endRowIndex": r_idx + 1},
                    "cell": {"userEnteredFormat": {"textFormat": {"bold": True}, "backgroundColor": {"red": 0.9, "green": 0.9, "blue": 0.95}}},
                    "fields": "userEnteredFormat(textFormat,backgroundColor)",
                }
            })
        elif kind == "SUBTOTAL":
            requests.append({
                "repeatCell": {
                    "range": {"sheetId": sheet_id, "startRowIndex": r_idx, "endRowIndex": r_idx + 1},
                    "cell": {"userEnteredFormat": {"textFormat": {"bold": True}}},
                    "fields": "userEnteredFormat.textFormat",
                }
            })
    if requests:
        sheets_api.spreadsheets().batchUpdate(spreadsheetId=sh.id, body={"requests": requests}).execute()

    print(f"DRE_Mensal escrito: {len(out_values)} linhas x {len(header_row)} colunas")
    orig_liquido = data.get("Salário Liquido", [0.0] * len(months))[-1]
    print(f"Reconciliação Receita Líquida (última coluna): calc={totals['receita_liquida'][-1]:.2f} orig={orig_liquido:.2f}")
    print(f"Custos Fixos (total período): {fmt_brl(sum(totals['fixo']))}")
    print(f"Custos Variáveis (total período, incl. cartão por tipo): {fmt_brl(sum(totals['variavel']))}")
    print(f"Margem Líquida (mês ref {months[REF_MONTH_INDEX]}): {fmt_brl(totals['margem_liquida'][REF_MONTH_INDEX])}")


if __name__ == "__main__":
    main()
