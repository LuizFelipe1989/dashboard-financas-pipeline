import json
from collections import OrderedDict

from finlib import (
    get_clients, PROJ_TAB, CONTAS_TAB, FLUXO_APTO_TAB, DESPESAS_CASA_TAB, REF_MONTH_INDEX,
    load_projecao, load_card_items, cartao_por_tipo, load_cartao_obra_mensal, compute_totals, fmt_brl,
    apply_despesas_casa_handover, neutralize_investimentos_row, compute_financiamento_obra,
    variavel_disponivel_para_obra, _MES_ABREV_PARA_NOME,
)
from build_dre import build_rows
from build_obra import load_items_and_colors, load_month_window, load_janela_pix_manual, payment_summary, SRC_TAB as OBRA_TAB
from build_gastos_tipo import group_by_natureza, NATUREZA_ORDEM
from build_investimentos import (
    load_investimentos, ensure_live_quotes, get_fundo_obra_balance,
    compute_rentabilidade_ativa, compute_highlights, SRC_TAB as INVEST_TAB,
)

OUT_PATH = "dashboard_data.json"


def dre_detalhe_full(months, data, ctipo, cartao_obra_mensal, totals):
    """Sectioned line-item list (kind HEADER/LINE/SUBTOTAL) across ALL months, reusing
    build_dre.build_rows() so the dashboard's DRE detail table matches the DRE_Mensal
    sheet's own structure. `grupo` (raw group key) is kept for internal filtering (e.g.
    Composição das Despesas) but is not meant to be rendered as its own column.

    Moradia Saúde (pago pela Gabi) fica de fora da tabela do dashboard — é puramente
    informativo, não entra na margem, e só teria as próprias parcelas do Cartão Crédito
    Casa; segue disponível na aba DRE_Mensal (build_rows() não muda) para quem quiser
    o detalhe completo."""
    rows = build_rows(months, data, ctipo, cartao_obra_mensal, totals)
    out = []
    for kind, label, vals, _classif, grp in rows:
        if grp == "MORADIA_GABI" or (kind == "HEADER" and "MORADIA SAÚDE" in label):
            continue
        out.append({"kind": kind, "label": label, "grupo": grp, "vals": list(vals) if vals is not None else None})
    return out


def build_alerts(months, ref, totals, cartao_obra_mensal, obra, gastos_natureza, saldo_investimento_series, saldo_acumulado=None, invest_search_from=0):
    """Regras de bom senso sobre os dados frescos — mesma lógica que o agente da
    routine diária aplicaria; roda aqui também para manter o dashboard com alertas
    sempre que os scripts locais forem executados, não só na rotina de nuvem.
    `ref` aqui é o mês em foco (dash_ref = próximo mês a acontecer), não o mês âncora."""
    alerts = []

    if saldo_acumulado is not None:
        saldo_mes_ref = saldo_acumulado[ref]
        saldo_mes_anterior = saldo_acumulado[ref - 1] if ref > 0 else None
        if saldo_mes_ref < 0:
            alerts.append({"icon": "🚨", "text": f"Projeção de caixa fica negativa em {months[ref]}: R$ {fmt_brl(saldo_mes_ref)} acumulado — inclui a fatura do cartão de 10/{months[ref].split('./')[0]} (consumo de {months[ref-1]}). Vale antecipar uma decisão antes desse mês."})
        elif saldo_mes_anterior is not None and saldo_mes_ref < saldo_mes_anterior:
            queda = saldo_mes_ref - saldo_mes_anterior
            alerts.append({"icon": "📉", "text": f"Caixa projetado cai R$ {fmt_brl(abs(queda))} em {months[ref]} (fatura de 10/{months[ref].split('./')[0]} inclusa) — acumulado vai a R$ {fmt_brl(saldo_mes_ref)}."})

    margem = totals["margem_liquida"][ref]
    if margem < 0:
        alerts.append({"icon": "⚠️", "text": f"Margem líquida negativa em {months[ref]}: R$ {fmt_brl(margem)} — as saídas do mês superam as entradas."})

    cartao_obra_ref = abs(cartao_obra_mensal[ref])
    receita_ref = totals["receita_liquida"][ref]
    if receita_ref and cartao_obra_ref >= receita_ref * 0.6:
        pct = cartao_obra_ref / receita_ref * 100
        alerts.append({"icon": "💳", "text": f"Parcela do cartão da obra em {months[ref]} (fatura 10/{months[ref].split('./')[0]}) consome {pct:.0f}% do salário líquido do mês."})

    for c in obra["por_classificacao"]:
        if c["previsto"] and c["pago"] / c["previsto"] > 1.0:
            pct = c["pago"] / c["previsto"] * 100
            alerts.append({"icon": "🏗️", "text": f"Obra \"{c['classificacao']}\" já pagou {pct:.0f}% do previsto (estourou o orçamento)."})

    disc_total = sum(acc["total"] for acc in gastos_natureza.get("Discricionário", {}).values())
    var_total = abs(totals["variavel"][ref]) or 1.0
    if disc_total / var_total > 0.15:
        alerts.append({"icon": "🔀", "text": f"Gastos discricionários (não recorrentes) somam R$ {fmt_brl(disc_total)} este mês — vale revisar."})

    if saldo_investimento_series:
        idx0 = next((i for i in range(invest_search_from, len(saldo_investimento_series)) if saldo_investimento_series[i] <= 0), None)
        if idx0 is not None and idx0 < len(months):
            alerts.append({"icon": "📉", "text": f"No ritmo atual, o investimento usado para cobrir a parcela da obra se esgota por volta de {months[idx0]}."})

    return alerts[:6]


