from finlib import (
    get_clients, fmt_brl, PROJ_TAB, CONTAS_TAB, FLUXO_APTO_TAB, DESPESAS_CASA_TAB, REF_MONTH_INDEX,
    CARD_REF_MONTH_INDEX,
    load_projecao, load_card_items, cartao_por_tipo, load_cartao_obra_mensal, load_pix_obra_mensal, compute_totals,
    apply_despesas_casa_handover, neutralize_investimentos_row, compute_financiamento_obra, red_negative_rule,
)
from build_investimentos import load_investimentos, get_fundo_obra_balance, SRC_TAB as INVEST_TAB

OUT_TAB = "Fluxo_Caixa"


def main():
    sh, sheets_api = get_clients()
    contas_ws = sh.worksheet(CONTAS_TAB)
    proj_ws = sh.worksheet(PROJ_TAB)
    apto_ws = sh.worksheet(FLUXO_APTO_TAB)
    despesas_casa_ws = sh.worksheet(DESPESAS_CASA_TAB)

    months, proj_data = load_projecao(proj_ws)
    apply_despesas_casa_handover(months, proj_data, despesas_casa_ws)
    # Captura o lançamento bruto de 'Investimentos' (posição inicial do fundo da obra,
    # ~R$144k em jul./26) antes de zerá-lo — usado como saldo de abertura do Saldo
    # Acumulado abaixo (ver extract_dashboard_data.py, mesma lógica).
    raw_investimentos = list(proj_data.get("Investimentos", []))
    investimento_posicao_inicial = next((abs(v) for v in raw_investimentos if v), 0.0)
    investimento_mes_inicial_idx = next((i for i, v in enumerate(raw_investimentos) if v), 0)
    neutralize_investimentos_row(proj_data)
    n = len(months)

    card_items = load_card_items(contas_ws)
    ctipo = cartao_por_tipo(card_items, n, ref_month_index=CARD_REF_MONTH_INDEX)
    cartao_obra_mensal = load_cartao_obra_mensal(apto_ws, months)
    obra_pix_mensal = load_pix_obra_mensal(apto_ws, months)
    totals = compute_totals(months, proj_data, ctipo, cartao_obra_mensal, obra_pix_mensal)

    invest_categorias, _invest_total = load_investimentos(sh.worksheet(INVEST_TAB))
    fundo_obra_balance = get_fundo_obra_balance(invest_categorias)
    fin_kwargs = {"investimento_total": fundo_obra_balance} if fundo_obra_balance is not None else {}
    if investimento_posicao_inicial:
        fin_kwargs["historical_start_balance"] = investimento_posicao_inicial
        fin_kwargs["historical_start_index"] = investimento_mes_inicial_idx
    # Conta corrente e fundo da obra são a mesma reserva na prática: o extrato mostra
    # resgate automático do fundo cobrindo CADA saída (cartão inteiro, boletos, Pix — não
    # só a parte da obra), e a Gabriela recompõe depois via Pix (linha "Reembolso
    # Gabriela", dentro de entradas) quando ela recebe o salário dela. Por isso o "Saldo
    # Acumulado" é a própria trajetória do fundo (saidas_caixa inclui de volta
    # Fixo_Gabi/Moradia_Gabi, que na prática também saem dessa reserva).
    fin = compute_financiamento_obra(months, totals["entradas"], totals["saidas_caixa"], **fin_kwargs)
    saldo_acumulado = fin["saldo_investimento"]

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
    add_row("SUBTOTAL", "Total Entradas (Receita Líquida)", totals["entradas"])
    add_row("REF", "  do qual: Reembolso Gabriela (Pix quando ela recebe o salário dela)", proj_data.get("Reembolso Gabriela", [0.0] * n))

    add_section("(-) SAÍDAS — CUSTOS FIXOS DA CASA (GABI RECOMPÕE DEPOIS, MAS SAI DO FUNDO AGORA)")
    add_row("LINE", "Moradia Saúde (Apto devolvido em ago./26 — resta só Cartão Crédito Casa)", totals["moradia_gabi"])
    add_row("LINE", "Financiamento/Condomínio/IPTU/Energia/Gás/Internet VM + Seguro Taos", totals["fixo_gabi"])
    add_row("SUBTOTAL", "Subtotal Custos Fixos da Casa", [a + b for a, b in zip(totals["moradia_gabi"], totals["fixo_gabi"])])

    add_section("(-) SAÍDAS — CUSTOS FIXOS (PESSOAIS)")
    add_row("SUBTOTAL", "Subtotal Custos Fixos", totals["fixo"])

    add_section("(-) SAÍDAS — CUSTOS VARIÁVEIS")
    add_row("LINE", "Variáveis (exceto cartão)", totals["variavel_sem_cartao"])
    for tipo, vals in sorted(ctipo.items(), key=lambda kv: -sum(kv[1])):
        add_row("LINE", f"Cartão Pessoal — {tipo}", vals)
    add_row("SUBTOTAL", "Subtotal Custos Variáveis", totals["variavel"])

    add_section("(-) SAÍDAS — CUSTOS VARIÁVEIS OBRA")
    add_row("LINE", "Pix Pagamentos Obra", totals["obra_pix"])
    add_row("LINE", "Cartão Obra (parcelas — Fluxo_Apto_Realizado, linha 55)", cartao_obra_mensal)
    add_row("SUBTOTAL", "Subtotal Variável Obra", totals["variavel_obra"])

    add_row("TOTAL", "Total Saídas (caixa real — inclui custos fixos da casa)", totals["saidas_caixa"])

    add_section("(=) SALDO LÍQUIDO DE CAIXA (ENTRADAS − SAÍDAS REAIS)")
    add_row("TOTAL", "Saldo Líquido de Caixa", totals["saldo_liquido_caixa"])

    add_section("(=) RESULTADO FINAL DO MÊS")
    add_row("TOTAL", f"Saldo Acumulado (conta corrente + fundo da obra — mesma reserva, ancorado no saldo real de {months[REF_MONTH_INDEX]})", saldo_acumulado)

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
    print(f"Saídas caixa real (mês ref {months[REF_MONTH_INDEX]}): {fmt_brl(totals['saidas_caixa'][REF_MONTH_INDEX])}")
    print(f"Saldo Líquido de Caixa (mês ref {months[REF_MONTH_INDEX]}): {fmt_brl(totals['saldo_liquido_caixa'][REF_MONTH_INDEX])}")
    print(f"Saldo Acumulado (conta+fundo, mês ref, ancorado no saldo real): {fmt_brl(saldo_acumulado[REF_MONTH_INDEX])}")
    print(f"Saldo Acumulado (último mês, {months[-1]}): {fmt_brl(saldo_acumulado[-1])}")


if __name__ == "__main__":
    main()
