import json
from collections import OrderedDict

from finlib import (
    get_clients, PROJ_TAB, CONTAS_TAB, FLUXO_APTO_TAB, DESPESAS_CASA_TAB, REF_MONTH_INDEX,
    load_projecao, load_card_items, cartao_por_tipo, load_cartao_obra_mensal, compute_totals, fmt_brl,
    apply_despesas_casa_handover, compute_financiamento_obra,
)
from build_dre import build_rows
from build_obra import load_items_and_colors, payment_summary, SRC_TAB as OBRA_TAB
from build_gastos_tipo import group_by_natureza, NATUREZA_ORDEM

OUT_PATH = "dashboard_data.json"


def dre_detalhe_full(months, data, ctipo, cartao_obra_mensal, totals):
    """Sectioned line-item list (kind HEADER/LINE/SUBTOTAL) across ALL months, reusing
    build_dre.build_rows() so the dashboard's DRE detail table is exactly the DRE_Mensal
    sheet's own structure. `grupo` (raw group key) is kept for internal filtering (e.g.
    Composição das Despesas) but is not meant to be rendered as its own column."""
    rows = build_rows(months, data, ctipo, cartao_obra_mensal, totals)
    return [{"kind": kind, "label": label, "grupo": grp, "vals": list(vals) if vals is not None else None}
            for kind, label, vals, _classif, grp in rows]


