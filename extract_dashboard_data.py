import json
from collections import OrderedDict

from finlib import (
    get_clients, GROUPS, PROJ_TAB, CONTAS_TAB, REF_MONTH_INDEX,
    load_projecao, load_card_items, distribute, cartao_por_tipo, compute_totals,
)
from build_obra import load_items_and_colors, payment_summary, SRC_TAB as OBRA_TAB
from build_gastos_tipo import group_by_tipo

OUT_PATH = "dashboard_data.json"

# Extrato BB (conta 3494-0 / 48516-0), posição em 20/08/2026 — atualize manualmente
# a cada novo extrato até termos ingestão automática.
SALDO_DISPONIVEL_IMEDIATO = 25371.41
INVESTIMENTO_BLOQUEADO_TOTAL = 74887.76  # RF Ref DI Plus Ágil, dado em garantia do limite do cartão


def dre_detalhe_for_month(data, ctipo, month_idx, base_receita):
    """Flat line-item list (label, grupo, valor, % peso) for one reference month —
    feeds the dashboard's drill-down table."""
    rows = []
    i = 0
    while i < len(GROUPS):
        label, group = GROUPS[i]
        if group is None:
            grp_key = None
            j = i + 1
            while j < len(GROUPS) and GROUPS[j][1] is not None:
                sub_label, sub_group = GROUPS[j]
                grp_key = sub_group
                if sub_label in data:
                    val = data[sub_label][month_idx]
                    rows.append({
                        "label": sub_label.replace("#2", ""), "grupo": grp_key, "valor": val,
                        "pct_peso": abs(val) / base_receita * 100 if base_receita else 0,
                    })
                j += 1
            if grp_key == "VARIAVEL":
                for tipo, vals in sorted(ctipo.items(), key=lambda kv: -sum(kv[1])):
                    val = vals[month_idx]
                    rows.append({
                        "label": f"Cartão Pessoal — {tipo}", "grupo": "VARIAVEL", "valor": val,
                        "pct_peso": abs(val) / base_receita * 100 if base_receita else 0,
                    })
            i = j
        else:
            i += 1
    return rows