def main():
    sh, sheets_api = get_clients()

    proj_ws = sh.worksheet(PROJ_TAB)
    contas_ws = sh.worksheet(CONTAS_TAB)
    apto_ws = sh.worksheet(FLUXO_APTO_TAB)
    despesas_casa_ws = sh.worksheet(DESPESAS_CASA_TAB)
    months, proj_data = load_projecao(proj_ws)
    apply_despesas_casa_handover(months, proj_data, despesas_casa_ws)
    # Captura o lançamento bruto de 'Investimentos' (posição inicial do fundo da obra,
    # ~R$144k em jul./26) antes de zerá-lo — usado só como ponto histórico no gráfico
    # de Financiamento da Obra, não entra em nenhum total da DRE.
    raw_investimentos = list(proj_data.get("Investimentos", []))
    investimento_posicao_inicial = next((abs(v) for v in raw_investimentos if v), 0.0)
    investimento_mes_inicial_idx = next((i for i, v in enumerate(raw_investimentos) if v), 0)
    neutralize_investimentos_row(proj_data)
    n = len(months)
    ref = REF_MONTH_INDEX
    # Ago./26 já foi realizado (saldo real ancorado nele) — o mês em foco no dashboard
    # (KPIs, DRE Resumida, alertas) passa a ser o seguinte: set./26, que ainda inclui a
    # fatura do cartão de 10/set (consumo de agosto, abertura já imputada) e ainda não
    # aconteceu de fato. O anchor/financiamento continuam usando `ref` (ago./26) sem
    # mudança — é o ponto real conhecido (saldo do extrato).
    dash_ref = ref + 1

    card_items = load_card_items(contas_ws)
    ctipo = cartao_por_tipo(card_items, n)
    cartao_obra_mensal = load_cartao_obra_mensal(apto_ws, months)
    totals = compute_totals(months, proj_data, ctipo, cartao_obra_mensal)

    # Investimentos carregado cedo pra alimentar o saldo real (ao vivo) do fundo que
    # garante o limite do cartão da obra, usado no financiamento abaixo.
    invest_ws = sh.worksheet(INVEST_TAB)
    invest_categorias, invest_total = load_investimentos(invest_ws)
    invest_tickers = sorted({it["ticker"] for cat in invest_categorias for it in cat["itens"] if it["ticker"]})
    invest_quotes = ensure_live_quotes(sh, sheets_api, invest_tickers)
    invest_rent_ativa = compute_rentabilidade_ativa(invest_categorias)
    fundo_obra_balance = get_fundo_obra_balance(invest_categorias)

    # Financiamento da obra e Fluxo de Caixa compartilham a mesma lógica de saque —
    # é o que faz o saldo final de um bater com o do outro (double-check pedido). O saldo
    # inicial do fundo (~R$144k) foi consumido ao longo de 2026; usa-se o saldo atual da
    # aba Investimentos como ponto de partida da projeção, não mais um valor fixo no código.
    fin_kwargs = {"investimento_total": fundo_obra_balance} if fundo_obra_balance is not None else {}
    variavel_obra_calc = variavel_disponivel_para_obra(proj_data, totals, n)
    fin = compute_financiamento_obra(
        months, totals["receita_liquida"], variavel_obra_calc, cartao_obra_mensal, totals["obra_pix"], **fin_kwargs
    )
    saldo_mes = [sl + inv + sq for sl, inv, sq in zip(totals["saldo_liquido"], totals["investimentos"], fin["saque_mensal"])]
    raw_cum = []
    running = 0.0
    for v in saldo_mes:
        running += v
        raw_cum.append(running)
    anchor = raw_cum[ref] - fin["saldo_disponivel_imediato"]
    saldo_acumulado = [v - anchor for v in raw_cum]

    # ---- DRE resumo (mês em foco: dash_ref = set./26, o próximo a acontecer) — Custo
    # Obra separado da Margem Líquida, já que a obra tem prazo pra terminar e não
    # deveria diluir a margem recorrente.
    receita_liquida_ref = totals["receita_liquida"][dash_ref]
    custos_fixos_ref = totals["fixo"][dash_ref]
    custos_variaveis_ref = totals["variavel"][dash_ref]
    custo_obra_ref = totals["variavel_obra"][dash_ref]
    margem_sem_obra_ref = receita_liquida_ref + custos_fixos_ref + custos_variaveis_ref
    base_receita = abs(receita_liquida_ref) or 1.0
    dre_resumo = {
        "receita_liquida": receita_liquida_ref,
        "custos_fixos": custos_fixos_ref,
        "custos_fixos_pct": abs(custos_fixos_ref) / base_receita * 100,
        "custos_variaveis": custos_variaveis_ref,
        "custos_variaveis_pct": abs(custos_variaveis_ref) / base_receita * 100,
        "custo_obra": custo_obra_ref,
        "custo_obra_pct": abs(custo_obra_ref) / base_receita * 100,
        "margem_liquida": margem_sem_obra_ref,
        "margem_liquida_pct": margem_sem_obra_ref / base_receita * 100,
    }
    dre_detalhe = dre_detalhe_full(months, proj_data, ctipo, cartao_obra_mensal, totals)

    # ---- Gastos por Tipo: Fixo Mensal / Parcelado / Discricionário, com subtotais ----
    by_natureza = group_by_natureza(card_items)
    grand_total_cartao = sum(it["valor_parcela"] for it in card_items) or 1.0
    gastos_por_natureza = []
    for nat in NATUREZA_ORDEM:
        tipos = by_natureza[nat]
        nat_total = sum(acc["total"] for acc in tipos.values())
        gastos_por_natureza.append({
            "natureza": nat,
            "total": nat_total,
            "pct": nat_total / grand_total_cartao * 100,
            "tipos": [
                {"tipo": tipo, "total": acc["total"], "pct": acc["total"] / grand_total_cartao * 100, "n_itens": len(acc["itens"])}
                for tipo, acc in sorted(tipos.items(), key=lambda kv: -kv[1]["total"])
            ],
        })

    # ---- Obra ----
    obra_ws = sh.worksheet(OBRA_TAB)
    items = load_items_and_colors(sh, sheets_api, obra_ws)
    grand_previsto = sum(i["previsto"] for i in items)
    grand_pago = sum(i["pago"] for i in items)
    grand_pendente = sum(i["pendente"] for i in items)
    grand_futuro = sum(i["futuro"] for i in items)

    by_class = OrderedDict()
    for it in items:
        c = it["classificacao"] or "(sem classificação)"
        acc = by_class.setdefault(c, {
            "previsto": 0.0, "pago": 0.0, "pendente": 0.0, "futuro": 0.0,
            "pendente_pix": 0.0, "pendente_cartao": 0.0,
        })
        acc["previsto"] += it["previsto"]
        acc["pago"] += it["pago"]
        acc["pendente"] += it["pendente"]
        acc["futuro"] += it["futuro"]
        # Pix não tem um "futuro com data" separado como o Cartão (parcela agendada) —
        # rosa (pendente) e azul (futuro) são os dois estados de "ainda não pago"; ao
        # abrir o mês com a janela de pagamentos pronta, os dois contam como a pagar
        # (bate com a tabela "Janela de Pagamentos AI:AK", que reúne exatamente os
        # itens hoje classificados como azul/futuro). Cartão segue só "futuro" (parcela
        # ainda não lançada) como o pendente em aberto — "Pendente Cartão" reaproveita
        # esse bucket.
        modalidade = it["modalidade"].strip().lower()
        if modalidade == "pix":
            acc["pendente_pix"] += it["pendente"] + it["futuro"]
        elif modalidade == "cartão":
            acc["pendente_cartao"] += it["futuro"]
    class_rollup = [{"classificacao": c, **acc} for c, acc in sorted(by_class.items(), key=lambda kv: -kv[1]["previsto"])]

    pagamentos = payment_summary(items)
    # "Cartão a vencer" usa a classificação por cor das células do item table (a mesma
    # fonte do totalizador "Pendente Cartão" da tabela por classificação) — soma de
    # Fluxo_Apto_Realizado!linha 55 a partir do mês de referência SUPERESTIMA o valor
    # porque inclui o mês de referência inteiro mesmo quando a parcela desse mês já foi
    # paga (cartão nunca fica "pendente/rosa", só "pago/verde" ou "futuro/branco" —
    # verificado: pago R$29.407,90 + futuro R$143.334,00 ≈ R$172.741,90 soma toda a
    # linha 55 do período, R$172.160,50; a diferença pro "a vencer" some quando o mês
    # de referência já pago some do lado errado da conta).
    obra_out = {
        "previsto": grand_previsto, "pago": grand_pago, "pendente": grand_pendente, "futuro": grand_futuro,
        "por_classificacao": class_rollup,
    }

    # ---- Janela de pagamento do mês em foco: quadro separado com o que é esperado
    # sair nesse mês. Cartão vem da classificação por cor (só dá o mês, não o dia).
    # Pix vem da tabela manual "Janela de Pagamentos {Mês}{Ano}" (colunas AI:AK) que o
    # usuário monta com datas reais — mais precisa; cai de volta pra classificação por
    # cor se essa tabela não existir ainda pro mês em foco.
    mes_abrev = months[dash_ref].split("./")[0].strip().lower()
    mes_nome = _MES_ABREV_PARA_NOME.get(mes_abrev, "").capitalize()
    month_window = load_month_window(sh, sheets_api, obra_ws, mes_nome)
    cartao_itens = [
        {"item": it["item"], "classificacao": it["classificacao"], "modalidade": it["modalidade"],
         "valor": it["valor"], "status": it["status"], "data": ""}
        for it in month_window if it["modalidade"].strip().lower() == "cartão"
    ]
    janela_pix_manual = load_janela_pix_manual(obra_ws)
    if janela_pix_manual is not None:
        pix_itens = [
            {"item": it["item"], "classificacao": "", "modalidade": "Pix", "valor": it["valor"],
             "status": "PENDENTE", "data": it["data"]}
            for it in janela_pix_manual["itens"]
        ]
        pix_fonte = "manual"
    else:
        pix_itens = [
            {"item": it["item"], "classificacao": it["classificacao"], "modalidade": it["modalidade"],
             "valor": it["valor"], "status": it["status"], "data": ""}
            for it in month_window if it["modalidade"].strip().lower() == "pix"
        ]
        pix_fonte = "cor"

    # "Pix pendente a realizar" (tile + tabela por classificação da Obra) soma pendente
    # (rosa) e futuro (azul) — Pix não tem um "futuro com data" separado como o Cartão;
    # os dois são "ainda não pago" e batem exatamente com o total da Janela de Pagamento
    # manual (mesmos itens, só que sem quebra por classificação lá).
    pagamentos["pix_pendente_total"] = pagamentos["pix_pendente"] + pagamentos["pix_futuro"]

    janela_pagamento = {
        "mes": months[dash_ref],
        "pix_fonte": pix_fonte,
        "itens": pix_itens + cartao_itens,
    }
    janela_pagamento["total"] = sum(it["valor"] for it in janela_pagamento["itens"])

    jul27_idx = next((i for i, m in enumerate(months) if m.startswith("jul./27")), n - 1)

    alerts = build_alerts(
        months, dash_ref, totals, cartao_obra_mensal, obra_out, by_natureza,
        fin["saldo_investimento"], saldo_acumulado=saldo_acumulado, invest_search_from=ref,
    )

    # ---- Investimentos: highlights de eficiência/concentração/liquidez (dados já
    # carregados no início de main(), inclusive para alimentar o financiamento da obra).
    invest_highlights = compute_highlights(invest_categorias, invest_total, invest_quotes, invest_rent_ativa)
    investimentos_out = {
        "total": invest_total,
        "categorias": invest_categorias,
        "cotacoes": invest_quotes,
        "rent_ativa": invest_rent_ativa,
        "highlights": invest_highlights,
    }

    personal_n = len([it for it in card_items if it["tipo"] != "Obra Apto"])
    obra_card_n = len([it for it in card_items if it["tipo"] == "Obra Apto"])

    out = {
        "months": months,
        "ref_month_index": dash_ref,
        "anchor_month_index": ref,
        "jul27_index": jul27_idx,
        "entradas": totals["entradas"],
        "saidas": totals["saidas"],
        "saldo_liquido": totals["saldo_liquido"],
        "receita_liquida": totals["receita_liquida"],
        "outras_receitas": totals["outras_receitas"],
        "custos_fixos": totals["fixo"],
        "moradia_gabi": totals["moradia_gabi"],
        "custos_variaveis": totals["variavel"],
        "cartao_obra_mensal": cartao_obra_mensal,
        "investimentos_dre": totals["investimentos"],
        "saldo_mes": saldo_mes,
        "saldo_acumulado": saldo_acumulado,
        "dre_resumo": dre_resumo,
        "dre_detalhe": dre_detalhe,
        "gastos_por_natureza": gastos_por_natureza,
        "obra": obra_out,
        "janela_pagamento": janela_pagamento,
        "pagamentos": pagamentos,
        "financiamento_obra": {
            "investimento_bloqueado_total": fin["investimento_bloqueado_total"],
            "saque_mensal": fin["saque_mensal"],
            "saldo_investimento": fin["saldo_investimento"],
            "posicao_inicial": investimento_posicao_inicial,
            "posicao_inicial_mes": months[investimento_mes_inicial_idx],
        },
        "n_itens_cartao_pessoal": personal_n,
        "n_itens_obra_cartao": obra_card_n,
        "alerts": alerts,
        "investimentos": investimentos_out,
    }

    with open(OUT_PATH, "w") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    print(f"{OUT_PATH} escrito.")
    print(f"Mês âncora (saldo real): {months[ref]} | Mês em foco (dashboard): {months[dash_ref]} | Margem Líquida: {dre_resumo['margem_liquida']:.2f}")
    print(f"Entradas: {totals['entradas'][dash_ref]:.2f} | Saídas: {totals['saidas'][dash_ref]:.2f} | Saldo Líquido: {totals['saldo_liquido'][dash_ref]:.2f}")
    print(f"Cartão Obra (mês em foco, via Fluxo_Apto_Realizado linha 55): {cartao_obra_mensal[dash_ref]:.2f}")
    print(f"Moradia paga por Gabi (só Saúde, mês em foco): {totals['moradia_gabi'][dash_ref]:.2f}")
    print(f"Saldo Acumulado projetado ({months[dash_ref]}): {saldo_acumulado[dash_ref]:.2f}")
    print(f"Janela de pagamento {janela_pagamento['mes']}: {len(janela_pagamento['itens'])} itens, total {janela_pagamento['total']:.2f}")
    for g in gastos_por_natureza:
        print(f"  Gastos {g['natureza']}: {g['total']:.2f} ({g['pct']:.1f}%)")
    print(f"Pagamentos -> Pago total: {pagamentos['pago_total']:.2f} | Pix pendente (total previsto): {pagamentos['pix_pendente_total']:.2f} | Cartão futuro: {pagamentos['cartao_futuro']:.2f}")
    print(f"Financiamento obra: saldo em {months[jul27_idx]}: {fin['saldo_investimento'][jul27_idx]:.2f} (partindo de {fin['investimento_bloqueado_total']:.2f}, posição inicial {months[investimento_mes_inicial_idx]}: {investimento_posicao_inicial:.2f})")
    print(f"Saldo Acumulado final ({months[-1]}): {saldo_acumulado[-1]:.2f}")
    print(f"[double-check] Saldo Acumulado + Saldo Investimento (último mês): {(saldo_acumulado[-1] + fin['saldo_investimento'][-1]):.2f}")
    print(f"Alertas gerados: {len(alerts)}")
    print(f"Investimentos: total atual {fmt_brl(invest_total['valor_atual'])} | rentabilidade posições ativas {invest_rent_ativa['rent_pct']} | highlights: {len(invest_highlights)}")


if __name__ == "__main__":
    main()
