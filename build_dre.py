from finlib import (
    get_clients, fmt_brl, GROUPS, LABEL_OVERRIDES, PROJ_TAB, CONTAS_TAB, FLUXO_APTO_TAB,
    DESPESAS_CASA_TAB, REF_MONTH_INDEX,
    load_projecao, load_card_items, cartao_por_tipo, load_cartao_obra_mensal, compute_totals,
    apply_despesas_casa_handover, apply_investimentos_sign, red_negative_rule,
)

OUT_TAB = "DRE_Mensal"

GRUPO_LABEL = {
    "DEDUCOES": "Dedução", "MORADIA_GABI": "Informativo (Gabi)", "FIXO": "Fixo",
    "VARIAVEL": "Variável", "VARIAVEL_OBRA": "Variável Obra", "RECEITA_BRUTA": "Receita",
    "OUTRAS_RECEITAS": "Receita", "INVESTIMENTOS": "Investimento",
}

SUBTOTAL_LABEL = {
    "DEDUCOES": "Salário Líquido", "MORADIA_GABI": "Subtotal Moradia (Gabi)",
    "FIXO": "Subtotal Despesas Fixas", "VARIAVEL": "Subtotal Despesas Variáveis",
    "VARIAVEL_OBRA": "Subtotal Despesas Variável Obra", "OUTRAS_RECEITAS": "Subtotal Outras Receitas",
    "INVESTIMENTOS": "Subtotal Investimentos",
}


def build_rows(months, data, cartao_tipo, cartao_obra_mensal, totals):
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
            final_rows.append(("HEADER", label, None, "", None))
            j = i + 1
            grp_key = None
            while j < len(GROUPS) and GROUPS[j][1] is not None:
                sub_label, sub_group = GROUPS[j]
                grp_key = sub_group
                vals = data.get(sub_label, [0.0] * n)
                display_label = LABEL_OVERRIDES.get(sub_label, sub_label.replace("#2", ""))
                final_rows.append(("LINE", display_label, vals, GRUPO_LABEL.get(sub_group, ""), sub_group))
                j += 1
            if grp_key == "VARIAVEL":
                for tipo, vals in sorted(cartao_tipo.items(), key=lambda kv: -sum(kv[1])):
                    final_rows.append(("LINE", f"Cartão Pessoal — {tipo}", vals, "Variável", "VARIAVEL"))
                final_rows.append(("SUBTOTAL", SUBTOTAL_LABEL["VARIAVEL"], totals["variavel"], "Variável", "VARIAVEL"))
            elif grp_key == "VARIAVEL_OBRA":
                final_rows.append(("LINE", "Cartão Obra (parcelas — Fluxo_Apto_Realizado)", cartao_obra_mensal, "Variável Obra", "VARIAVEL_OBRA"))
                final_rows.append(("SUBTOTAL", SUBTOTAL_LABEL["VARIAVEL_OBRA"], totals["variavel_obra"], "Variável Obra", "VARIAVEL_OBRA"))
            elif grp_key == "RECEITA_BRUTA":
                pass  # linha única — subtotal seria redundante
            elif grp_key == "DEDUCOES":
                # "Salário Líquido" = Salário Bruto + Deduções, não a soma das deduções sozinha.
                final_rows.append(("SUBTOTAL", SUBTOTAL_LABEL["DEDUCOES"], totals["receita_liquida"], GRUPO_LABEL.get(grp_key, ""), grp_key))
            elif grp_key is not None:
                final_rows.append(("SUBTOTAL", SUBTOTAL_LABEL.get(grp_key, "Subtotal"), group_sums[grp_key], GRUPO_LABEL.get(grp_key, ""), grp_key))
            i = j
        else:
            i += 1

    final_rows.append(("HEADER", "(=) MARGEM LÍQUIDA (SEM OBRA)", None, "", None))
    margem_sem_obra = [ml - vo for ml, vo in zip(totals["margem_liquida"], totals["variavel_obra"])]
    final_rows.append(("SUBTOTAL", "Margem Líquida (Entradas − Saídas, exceto Obra)", margem_sem_obra, "Resultado", "MARGEM"))

    return final_rows


def main():
    sh, sheets_api = get_clients()
    src_ws = sh.worksheet(PROJ_TAB)
    contas_ws = sh.worksheet(CONTAS_TAB)
    apto_ws = sh.worksheet(FLUXO_APTO_TAB)
    despesas_casa_ws = sh.worksheet(DESPESAS_CASA_TAB)
    months, data = load_projecao(src_ws)
    apply_despesas_casa_handover(months, data, despesas_casa_ws)
    apply_investimentos_sign(data)
    card_items = load_card_items(contas_ws)
    ctipo = cartao_por_tipo(card_items, len(months))
    cartao_obra_mensal = load_cartao_obra_mensal(apto_ws, months)
    totals = compute_totals(months, data, ctipo, cartao_obra_mensal)
    rows = build_rows(months, data, ctipo, cartao_obra_mensal, totals)

    base_receita = sum(abs(v) for v in totals["receita_liquida"]) or 1.0

    header_row = ["Linha", "Classificação"] + months + ["TOTAL", "% peso (sobre Receita Líquida)"]
    out_values = [header_row]
    row_types = ["HEADER"]
    for kind, label, vals, classif, _grp in rows:
        if kind == "HEADER":
            out_values.append([label, ""] + [""] * (len(months) + 2))
        else:
            total = sum(vals)
            pct = abs(total) / base_receita * 100
            out_values.append([label, classif] + [fmt_brl(v) for v in vals] + [fmt_brl(total), f"{pct:.1f}%"])
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
    requests.append(red_negative_rule(sheet_id, len(out_values), len(header_row)))
    if requests:
        sheets_api.spreadsheets().batchUpdate(spreadsheetId=sh.id, body={"requests": requests}).execute()

    print(f"DRE_Mensal escrito: {len(out_values)} linhas x {len(header_row)} colunas")
    orig_liquido = data.get("Salário Liquido", [0.0] * len(months))[-1]
    print(f"Reconciliação Receita Líquida (última coluna): calc={totals['receita_liquida'][-1]:.2f} orig={orig_liquido:.2f}")
    print(f"Custos Fixos (total período): {fmt_brl(sum(totals['fixo']))}")
    print(f"Custos Variáveis (total período, cartão pessoal incl.): {fmt_brl(sum(totals['variavel']))}")
    print(f"Custos Variável Obra (total período, Pix+Cartão): {fmt_brl(sum(totals['variavel_obra']))}")
    print(f"Cartão Obra (mês ref {months[REF_MONTH_INDEX]}): {fmt_brl(cartao_obra_mensal[REF_MONTH_INDEX])}")
    print(f"Margem Líquida (mês ref {months[REF_MONTH_INDEX]}): {fmt_brl(totals['margem_liquida'][REF_MONTH_INDEX])}")


if __name__ == "__main__":
    main()
