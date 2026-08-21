from finlib import (
    get_clients, fmt_brl, PROJ_TAB, CONTAS_TAB, FLUXO_APTO_TAB, REF_MONTH_INDEX,
    load_projecao, load_card_items, cartao_por_tipo, load_cartao_obra_mensal, compute_totals, red_negative_rule,
)

OUT_TAB = "Fluxo_Caixa"


def main():
    sh, sheets_api = get_clients()
    contas_ws = sh.worksheet(CONTAS_TAB)
    proj_ws = sh.worksheet(PROJ_TAB)
    apto_ws = sh.worksheet(FLUXO_APTO_TAB)

    months, proj_data = load_projecao(proj_ws)
    n = len(months)

    card_items = load_card_items(contas_ws)
    ctipo = cartao_por_tipo(card_items, n)
    cartao_obra_mensal = load_cartao_obra_mensal(apto_ws, months)
    totals = compute_totals(months, proj_data, ctipo, cartao_obra_mensal)

    # Fluxo de caixa parte diretamente da DRE: Entradas − Saídas = Saldo Líquido.
    # Investimentos entra depois do saldo líquido operacional (não é despesa recorrente).
    saldo_mes = [sl + inv for sl, inv in zip(totals["saldo_liquido"], totals["investimentos"])]
    saldo_acumulado = []
    running = 0.0
    for v in saldo_mes:
        running += v
        saldo_acumulado.append(running)

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

    add_section("(+) ENTRADAS")
    add_row("LINE", "Receita Líquida (Salário)", totals["receita_liquida"])
    add_row("LINE", "Outras Receitas / Aportes (Gabriela)", totals["outras_receitas"])
    add_row("SUBTOTAL", "Total Entradas", totals["entradas"])

    add_section("MORADIA SAÚDE — PAGO POR GABI (INFORMATIVO, NÃO ENTRA NAS SAÍDAS)")
    add_row("REF", "Aluguel + Condomínio + Enel + Internet + Cartão Casa", totals["moradia_gabi"])

    add_section("(-) SAÍDAS — CUSTOS FIXOS")
    add_row("SUBTOTAL", "Subtotal Custos Fixos", totals["fixo"])

    add_section("(-) SAÍDAS — CUSTOS VARIÁVEIS")
    add_row("LINE", "Variáveis (exceto cartão)", totals["variavel_sem_cartao"])
    for tipo, vals in sorted(ctipo.items(), key=lambda kv: -sum(kv[1])):
        add_row("LINE", f"Cartão Pessoal — {tipo}", vals)
    add_row("LINE", "Cartão Obra (parcelas — Fluxo_Apto_Realizado, linha 55)", cartao_obra_mensal)
    add_row("SUBTOTAL", "Subtotal Custos Variáveis", totals["variavel"])

    add_row("TOTAL", "Total Saídas", totals["saidas"])

    add_section("(=) SALDO LÍQUIDO (ENTRADAS − SAÍDAS)")
    add_row("TOTAL", "Saldo Líquido", totals["saldo_liquido"])

    add_section("(-) INVESTIMENTOS")
    add_row("LINE", "Investimentos", totals["investimentos"])

    add_section("(=) RESULTADO FINAL DO MÊS")
    add_row("TOTAL", "Saldo do Mês (após investimentos)", saldo_mes)
    add_row("TOTAL", "Saldo Acumulado", saldo_acumulado)

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
    requests.append(red_negative_rule(sheet_id, len(out_values), len(header)))
    if requests:
        sheets_api.spreadsheets().batchUpdate(spreadsheetId=sh.id, body={"requests": requests}).execute()

    print(f"Fluxo_Caixa escrito: {len(out_values)} linhas x {len(header)} colunas")
    print(f"Entradas (mês ref {months[REF_MONTH_INDEX]}): {fmt_brl(totals['entradas'][REF_MONTH_INDEX])}")
    print(f"Saídas (mês ref {months[REF_MONTH_INDEX]}): {fmt_brl(totals['saidas'][REF_MONTH_INDEX])}")
    print(f"Saldo Líquido (mês ref {months[REF_MONTH_INDEX]}): {fmt_brl(totals['saldo_liquido'][REF_MONTH_INDEX])}")
    print(f"Saldo Acumulado (último mês, {months[-1]}): {fmt_brl(saldo_acumulado[-1])}")


if __name__ == "__main__":
    main()