def build_alerts(months, ref, totals, cartao_obra_mensal, obra, gastos_natureza, saldo_investimento_series):
    """Regras de bom senso sobre os dados frescos — mesma lógica que o agente da
    routine diária aplicaria; roda aqui também para manter o dashboard com alertas
    sempre que os scripts locais forem executados, não só na rotina de nuvem."""
    alerts = []

    margem = totals["margem_liquida"][ref]
    if margem < 0:
        alerts.append({"icon": "⚠️", "text": f"Margem líquida negativa em {months[ref]}: R$ {fmt_brl(margem)} — as saídas do mês superam as entradas."})

    cartao_obra_ref = abs(cartao_obra_mensal[ref])
    receita_ref = totals["receita_liquida"][ref]
    if receita_ref and cartao_obra_ref >= receita_ref * 0.6:
        pct = cartao_obra_ref / receita_ref * 100
        alerts.append({"icon": "💳", "text": f"Parcela do cartão da obra em {months[ref]} consome {pct:.0f}% do salário líquido do mês."})

    for c in obra["por_classificacao"]:
        if c["previsto"] and c["pago"] / c["previsto"] > 1.0:
            pct = c["pago"] / c["previsto"] * 100
            alerts.append({"icon": "🏗️", "text": f"Obra \"{c['classificacao']}\" já pagou {pct:.0f}% do previsto (estourou o orçamento)."})

    disc_total = sum(acc["total"] for acc in gastos_natureza.get("Discricionário", {}).values())
    var_total = abs(totals["variavel"][ref]) or 1.0
    if disc_total / var_total > 0.15:
        alerts.append({"icon": "🔀", "text": f"Gastos discricionários (não recorrentes) somam R$ {fmt_brl(disc_total)} este mês — vale revisar."})

    if saldo_investimento_series and min(saldo_investimento_series) <= 0:
        idx0 = next((i for i, v in enumerate(saldo_investimento_series) if v <= 0), None)
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
    n = len(months)
    ref = REF_MONTH_INDEX

    card_items = load_card_items(contas_ws)
    ctipo = cartao_por_tipo(card_items, n)
    cartao_obra_mensal = load_cartao_obra_mensal(apto_ws, months)
    totals = compute_totals(months, proj_data, ctipo, cartao_obra_mensal)

    # Financiamento da obra e Fluxo de Caixa compartilham a mesma lógica de saque —
    # é o que faz o saldo final de um bater com o do outro (double-check pedido).
    fin = compute_financiamento_obra(months, cartao_obra_mensal, totals["receita_liquida"])
    saldo_mes = [sl + inv + sq for sl, inv, sq in zip(totals["saldo_liquido"], totals["investimentos"], fin["saque_mensal"])]
    raw_cum = []
    running = 0.0
    for v in saldo_mes:
        running += v
        raw_cum.append(running)
    anchor = raw_cum[ref] - fin["saldo_disponivel_imediato"]
    saldo_acumulado = [v - anchor for v in raw_cum]

    # ---- DRE resumo (mês de referência) — Custo Obra separado da Margem Líquida,
    # já que a obra tem prazo pra terminar e não deveria diluir a margem recorrente.
    receita_liquida_ref = totals["receita_liquida"][ref]
    custos_fixos_ref = totals["fixo"][ref]
    custos_variaveis_ref = totals["variavel"][ref]
    custo_obra_ref = totals["variavel_obra"][ref]
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
        acc = by_class.setdefault(c, {"previsto": 0.0, "pago": 0.0, "pendente": 0.0, "futuro": 0.0})
        acc["previsto"] += it["previsto"]
        acc["pago"] += it["pago"]
        acc["pendente"] += it["pendente"]
        acc["futuro"] += it["futuro"]
    class_rollup = [{"classificacao": c, **acc} for c, acc in sorted(by_class.items(), key=lambda kv: -kv[1]["previsto"])]

    pagamentos = payment_summary(items)
    # "Cartão a vencer" reconciliado com o mesmo dado mensal do gráfico Cartão Obra —
    # soma de Fluxo_Apto_Realizado!linha 55 a partir do mês de referência, não a
    # classificação por cor das células do item table (que só reflete parcelas já
    # lançadas linha a linha e diverge do agendamento consolidado da linha 55).
    pagamentos["cartao_futuro"] = sum(abs(v) for v in cartao_obra_mensal[ref:])
    obra_out = {
        "previsto": grand_previsto, "pago": grand_pago, "pendente": grand_pendente, "futuro": grand_futuro,
        "por_classificacao": class_rollup,
    }

    jul27_idx = next((i for i, m in enumerate(months) if m.startswith("jul./27")), n - 1)

    alerts = build_alerts(months, ref, totals, cartao_obra_mensal, obra_out, by_natureza, fin["saldo_investimento"][ref:])

    personal_n = len([it for it in card_items if it["tipo"] != "Obra Apto"])
    obra_card_n = len([it for it in card_items if it["tipo"] == "Obra Apto"])

    out = {
        "months": months,
        "ref_month_index": ref,
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
        "investimentos": totals["investimentos"],
        "saldo_mes": saldo_mes,
        "saldo_acumulado": saldo_acumulado,
        "dre_resumo": dre_resumo,
        "dre_detalhe": dre_detalhe,
        "gastos_por_natureza": gastos_por_natureza,
        "obra": obra_out,
        "pagamentos": pagamentos,
        "financiamento_obra": {
            "investimento_bloqueado_total": fin["investimento_bloqueado_total"],
            "saque_mensal": fin["saque_mensal"],
            "saldo_investimento": fin["saldo_investimento"],
        },
        "n_itens_cartao_pessoal": personal_n,
        "n_itens_obra_cartao": obra_card_n,
        "alerts": alerts,
    }

    with open(OUT_PATH, "w") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    print(f"{OUT_PATH} escrito.")
    print(f"Mês referência: {months[ref]} | Margem Líquida: {dre_resumo['margem_liquida']:.2f}")
    print(f"Entradas: {totals['entradas'][ref]:.2f} | Saídas: {totals['saidas'][ref]:.2f} | Saldo Líquido: {totals['saldo_liquido'][ref]:.2f}")
    print(f"Cartão Obra (mês ref, via Fluxo_Apto_Realizado linha 55): {cartao_obra_mensal[ref]:.2f}")
    print(f"Moradia paga por Gabi (só Saúde, mês ref): {totals['moradia_gabi'][ref]:.2f}")
    for g in gastos_por_natureza:
        print(f"  Gastos {g['natureza']}: {g['total']:.2f} ({g['pct']:.1f}%)")
    print(f"Pagamentos -> Pago total: {pagamentos['pago_total']:.2f} | Pix pendente: {pagamentos['pix_pendente']:.2f} | Cartão futuro: {pagamentos['cartao_futuro']:.2f}")
    print(f"Financiamento obra: saldo em {months[jul27_idx]}: {fin['saldo_investimento'][jul27_idx]:.2f} (partindo de {fin['investimento_bloqueado_total']:.2f})")
    print(f"Saldo Acumulado final ({months[-1]}): {saldo_acumulado[-1]:.2f}")
    print(f"[double-check] Saldo Acumulado + Saldo Investimento (último mês): {(saldo_acumulado[-1] + fin['saldo_investimento'][-1]):.2f}")
    print(f"Alertas gerados: {len(alerts)}")


if __name__ == "__main__":
    main()
