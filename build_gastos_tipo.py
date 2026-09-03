from collections import OrderedDict

from finlib import (
    get_clients, fmt_brl, CONTAS_TAB, PROJ_TAB, REF_MONTH_INDEX,
    load_card_items, load_projecao, distribute, red_negative_rule,
)

OUT_TAB = "Gastos_Por_Tipo"
NATUREZA_ORDEM = ["Fixo Mensal", "Parcelado", "Discricionário"]


def group_by_tipo(items):
    """Backwards-compatible flat grouping by Tipo only (used by the dashboard's
    'fatura atual' snapshot)."""
    by_tipo = OrderedDict()
    for it in items:
        acc = by_tipo.setdefault(it["tipo"] or "(sem tipo)", {"total": 0.0, "itens": []})
        acc["total"] += it["valor_parcela"]
        acc["itens"].append(it["desc"])
    return by_tipo


def group_by_natureza(items):
    """Tipo grouped within each Natureza (Fixo Mensal / Parcelado / Discricionário),
    each carrying its own subtotal — a snapshot direto do valor_parcela de cada item,
    sem olhar pra mês (equivale a "fatura mais recente lançada")."""
    out = OrderedDict((nat, OrderedDict()) for nat in NATUREZA_ORDEM)
    for it in items:
        bucket = out[it["natureza"]]
        acc = bucket.setdefault(it["tipo"] or "(sem tipo)", {"total": 0.0, "itens": []})
        acc["total"] += it["valor_parcela"]
        acc["itens"].append(it["desc"])
    return out


def group_by_natureza_for_month(items, month_idx, n_months, ref_month_index):
    """Mesma quebra Natureza → Tipo, mas usando o valor que cada item realmente lança
    naquele mês específico (via distribute(), a mesma lógica de recorrência usada em
    cartao_por_tipo) em vez do valor_parcela bruto. Usado quando a fatura de referência
    já foi paga e o "próximo" mês em foco muda (ex.: setembro quitado, olhar outubro) —
    Discricionário naturalmente aparece zerado em meses futuros, já que por natureza não
    recorre (só a fatura em que realmente foi lançado tem esses itens)."""
    dist = distribute(items, n_months, ref_month_index)
    out = OrderedDict((nat, OrderedDict()) for nat in NATUREZA_ORDEM)
    for it, vals in dist:
        val = abs(vals[month_idx]) if month_idx < len(vals) else 0.0
        if val == 0.0:
            continue
        bucket = out[it["natureza"]]
        acc = bucket.setdefault(it["tipo"] or "(sem tipo)", {"total": 0.0, "itens": []})
        acc["total"] += val
        acc["itens"].append(it["desc"])
    return out


def main():
    sh, sheets_api = get_clients()
    contas_ws = sh.worksheet(CONTAS_TAB)
    proj_ws = sh.worksheet(PROJ_TAB)
    months, _ = load_projecao(proj_ws)
    n = len(months)
    items = load_card_items(contas_ws)

    # A fatura do mês de referência (REF_MONTH_INDEX) já foi paga antecipada — a próxima
    # fatura em aberto é a do mês seguinte, então a "fatura atual" passa a mostrar essa
    # composição em vez do snapshot bruto. Discricionário fica zerado ali por natureza
    # (não recorre), o que é esperado — só aparece no mês em que foi realmente lançado.
    fatura_month_idx = REF_MONTH_INDEX + 1
    by_natureza = group_by_natureza_for_month(items, fatura_month_idx, n, REF_MONTH_INDEX)
    grand_total = sum(acc["total"] for tipos in by_natureza.values() for acc in tipos.values()) or 1.0

    header = ["Natureza / Tipo", "Total", "% do Total", "Itens"]
    out_values = [header]
    row_kinds = ["HEADER"]

    for nat in NATUREZA_ORDEM:
        tipos = by_natureza[nat]
        nat_total = sum(acc["total"] for acc in tipos.values())
        out_values.append([nat.upper(), fmt_brl(nat_total), f"{nat_total/grand_total*100:.1f}%", f"{sum(len(a['itens']) for a in tipos.values())} itens"])
        row_kinds.append("NATUREZA")
        for tipo, acc in sorted(tipos.items(), key=lambda kv: -kv[1]["total"]):
            pct = acc["total"] / grand_total * 100
            out_values.append([f"  {tipo}", fmt_brl(acc["total"]), f"{pct:.1f}%", "; ".join(acc["itens"])])
            row_kinds.append("ITEM")

    total_itens = sum(len(acc["itens"]) for tipos in by_natureza.values() for acc in tipos.values())
    out_values.append(["TOTAL GERAL", fmt_brl(grand_total), "100.0%", f"{total_itens} itens"])
    row_kinds.append("TOTAL")

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
    ]
    for r_idx, kind in enumerate(row_kinds):
        if kind in ("NATUREZA", "TOTAL"):
            requests.append({
                "repeatCell": {
                    "range": {"sheetId": sheet_id, "startRowIndex": r_idx, "endRowIndex": r_idx + 1},
                    "cell": {"userEnteredFormat": {"textFormat": {"bold": True}, "backgroundColor": {"red": 0.95, "green": 0.95, "blue": 0.97}}},
                    "fields": "userEnteredFormat(textFormat,backgroundColor)",
                }
            })
    requests.append(red_negative_rule(sheet_id, len(out_values), len(header)))
    sheets_api.spreadsheets().batchUpdate(spreadsheetId=sh.id, body={"requests": requests}).execute()

    print(f"Gastos_Por_Tipo escrito: {len(out_values)} linhas")
    for nat in NATUREZA_ORDEM:
        tipos = by_natureza[nat]
        nat_total = sum(acc["total"] for acc in tipos.values())
        print(f"  {nat}: {fmt_brl(nat_total)} ({nat_total/grand_total*100:.1f}%)")


if __name__ == "__main__":
    main()