def main():
    sh, sheets_api = get_clients()

    # ---- Fluxo de Caixa / DRE base series ----
    proj_ws = sh.worksheet(PROJ_TAB)
    contas_ws = sh.worksheet(CONTAS_TAB)
    months, proj_data = load_projecao(proj_ws)
    n = len(months)

    card_items = load_card_items(contas_ws)
    ctipo = cartao_por_tipo(card_items, n)
    totals = compute_totals(months, proj_data, ctipo)

    obra_card_items = [it for it in card_items if it["tipo"] == "Obra Apto"]
    obra_dist = distribute(obra_card_items, n)
    cartao_obra_mensal = [0.0] * n
    for _, vals in obra_dist:
        cartao_obra_mensal = [a + b for a, b in zip(cartao_obra_mensal, vals)]

    saldo_mes = [
        rl + orc + f + v + o + inv
        for rl, orc, f, v, o, inv in zip(
            totals["receita_liquida"], totals["outras_receitas"], totals["fixo"],
            totals["variavel"], totals["obra"], totals["investimentos"],
        )
    ]
    saldo_acumulado = []
    running = 0.0
    for v in saldo_mes:
        running += v
        saldo_acumulado.append(running)

    # ---- DRE resumo (mês de referência) ----
    ref = REF_MONTH_INDEX
    base_receita = abs(totals["receita_liquida"][ref] + totals["outras_receitas"][ref]) or 1.0
    dre_resumo = {
        "receita_liquida": totals["receita_liquida"][ref] + totals["outras_receitas"][ref],
        "custos_fixos": totals["fixo"][ref],
        "custos_fixos_pct": abs(totals["fixo"][ref]) / base_receita * 100,
        "custos_variaveis": totals["variavel"][ref],
        "custos_variaveis_pct": abs(totals["variavel"][ref]) / base_receita * 100,
        "obra": totals["obra"][ref],
        "obra_pct": abs(totals["obra"][ref]) / base_receita * 100,
        "investimentos": totals["investimentos"][ref],
        "investimentos_pct": abs(totals["investimentos"][ref]) / base_receita * 100,
        "margem_liquida": saldo_mes[ref],
        "margem_liquida_pct": saldo_mes[ref] / base_receita * 100,
    }
    dre_detalhe = sorted(
        dre_detalhe_for_month(proj_data, ctipo, ref, base_receita),
        key=lambda r: -abs(r["valor"]),
    )

    # ---- Gastos por Tipo (snapshot, não distribuído no tempo) ----
    by_tipo = group_by_tipo(card_items)
    grand_total = sum(acc["total"] for acc in by_tipo.values()) or 1.0
    gastos_por_tipo = [
        {"tipo": tipo, "total": acc["total"], "pct": acc["total"] / grand_total * 100, "n_itens": len(acc["itens"])}
        for tipo, acc in sorted(by_tipo.items(), key=lambda kv: -kv[1]["total"])
    ]

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

    # ---- Financiamento da obra: o investimento (RF Ref DI Plus Ágil) fica bloqueado como
    # garantia do limite do cartão e vai sendo liberado conforme as parcelas de obra no
    # cartão são pagas. Saldo real do extrato BB em 20/08/2026 (ver constantes no topo).
    investimento_liberado_acumulado = []
    investimento_ainda_bloqueado = []
    saldo_total_disponivel = []
    liberado_acumulado = 0.0
    for i in range(n):
        if i >= REF_MONTH_INDEX:
            liberado_acumulado = min(INVESTIMENTO_BLOQUEADO_TOTAL, liberado_acumulado + abs(cartao_obra_mensal[i]))
        investimento_liberado_acumulado.append(liberado_acumulado)
        investimento_ainda_bloqueado.append(INVESTIMENTO_BLOQUEADO_TOTAL - liberado_acumulado)
        saldo_total_disponivel.append(SALDO_DISPONIVEL_IMEDIATO + liberado_acumulado)

    personal_n = len([it for it in card_items if it["tipo"] != "Obra Apto"])
    obra_card_n = len([it for it in card_items if it["tipo"] == "Obra Apto"])

    out = {
        "months": months,
        "ref_month_index": REF_MONTH_INDEX,
        "receita_liquida": totals["receita_liquida"],
        "outras_receitas": totals["outras_receitas"],
        "custos_fixos": totals["fixo"],
        "moradia_gabi": totals["moradia_gabi"],
        "custos_variaveis": totals["variavel"],
        "obra_pix": proj_data.get("Pix Pagamentos Obra", [0.0] * n),
        "cartao_obra_mensal": cartao_obra_mensal,
        "investimentos": totals["investimentos"],
        "total_despesas": [f + v + o for f, v, o in zip(totals["fixo"], totals["variavel"], totals["obra"])],
        "saldo_mes": saldo_mes,
        "saldo_acumulado": saldo_acumulado,
        "dre_resumo": dre_resumo,
        "dre_detalhe": dre_detalhe,
        "gastos_por_tipo": gastos_por_tipo,
        "obra": {
            "previsto": grand_previsto, "pago": grand_pago, "pendente": grand_pendente, "futuro": grand_futuro,
            "por_classificacao": class_rollup,
        },
        "pagamentos": pagamentos,
        "financiamento_obra": {
            "saldo_disponivel_imediato": SALDO_DISPONIVEL_IMEDIATO,
            "investimento_bloqueado_total": INVESTIMENTO_BLOQUEADO_TOTAL,
            "investimento_liberado_acumulado": investimento_liberado_acumulado,
            "investimento_ainda_bloqueado": investimento_ainda_bloqueado,
            "saldo_total_disponivel": saldo_total_disponivel,
        },
        "n_itens_cartao_pessoal": personal_n,
        "n_itens_obra_cartao": obra_card_n,
        "alerts": [],
    }

    with open(OUT_PATH, "w") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    print(f"{OUT_PATH} escrito.")
    print(f"Mês referência: {months[REF_MONTH_INDEX]} | Margem Líquida: {dre_resumo['margem_liquida']:.2f}")
    print(f"Gastos por Tipo: {len(gastos_por_tipo)} tipos | Obra: {len(class_rollup)} classificações")
    print(f"Moradia paga por Gabi (mês ref): {totals['moradia_gabi'][ref]:.2f}")
    print(f"Cartão Obra mensal (mês ref): {cartao_obra_mensal[ref]:.2f} | pico: {min(cartao_obra_mensal):.2f}")
    print(f"Pagamentos -> Pago total: {pagamentos['pago_total']:.2f} | Pix pendente: {pagamentos['pix_pendente']:.2f} | Cartão futuro: {pagamentos['cartao_futuro']:.2f}")
    print(f"Financiamento obra: bloqueado {INVESTIMENTO_BLOQUEADO_TOTAL:.2f} -> liberado até {months[-1]}: {investimento_liberado_acumulado[-1]:.2f} | saldo total disponível final: {saldo_total_disponivel[-1]:.2f}")


if __name__ == "__main__":
    main()
