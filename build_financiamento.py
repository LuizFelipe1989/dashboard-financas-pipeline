"""Controle do financiamento do apartamento (Caixa) — aba 'Financiamento_Imovel'.

A aba é de ENTRADA manual (o usuário cola os dados do app da Caixa): este módulo só a
cria, com os valores iniciais, se ela ainda não existir — nunca sobrescreve edições.
Layout (três blocos lado a lado, cada lista cresce pra baixo):
  A:B  Parâmetros do contrato
  D:H  Histórico de posição (data, saldo devedor, meses restantes, prestação, vencimento)
  J:L  Amortizações extraordinárias (data, valor, tipo)
"""
from datetime import date

from finlib import get_clients, br_to_float

TAB = "Financiamento_Imovel"

PARAMS = [
    ("Credor", "Caixa Econômica Federal"),
    ("Data de assinatura", "27/04/2026"),
    ("Valor financiado (R$)", 365000.00),
    ("Prazo contratado (meses)", 300),
    ("Juros nominais (% a.a.)", 10.654),
    ("Juros com relacionamento (% a.a.)", 10.65),
    ("Valor de avaliação do imóvel (R$)", 872559.45),
    ("FGTS utilizado (R$)", 123500.00),
    ("Débito automático", "Sim"),
]
HISTORICO_HEADER = ["Data", "Saldo devedor (R$)", "Meses restantes", "Prestação em aberto (R$)", "Vencimento"]
HISTORICO_SEED = [["13/10/2026", 366544.59, 294, 3657.45, "25/10/2026"]]
AMORT_HEADER = ["Data", "Valor (R$)", "Tipo"]
AMORT_SEED = [["01/10/2026", 259.54, "Amortização — redução do prazo"]]
FIRST_ROW = 4  # primeira linha de dados dos três blocos


def ensure_tab(sh):
    try:
        return sh.worksheet(TAB), False
    except Exception:
        pass
    ws = sh.add_worksheet(TAB, rows=60, cols=12)
    ws.update(range_name="A1", values=[["Financiamento do Apartamento — controle (preencher a partir do app da Caixa)"]])
    ws.update(range_name="A3:B3", values=[["Parâmetros do contrato", ""]])
    ws.update(range_name=f"A{FIRST_ROW}", values=[[k, v] for k, v in PARAMS], value_input_option="USER_ENTERED")
    ws.update(range_name="D2", values=[["Histórico de posição (1 linha por consulta ao app)"]])
    ws.update(range_name="D3:H3", values=[HISTORICO_HEADER])
    ws.update(range_name=f"D{FIRST_ROW}", values=HISTORICO_SEED, value_input_option="USER_ENTERED")
    ws.update(range_name="J2", values=[["Amortizações extraordinárias"]])
    ws.update(range_name="J3:L3", values=[AMORT_HEADER])
    ws.update(range_name=f"J{FIRST_ROW}", values=AMORT_SEED, value_input_option="USER_ENTERED")
    ws.format("A1", {"textFormat": {"bold": True, "fontSize": 12}})
    for rng in ("A3:B3", "D3:H3", "J3:L3"):
        ws.format(rng, {"textFormat": {"bold": True}, "backgroundColor": {"red": 0.91, "green": 0.94, "blue": 0.98}})
    ws.format("D2", {"textFormat": {"bold": True}}); ws.format("J2", {"textFormat": {"bold": True}})
    ws.columns_auto_resize(0, 12)
    return ws, True


def _parse_date(s):
    s = str(s).strip()
    try:
        d, m, y = s.split("/")
        return date(int(y), int(m), int(d))
    except Exception:
        return None


def _add_months(d, k):
    idx = d.year * 12 + (d.month - 1) + k
    y, m = divmod(idx, 12)
    day = min(d.day, 28)
    return date(y, m + 1, day)


def load_financiamento_imovel(sh, plano_meses=None):
    """Lê a aba e devolve o dict que o dashboard consome. plano_meses: lista de
    {'mes','valor'} (saída planejada no fluxo — prestação + amortização extra), opcional."""
    ws, _ = ensure_tab(sh)
    v = ws.get_all_values()

    def cell(r, c):
        return v[r][c].strip() if r < len(v) and c < len(v[r]) else ""

    params = {}
    for r in range(FIRST_ROW - 1, len(v)):
        k = cell(r, 0)
        if not k:
            break
        params[k] = cell(r, 1)

    def pnum(key, default=0.0):
        return br_to_float(params.get(key, "")) if params.get(key, "") != "" else default

    financiado = pnum("Valor financiado (R$)")
    prazo = int(pnum("Prazo contratado (meses)"))
    avaliacao = pnum("Valor de avaliação do imóvel (R$)")

    historico = []
    r = FIRST_ROW - 1
    while cell(r, 3):
        historico.append({
            "data": cell(r, 3),
            "saldo_devedor": br_to_float(cell(r, 4)),
            "meses_restantes": int(br_to_float(cell(r, 5))),
            "prestacao": br_to_float(cell(r, 6)),
            "vencimento": cell(r, 7),
        })
        r += 1
    historico.sort(key=lambda h: _parse_date(h["data"]) or date.min)

    amort = []
    r = FIRST_ROW - 1
    while cell(r, 9):
        amort.append({"data": cell(r, 9), "valor": br_to_float(cell(r, 10)), "tipo": cell(r, 11)})
        r += 1

    if not historico:
        return None
    atual = historico[-1]
    venc = _parse_date(atual["vencimento"])
    quitacao = _add_months(venc, max(atual["meses_restantes"] - 1, 0)) if venc else None
    meses_pagos = max(prazo - atual["meses_restantes"], 0)
    primeiro = historico[0]
    return {
        "credor": params.get("Credor", ""),
        "assinatura": params.get("Data de assinatura", ""),
        "valor_financiado": financiado,
        "prazo_meses": prazo,
        "juros_nominais": pnum("Juros nominais (% a.a.)"),
        "juros_relacionamento": pnum("Juros com relacionamento (% a.a.)"),
        "valor_avaliacao": avaliacao,
        "fgts_utilizado": pnum("FGTS utilizado (R$)"),
        "debito_automatico": params.get("Débito automático", ""),
        "saldo_devedor": atual["saldo_devedor"],
        "data_posicao": atual["data"],
        "meses_restantes": atual["meses_restantes"],
        "meses_pagos": meses_pagos,
        "pct_prazo": (meses_pagos / prazo * 100) if prazo else 0.0,
        "prestacao": atual["prestacao"],
        "vencimento": atual["vencimento"],
        "saldo_vs_financiado": atual["saldo_devedor"] - financiado,
        "variacao_desde_primeira": atual["saldo_devedor"] - primeiro["saldo_devedor"],
        "primeira_posicao": primeiro["data"],
        "ltv_pct": (atual["saldo_devedor"] / avaliacao * 100) if avaliacao else 0.0,
        "amortizacao_extra_total": sum(a["valor"] for a in amort),
        "quitacao_prevista": quitacao.strftime("%m/%Y") if quitacao else "",
        "historico": historico,
        "amortizacoes": amort,
        "plano_caixa": plano_meses or [],
    }


def main():
    sh, _ = get_clients()
    ws, created = ensure_tab(sh)
    print(f"Aba {TAB}: {'criada com valores iniciais' if created else 'já existe (mantida)'}")


if __name__ == "__main__":
    main()
