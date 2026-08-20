from finlib import (
    get_clients, fmt_brl, PROJ_TAB, CONTAS_TAB, REF_MONTH_INDEX,
    load_projecao, load_card_items, distribute, cartao_por_tipo, compute_totals,
)

OUT_TAB = "Fluxo_Caixa"
SALDO_INICIAL = 0.0  # TODO: substituir pelo saldo real em conta no mês de referência


def main():
    sh, sheets_api = get_clients()
    contas_ws = sh.worksheet(CONTAS_TAB)
    proj_ws = sh.worksheet(PROJ_TAB)

    months, proj_data = load_projecao(proj_ws)
    n = len(months)

    card_items = load_card_items(contas_ws)
    personal_items = [it for it in card_items if it["tipo"] != "Obra Apto"]
    obra_items = [it for it in card_items if it["tipo"] == "Obra Apto"]
    personal_dist = distribute(personal_items, n)
    obra_dist = distribute(obra_items, n)
    ctipo = cartao_por_tipo(card_items, n)

    totals = compute_totals(months, proj_data, ctipo)
    pix_obra = proj_data.get("Pix Pagamentos Obra", [0.0] * n)

    total_despesas = [
        f + v + o for f, v, o in zip(totals["fixo"], totals["variavel"], totals["obra"])
    ]
    saldo_mes = [
        rl + orc + td + inv
        for rl, orc, td, inv in zip(totals["receita_liquida"], totals["outras_receitas"], total_despesas, totals["investimentos"])
    ]
    saldo_acumulado = []
    running = SALDO_INICIAL
    for v in saldo_mes:
        running += v
        saldo_acumulado.append(running)

    # ---- assemble sheet ----
    header = ["Linha"] + months + ["TOTAL"]
    out_values = [header]
    row_kinds = ["HEADER"]

    def add_row(kind, label, vals):
        total = sum(vals)
        out_values.append([label] + [fmt_brl(v) for v in vals] + [fmt_brl(total)])
        row_kinds.append(kind)

    def add_section(label):
        out_values.append([label] + [""] * (n + 1))
        row_kinds.append("SECTION")

    add_section("RECEITA")
    add_row("LINE", "Receita Líquida (Salário)", totals["receita_liquida"])
    add_row("LINE", "Outras Receitas / Aportes (Gabriela)", totals["outras_receitas"])

    add_section("(-) CUSTOS FIXOS")
    add_row("SUBTOTAL", "Subtotal Custos Fixos", totals["fixo"])

    add_section("(-) CUSTOS VARIÁVEIS")
    add_row("LINE", "Variáveis (exceto cartão)", totals["variavel_sem_cartao"])
    for tipo, vals in sorted(ctipo.items(), key=lambda kv: -sum(kv[1])):
        add_row("LINE", f"Cartão Pessoal — {tipo}", vals)
    add_row("SUBTOTAL", "Subtotal Custos Variáveis", totals["variavel"])

    add_section("(-) OBRA (REFORMA)")
    add_row("LINE", "Pix Pagamentos Obra", pix_obra)
    add_row("SUBTOTAL", "Subtotal Obra", totals["obra"])

    add_section("(-) INVESTIMENTOS")
    add_row("LINE", "Investimentos", totals["investimentos"])

    add_section("REFERÊNCIA — cartão de obra, já contabilizado em Obra_Consolidado, NÃO somado no total abaixo")
    for it, vals in obra_dist:
        label = f"{it['desc']} [Obra Apto — {it['banco']}]"
        add_row("REF", label, vals)

    add_section("(=) RESULTADO")
    add_row("TOTAL", "Total Despesas (Fixos+Variáveis+Obra)", total_despesas)
    add_row("TOTAL", "Saldo do Mês", saldo_mes)
    add_row("TOTAL", f"Saldo Acumulado (saldo inicial={fmt_brl(SALDO_INICIAL)})", saldo_acumulado)

    try:
        out_ws = sh.worksheet(OUT_TAB)
        out_ws.clear()
    except Exception:
        out_ws = sh.add_worksheet(title=OUT_TAB, rows=len(out_values) + 5, cols=len(header) + 2)

    out_ws.update(values=out_values, range_name="A1")

    sheet_id = out_ws.id
    requests = []
    for r_idx, kind in enumerate(row_kinds):
        if kind in ("HEADER", "SECTION"):
            requests.append({
                "repeatCell": {
                    "range": {"sheetId": sheet_id, "startRowIndex": r_idx, "endRowIndex": r_idx + 1},
                    "cell": {"userEnteredFormat": {"textFormat": {"bold": True}, "backgroundColor": {"red": 0.9, "green": 0.9, "blue": 0.95}}},
                    "fields": "userEnteredFormat(textFormat,backgroundColor)",
                }
            })
        elif kind in ("SUBTOTAL", "TOTAL"):
            requests.append({
                "repeatCell": {
                    "range": {"sheetId": sheet_id, "startRowIndex": r_idx, "endRowIndex": r_idx + 1},
                    "cell": {"userEnteredFormat": {"textFormat": {"bold": True}}},
                    "fields": "userEnteredFormat.textFormat",
                }
            })
        elif kind == "REF":
            requests.append({
                "repeatCell": {
                    "range": {"sheetId": sheet_id, "startRowIndex": r_idx, "endRowIndex": r_idx + 1},
                    "cell": {"userEnteredFormat": {"textFormat": {"italic": True, "foregroundColor": {"red": 0.5, "green": 0.5, "blue": 0.5}}}},
                    "fields": "userEnteredFormat.textFormat",
                }
            })
    if requests:
        sheets_api.spreadsheets().batchUpdate(spreadsheetId=sh.id, body={"requests": requests}).execute()

    print(f"Fluxo_Caixa escrito: {len(out_values)} linhas x {len(header)} colunas")
    print(f"Itens cartão pessoal: {len(personal_items)} | Itens obra (referência): {len(obra_items)}")
    print(f"Total Despesas (último mês, {months[-1]}): {fmt_brl(total_despesas[-1])}")
    print(f"Saldo do Mês (último mês): {fmt_brl(saldo_mes[-1])}")
    print(f"Saldo Acumulado (último mês, saldo inicial=0): {fmt_brl(saldo_acumulado[-1])}")


if __name__ == "__main__":
    main()
