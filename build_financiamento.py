"""Controle do financiamento do apartamento (Caixa) — aba 'Financiamento_Imovel'.

A aba é de ENTRADA manual (o usuário cola os dados do app da Caixa): este módulo só a
cria, com os valores iniciais, se ela ainda não existir — nunca sobrescreve edições.
Layout (três blocos lado a lado, cada lista cresce pra baixo):
  A:B  Parâmetros do contrato
  D:H  Histórico de posição (data, saldo devedor, meses restantes, prestação, vencimento)
  J:L  Amortizações extraordinárias já realizadas (data, valor, tipo)
  N:O  Antecipações avulsas PLANEJADAS (mês mm/aaaa, valor) — entram nas projeções
Premissas das projeções (antecipação mensal, FGTS bianual) ficam no bloco de parâmetros.
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
    ("Antecipação mensal atual (R$)", 259.54),
    ("FGTS a cada 2 anos (R$)", 38000.00),
    ("Primeiro uso do FGTS (mm/aaaa)", "05/2028"),
]
AVULSAS_HEADER = ["Mês (mm/aaaa)", "Valor (R$)"]
HISTORICO_HEADER = ["Data", "Saldo devedor (R$)", "Meses restantes", "Prestação em aberto (R$)", "Vencimento"]
HISTORICO_SEED = [["13/10/2026", 366544.59, 294, 3657.45, "25/10/2026"]]
AMORT_HEADER = ["Data", "Valor (R$)", "Tipo"]
AMORT_SEED = [["01/10/2026", 259.54, "Amortização — redução do prazo"]]
FIRST_ROW = 4  # primeira linha de dados dos três blocos


def _migrate(ws):
    """Tab criada numa versão anterior: acrescenta parâmetros/blocos novos sem tocar no que existe."""
    col = ws.col_values(1)
    existing = {c.strip() for c in col[FIRST_ROW - 1:]}
    row = FIRST_ROW + len([c for c in col[FIRST_ROW - 1:] if c.strip()])
    for k, v in PARAMS:
        if k not in existing:
            ws.update(range_name=f"A{row}", values=[[k, v]], value_input_option="USER_ENTERED")
            row += 1
    if not ws.acell("N3").value:
        ws.update(range_name="N2", values=[["Antecipações avulsas planejadas"]])
        ws.update(range_name="N3:O3", values=[AVULSAS_HEADER])
        ws.format("N2", {"textFormat": {"bold": True}})
        ws.format("N3:O3", {"textFormat": {"bold": True}, "backgroundColor": {"red": 0.91, "green": 0.94, "blue": 0.98}})


def ensure_tab(sh):
    try:
        ws = sh.worksheet(TAB)
    except Exception:
        ws = None
    if ws is not None:
        _migrate(ws)
        return ws, False
    ws = sh.add_worksheet(TAB, rows=60, cols=16)
    ws.update(range_name="A1", values=[["Financiamento do Apartamento — controle (preencher a partir do app da Caixa)"]])
    ws.update(range_name="A3:B3", values=[["Parâmetros do contrato", ""]])
    ws.update(range_name=f"A{FIRST_ROW}", values=[[k, v] for k, v in PARAMS], value_input_option="USER_ENTERED")
    ws.update(range_name="D2", values=[["Histórico de posição (1 linha por consulta ao app)"]])
    ws.update(range_name="D3:H3", values=[HISTORICO_HEADER])
    ws.update(range_name=f"D{FIRST_ROW}", values=HISTORICO_SEED, value_input_option="USER_ENTERED")
    ws.update(range_name="J2", values=[["Amortizações extraordinárias"]])
    ws.update(range_name="J3:L3", values=[AMORT_HEADER])
    ws.update(range_name=f"J{FIRST_ROW}", values=AMORT_SEED, value_input_option="USER_ENTERED")
    ws.update(range_name="N2", values=[["Antecipações avulsas planejadas"]])
    ws.update(range_name="N3:O3", values=[AVULSAS_HEADER])
    ws.format("N2", {"textFormat": {"bold": True}})
    ws.format("A1", {"textFormat": {"bold": True, "fontSize": 12}})
    for rng in ("A3:B3", "D3:H3", "J3:L3", "N3:O3"):
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


def _month_diff(a, b):
    """Meses de a até b (ambos date), por mês-calendário."""
    return (b.year - a.year) * 12 + (b.month - a.month)


def _parse_mm_aaaa(s):
    try:
        m, y = str(s).strip().split("/")
        return date(int(y), int(m), 1)
    except Exception:
        return None


def simulate(saldo0, i, pmt, extra, fgts_valor, fgts_k0, avulsas, max_k=400):
    """Tabela Price: a prestação (pmt, sem encargos) é fixa; juros = saldo*i; o resto amortiza.
    k=0 é a prestação em aberto. Antecipações (extra mensal, FGTS a cada 24 meses a partir de
    fgts_k0, avulsas {k: valor}) abatem saldo logo após a prestação do mês.
    Retorna (série de saldo por mês incluindo o ponto 0, meses até quitar, juros totais, fgts usado)."""
    s = saldo0
    serie = [saldo0]
    juros = 0.0
    fgts_usado = 0.0
    for k in range(max_k):
        jr = s * i
        juros += jr
        s -= min(max(pmt - jr, 0.0), s)
        if s > 0.005:
            ext = extra + avulsas.get(k, 0.0)
            if fgts_valor and fgts_k0 is not None and k >= fgts_k0 and (k - fgts_k0) % 24 == 0:
                ext += fgts_valor
                fgts_usado += min(fgts_valor, max(s, 0.0))
            s -= min(ext, s)
        serie.append(max(s, 0.0))
        if s <= 0.005:
            return serie, k + 1, juros, fgts_usado
    return serie, max_k, juros, fgts_usado


def _extra_necessario(alvo_meses, saldo0, i, pmt, fgts_valor, fgts_k0, avulsas):
    lo, hi = 0.0, saldo0
    if simulate(saldo0, i, pmt, 0.0, fgts_valor, fgts_k0, avulsas)[1] <= alvo_meses:
        return 0.0
    for _ in range(60):
        mid = (lo + hi) / 2
        if simulate(saldo0, i, pmt, mid, fgts_valor, fgts_k0, avulsas)[1] <= alvo_meses:
            hi = mid
        else:
            lo = mid
    return hi


def projetar_quitacao(fin, avulsas, extra_atual, fgts_valor, fgts_primeiro, horizonte=84):
    """Cenários de quitação (3 e 5 anos) e simulador de antecipação mensal. `fin` é o dict
    já carregado (saldo, meses restantes, prestação, vencimento, juros)."""
    venc = _parse_date(fin["vencimento"])
    if not venc:
        return None
    i = fin["juros_nominais"] / 100.0 / 12.0
    n = fin["meses_restantes"]
    saldo0 = fin["saldo_devedor"]
    pmt = saldo0 * i / (1 - (1 + i) ** (-n)) if i > 0 else saldo0 / n
    encargos = max(fin["prestacao"] - pmt, 0.0)
    primeiro = _parse_mm_aaaa(fgts_primeiro)
    fgts_k0 = _month_diff(venc.replace(day=1), primeiro) if primeiro else None
    if fgts_k0 is not None and fgts_k0 < 0:
        fgts_k0 = 0
    av = {}
    for a in avulsas:
        d = _parse_mm_aaaa(a["mes"])
        if d:
            k = _month_diff(venc.replace(day=1), d)
            if k >= 0:
                av[k] = av.get(k, 0.0) + a["valor"]

    base_juros = simulate(saldo0, i, pmt, 0.0, 0.0, None, {})[2]

    def fim(meses):
        d = _add_months(venc.replace(day=1), meses - 1)
        return d.strftime("%m/%Y")

    def cenario(cid, nome, extra, usa_fgts, usa_avulsas=True, meta=None):
        serie, meses, juros, fg = simulate(saldo0, i, pmt, extra, fgts_valor if usa_fgts else 0.0,
                                           fgts_k0, av if usa_avulsas else {})
        return {
            "id": cid, "nome": nome, "meta_meses": meta,
            "extra_mensal": extra, "usa_fgts": usa_fgts, "fgts_usado": fg,
            "meses": meses, "quitacao": fim(meses),
            "juros_total": juros, "economia_juros": base_juros - juros,
            "desembolso_mensal": fin["prestacao"] + extra,
            "serie": [round(x, 2) for x in serie[:horizonte + 1]],
        }

    cenarios = [
        cenario("base", "Sem antecipação (contrato)", 0.0, False, usa_avulsas=False),
        cenario("atual", "Ritmo atual", extra_atual, False),
        cenario("atual_fgts", "Ritmo atual + FGTS", extra_atual, True),
    ]
    for anos in (5, 3):
        alvo = anos * 12
        ex = _extra_necessario(alvo, saldo0, i, pmt, fgts_valor, fgts_k0, av)
        ex_sem = _extra_necessario(alvo, saldo0, i, pmt, 0.0, None, av)
        c = cenario(f"meta{anos}", f"Meta {anos} anos (com FGTS)", ex, True, meta=alvo)
        c["extra_sem_fgts"] = ex_sem
        cenarios.append(c)

    simulador = []
    for extra in (extra_atual, 500.0, 1000.0, 1500.0, 2000.0, 3000.0, 5000.0):
        a = simulate(saldo0, i, pmt, extra, 0.0, None, av)
        b = simulate(saldo0, i, pmt, extra, fgts_valor, fgts_k0, av)
        simulador.append({
            "extra": extra,
            "meses_sem_fgts": a[1], "quitacao_sem_fgts": fim(a[1]), "economia_sem_fgts": base_juros - a[2],
            "meses_com_fgts": b[1], "quitacao_com_fgts": fim(b[1]), "economia_com_fgts": base_juros - b[2],
        })
    return {
        "premissas": {
            "taxa_mensal_pct": i * 100, "prestacao_sem_encargos": pmt, "encargos": encargos,
            "extra_atual": extra_atual, "fgts_valor": fgts_valor, "fgts_primeiro": fgts_primeiro,
            "avulsas": [{"mes": a["mes"], "valor": a["valor"]} for a in avulsas],
            "inicio": venc.strftime("%m/%Y"), "juros_total_base": base_juros,
        },
        "cenarios": cenarios,
        "simulador": simulador,
    }


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

    avulsas = []
    r = FIRST_ROW - 1
    while cell(r, 13):
        avulsas.append({"mes": cell(r, 13), "valor": br_to_float(cell(r, 14))})
        r += 1

    if not historico:
        return None
    atual = historico[-1]
    venc = _parse_date(atual["vencimento"])
    quitacao = _add_months(venc, max(atual["meses_restantes"] - 1, 0)) if venc else None
    meses_pagos = max(prazo - atual["meses_restantes"], 0)
    primeiro = historico[0]
    out = {
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
    out["projecao"] = projetar_quitacao(
        out, avulsas, pnum("Antecipação mensal atual (R$)"),
        pnum("FGTS a cada 2 anos (R$)"), params.get("Primeiro uso do FGTS (mm/aaaa)", ""))
    return out


def main():
    sh, _ = get_clients()
    ws, created = ensure_tab(sh)
    print(f"Aba {TAB}: {'criada com valores iniciais' if created else 'já existe (mantida)'}")


if __name__ == "__main__":
    main()
