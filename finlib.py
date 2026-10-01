import re
from collections import OrderedDict

import gspread
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

SPREADSHEET_ID = "12iiz1dmbwgAluTtNXnGy2FHQ0sWemDKL4Sc_5OeXS8A"
KEY_FILE = "swift-shore-505201-b3-e6c16d2ee287.json"
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

PROJ_TAB = "Projeção Gastos_Atualizados"
CONTAS_TAB = "Contas"
FLUXO_APTO_TAB = "Fluxo_Apto_Realizado"

CARD_TABLE_COL_DESC = 9   # 0-indexed: col J
CARD_TABLE_COL_VALOR = 10
CARD_TABLE_COL_TIPO = 11
CARD_TABLE_COL_BANCO = 12
CARD_TABLE_FIRST_ROW = 3  # 1-indexed sheet row

REF_MONTH_INDEX = 2  # 'set./26' — mês já realizado/corrente (saldo do fundo lido "hoje"
# reflete até aqui); ajuste aqui conforme o tempo passa, junto com o saldo do fundo
# (get_fundo_obra_balance) e o saldo da conta corrente (SALDO_DISPONIVEL_IMEDIATO).
# Contas!Cartão Pessoal é reescrita a cada rodada pra refletir a fatura em ABERTO atual
# (a que vence dia 10 do mês seguinte) — um fato diferente e independente de
# REF_MONTH_INDEX (o ciclo do cartão fecha dia 10, não no fim do mês civil), por isso é
# uma constante própria, não derivada: mudar REF_MONTH_INDEX não deve mudar qual fatura
# do cartão está aberta. cartao_por_tipo() precisa desse anchor (não o REF_MONTH_INDEX)
# pra bater com o snapshot de Gastos por Tipo/gráfico por cartão.
CARD_REF_MONTH_INDEX = 3  # 'out./26' — mês da fatura aberta refletida em Contas (vence 10/10)
PARCELA_RE = re.compile(r"[Pp]arcela\s+(\d+)\s*/\s*(\d+)")

# Assinaturas (natureza "Fixo Mensal") que NÃO devem recorrer nos meses seguintes:
ASSINATURAS_CANCELADAS = [
    "Apple Bill - Chatgpt",  # já cancelada, não repete
    "Hotmart Marcos Maia",  # compra avulsa (curso), não assinatura recorrente — tipo Assinaturas só pra categorização
]
# GymPass virou Total Pass (R$89,90/mês) — confirmado pelo usuário que recorre normalmente
# nos meses seguintes junto com o cartão, então não entra mais nessa lista de exclusão.
ASSINATURAS_JA_EM_OUTRO_GRUPO = []

# Canonical row taxonomy for Projeção Gastos_Atualizados -> DRE groups.
# (row label in source, DRE group). Shared by build_dre.py, build_fluxo_caixa.py,
# extract_dashboard_data.py so all 3 views agree on what's Fixo vs Variável.
GROUPS = [
    ("RECEITA BRUTA", None),
    ("Salário Bruto", "RECEITA_BRUTA"),
    ("(+) OUTRAS RECEITAS", None),
    # Reembolsos da Gabriela pelas contas da casa que o Luiz antecipa (ela paga as
    # contas dele, ele paga as da casa, ela recompõe depois no 5º dia útil do mês
    # seguinte) — lançado quando o Pix realmente chega, não uma média mensal.
    ("Reembolso Gabriela", "OUTRAS_RECEITAS"),
    ("(-) DEDUÇÕES SOBRE SALÁRIO", None),
    # "Deduções Salário" is the source sheet's own subtotal of the lines below —
    # excluded here to avoid double-counting; the computed Subtotal reproduces it.
    ("IRRF", "DEDUCOES"),
    ("INSS", "DEDUCOES"),
    ("Previdencia Priv Boti", "DEDUCOES"),
    ("Associação GB", "DEDUCOES"),
    ("Vale Refeição", "DEDUCOES"),
    ("Combustível", "DEDUCOES"),  # salary-linked deduction (first occurrence)
    ("Vale Alimentação", "DEDUCOES"),
    ("Desc. Plano Saúde + Dental", "DEDUCOES"),
    ("Desc. Farmácia", "DEDUCOES"),
    ("13º Salário", "DEDUCOES"),  # único valor real: R$4.521,93 em dez./26 (13º de verdade, confirmado pelo usuário)
    ("(-) MORADIA SAÚDE (PAGO POR GABI — INFORMATIVO, NÃO ENTRA NA MARGEM)", None),
    # Apto Saúde devolvido em ago./26 — a partir de set./26 (SET_MONTH_LABEL) estas 4 linhas
    # são zeradas e "Cartão Crédito Casa" passa a refletir só as parcelas pendentes de
    # Despesas_Casa (ver apply_despesas_casa_handover, aplicado logo após load_projecao()).
    ("Aluguel Saúde Saúde", "MORADIA_GABI"),
    ("Condominio + Gás + Agua Saúde", "MORADIA_GABI"),
    ("Enel Saúde", "MORADIA_GABI"),
    ("Internet - Saúde", "MORADIA_GABI"),
    ("Cartão Crédito Casa", "MORADIA_GABI"),
    ("(-) CUSTOS FIXOS DA CASA (PAGO POR GABI — INFORMATIVO, NÃO ENTRA NA MARGEM)", None),
    ("Financiamento VM", "FIXO_GABI"),
    ("Condominio VM", "FIXO_GABI"),
    ("IPTU", "FIXO_GABI"),
    ("Energia Eletrica VM", "FIXO_GABI"),
    ("ComGás VM", "FIXO_GABI"),
    ("Internet VM", "FIXO_GABI"),
    ("Seguro Carro Taos", "FIXO_GABI"),
    ("(-) CUSTOS FIXOS", None),
    ("Previdencia Privada BB", "FIXO"),
    ("Celular", "FIXO"),
    ("Academia", "FIXO"),
    ("(-) CUSTOS VARIÁVEIS", None),
    ("Diarista", "VARIAVEL"),
    ("Combustível#2", "VARIAVEL"),  # second occurrence (personal)
    ("Supermercado", "VARIAVEL"),
    ("Farmácia Maria", "VARIAVEL"),
    ("Pediatra Maria", "VARIAVEL"),
    ("Capitalização Caixa", "VARIAVEL"),
    ("Seguro Residencial  Caixa", "VARIAVEL"),
    ("Terapia", "VARIAVEL"),
    ("Barbearia + Farmácia", "VARIAVEL"),
    ("Doações", "VARIAVEL"),
    ("Vestuário", "VARIAVEL"),
    ("Osteopata Maria", "VARIAVEL"),
    ("(-) CUSTOS VARIÁVEIS — OBRA", None),
    ("Pix Pagamentos Obra", "VARIAVEL_OBRA"),
    ("(-) INVESTIMENTOS", None),
    ("Investimentos", "INVESTIMENTOS"),
]

LABEL_OVERRIDES = {}


def get_clients():
    creds = Credentials.from_service_account_file(KEY_FILE, scopes=SCOPES)
    gc = gspread.authorize(creds)
    sh = gc.open_by_key(SPREADSHEET_ID)
    sheets_api = build("sheets", "v4", credentials=creds)
    return sh, sheets_api


def load_projecao(ws):
    """Read Projeção Gastos_Atualizados into (months, {label: [monthly values]})."""
    values = ws.get_all_values()
    header = values[0]
    months = header[2:-1]  # skip blank col, 'Itens' col, drop trailing TOTAL label
    data = {}
    for row in values[1:]:
        if len(row) < 2 or not row[1].strip():
            continue
        label = row[1].strip()
        nums = [br_to_float(x) for x in row[2:2 + len(months)]]
        key = label
        if label == "Combustível" and key in data:
            key = "Combustível#2"
        data[key] = nums
    return months, data


def load_card_items(ws):
    """Read Contas!Cartão Pessoal: description, per-installment value, Tipo, Banco,
    remaining installments parsed from 'Parcela X/Y' in the description."""
    values = ws.get_all_values()
    items = []
    r = CARD_TABLE_FIRST_ROW
    while r - 1 < len(values):
        row = values[r - 1]
        desc = row[CARD_TABLE_COL_DESC] if len(row) > CARD_TABLE_COL_DESC else ""
        desc = desc.strip()
        if not desc or desc.strip().upper() == "TOTAL":
            break
        valor = br_to_float(row[CARD_TABLE_COL_VALOR]) if len(row) > CARD_TABLE_COL_VALOR else 0.0
        tipo = row[CARD_TABLE_COL_TIPO].strip() if len(row) > CARD_TABLE_COL_TIPO else ""
        banco = row[CARD_TABLE_COL_BANCO].strip() if len(row) > CARD_TABLE_COL_BANCO else ""
        m = PARCELA_RE.search(desc)
        if m:
            atual, total = int(m.group(1)), int(m.group(2))
            restantes = max(total - atual + 1, 1)
        else:
            restantes = 1
        is_mensal = "mensal" in desc.lower() or tipo.strip().lower() == "assinaturas"
        if m:
            natureza = "Parcelado"
        elif is_mensal:
            natureza = "Fixo Mensal"
        else:
            natureza = "Discricionário"
        items.append({
            "desc": desc, "valor_parcela": valor, "tipo": tipo, "banco": banco,
            "restantes": restantes, "parcelado": bool(m), "natureza": natureza,
        })
        r += 1
    return items


def distribute(items, n_months, ref_month_index=REF_MONTH_INDEX):
    """Return list of (item, monthly_values[n_months]) — each item's per-installment
    value placed as a negative (expense) in its remaining months from ref_month_index.
    Assinaturas (natureza 'Fixo Mensal') recorrem até o fim do horizonte, já que são
    recorrentes de verdade — diferente de Discricionário (só o mês da fatura) e Parcelado
    (só as parcelas restantes). Exceções: ASSINATURAS_CANCELADAS (já cancelada, não
    recorre) e ASSINATURAS_JA_EM_OUTRO_GRUPO (já projetada em outra linha, não duplica)."""
    out = []
    for it in items:
        vals = [0.0] * n_months
        restantes = it["restantes"]
        if (it["natureza"] == "Fixo Mensal" and it["desc"] not in ASSINATURAS_CANCELADAS
                and it["desc"] not in ASSINATURAS_JA_EM_OUTRO_GRUPO):
            restantes = max(n_months - ref_month_index, restantes)
        for k in range(restantes):
            idx = ref_month_index + k
            if idx < n_months:
                vals[idx] = -abs(it["valor_parcela"])
        out.append((it, vals))
    return out


def cartao_por_tipo(card_items, n_months, ref_month_index=REF_MONTH_INDEX):
    """Personal (non-Obra Apto) card items, grouped by Tipo, distributed across months."""
    personal = [it for it in card_items if it["tipo"] != "Obra Apto"]
    dist = distribute(personal, n_months, ref_month_index)
    by_tipo = OrderedDict()
    for it, vals in dist:
        key = it["tipo"] or "(sem tipo)"
        acc = by_tipo.setdefault(key, [0.0] * n_months)
        by_tipo[key] = [a + b for a, b in zip(acc, vals)]
    return by_tipo


_MES_ABREV_PARA_NOME = {
    "jan": "janeiro", "fev": "fevereiro", "mar": "marco", "abr": "abril",
    "mai": "maio", "jun": "junho", "jul": "julho", "ago": "agosto",
    "set": "setembro", "out": "outubro", "nov": "novembro", "dez": "dezembro",
}


def _normalize_month(s):
    s = s.strip().lower()
    for a, b in [("á", "a"), ("ã", "a"), ("â", "a"), ("é", "e"), ("ê", "e"),
                 ("í", "i"), ("ó", "o"), ("õ", "o"), ("ô", "o"), ("ú", "u"), ("ç", "c")]:
        s = s.replace(a, b)
    return s


def _load_obra_row_mensal(ws, proj_months, row_label):
    """Read one of Fluxo_Apto_Realizado's own monthly totalizer rows (col H label
    'Cartão' ou 'Pix' — realizado + parcelas/pagamentos futuros já agendados) and align
    it onto the Projeção month axis. Fluxo_Apto_Realizado starts one calendar month
    earlier than Projeção (verified by month-name match), so fluxo_series[i+1] lines up
    with proj_months[i]; falls back to a full name-match scan if that offset ever stops
    holding."""
    values = ws.get_all_values()
    header_idx = None
    for i, row in enumerate(values):
        if i > 50 and len(row) > 9 and row[9].strip() == "Junho":
            header_idx = i
            break
    if header_idx is None:
        return [0.0] * len(proj_months)
    fluxo_months = [c.strip() for c in values[header_idx][9:22] if c.strip()]
    target_row = None
    for row in values[header_idx:header_idx + 4]:
        if len(row) > 8 and row[8].strip() == row_label:
            target_row = [br_to_float(c) for c in row[9:9 + len(fluxo_months)]]
            break
    if target_row is None:
        return [0.0] * len(proj_months)

    offset = 1
    expected = _MES_ABREV_PARA_NOME.get(proj_months[0].split("./")[0].strip().lower(), "")
    if offset >= len(fluxo_months) or _normalize_month(fluxo_months[offset]) != _normalize_month(expected):
        for k, m in enumerate(fluxo_months):
            if _normalize_month(m) == _normalize_month(expected):
                offset = k
                break

    aligned = []
    for i in range(len(proj_months)):
        src_idx = i + offset
        aligned.append(target_row[src_idx] if 0 <= src_idx < len(target_row) else 0.0)
    return aligned


def load_cartao_obra_mensal(ws, proj_months):
    """Linha 'Cartão' (realizado + parcelas futuras já agendadas do cartão de obra)."""
    return _load_obra_row_mensal(ws, proj_months, "Cartão")


def load_pix_obra_mensal(ws, proj_months):
    """Linha 'Pix' (realizado + pagamentos futuros já agendados do Pix da obra) — a
    linha 'Pix Pagamentos Obra' de Projeção Gastos_Atualizados fica sempre zerada (nunca
    mantida pelo usuário), então o Custo Obra/Margem Líquida usava só a parte do cartão
    até esta função existir; agora lê o valor real, mesma fonte usada pelo card_obra."""
    return _load_obra_row_mensal(ws, proj_months, "Pix")


DESPESAS_CASA_TAB = "Despesas_Casa"
SET_MONTH_LABEL = "set./26"
SAUDE_APT_ROWS = ["Aluguel Saúde Saúde", "Condominio + Gás + Agua Saúde", "Enel Saúde", "Internet - Saúde"]


def load_despesas_casa_cartao_mensal(ws, proj_months, from_label=SET_MONTH_LABEL):
    """Read Despesas_Casa's card-item block (Gasto | R$ | Tipo | Banco) and project it
    forward as the new 'Cartão Crédito Casa' monthly value from `from_label` on — o apto
    Saúde foi devolvido em ago./26, então o que resta são só as parcelas já lançadas antes
    da devolução. Itens sem 'Parcela X/Y' são compra avulsa (já cobrada no mês descrito
    pela aba) e não se repetem nos meses seguintes."""
    values = ws.get_all_values()
    header_idx = None
    for i, row in enumerate(values):
        if len(row) > 9 and row[7].strip() == "Gasto" and row[9].strip() == "Tipo":
            header_idx = i
            break
    n = len(proj_months)
    if header_idx is None:
        return [0.0] * n

    items = []
    for row in values[header_idx + 1:]:
        desc = row[7].strip() if len(row) > 7 else ""
        if not desc or desc.strip().upper() == "TOTAL":
            break
        valor = br_to_float(row[8]) if len(row) > 8 else 0.0
        m = PARCELA_RE.search(desc)
        if m:
            atual, total = int(m.group(1)), int(m.group(2))
            restantes = max(total - atual + 1, 1)
        else:
            restantes = 1
        items.append({"valor": valor, "restantes": restantes})

    aligned = [0.0] * n
    if from_label not in proj_months:
        return aligned
    from_idx = proj_months.index(from_label)
    for it in items:
        for k in range(it["restantes"]):
            idx = from_idx + k
            if idx < n:
                aligned[idx] += -abs(it["valor"])
    return aligned


def apply_despesas_casa_handover(months, data, despesas_casa_ws, from_label=SET_MONTH_LABEL):
    """Apto Saúde devolvido em ago./26: zera as 4 linhas de moradia (Aluguel/Condomínio+
    Gás+Água/Enel/Internet Saúde) a partir de `from_label` e troca 'Cartão Crédito Casa'
    pela projeção de parcelas pendentes de Despesas_Casa a partir do mesmo mês — mantém
    os valores históricos (jul./ago.) como já estavam registrados no Projeção. Muda `data`
    in place e também retorna, para uso direto em atribuição."""
    from_idx = months.index(from_label) if from_label in months else len(months)
    for label in SAUDE_APT_ROWS:
        if label in data:
            vals = list(data[label])
            for i in range(from_idx, len(vals)):
                vals[i] = 0.0
            data[label] = vals

    cartao_casa = list(data.get("Cartão Crédito Casa", [0.0] * len(months)))
    projected = load_despesas_casa_cartao_mensal(despesas_casa_ws, months, from_label)
    for i in range(from_idx, len(cartao_casa)):
        cartao_casa[i] = projected[i] if i < len(projected) else 0.0
    data["Cartão Crédito Casa"] = cartao_casa
    return data


def neutralize_investimentos_row(data):
    """A linha 'Investimentos' da Projeção tem um único lançamento (R$144.007,23 em
    jul./26) que era uma estimativa antiga do mesmo fundo hoje rastreado com precisão
    pelo extrato real (R$74.887,76 — ver compute_financiamento_obra). Mantê-la geraria
    um número duplicado/confuso na DRE, então ela é zerada aqui: não entra como saída
    nem como fonte de caixa. Se um aporte recorrente de verdade existir no futuro, essa
    função pode voltar a repassar o valor da planilha em vez de zerar."""
    if "Investimentos" in data:
        data["Investimentos"] = [0.0 for _ in data["Investimentos"]]
    return data


# Extrato BB (conta 3494-0 / 48516-0), posição em 28/09/2026 — não usado no cálculo do
# fundo combinado hoje (o extrato mostra resgate automático zerando a conta corrente
# todo dia, então esse saldo já é 0 na prática), mantido só como registro/fallback.
# Atualize manualmente a cada novo extrato até termos ingestão automática.
SALDO_DISPONIVEL_IMEDIATO = 0.0
# Fallback só usado se a leitura ao vivo da aba Investimentos (build_investimentos.
# get_fundo_obra_balance) falhar — o valor real e atual do RF Ref DI Plus Ágil (fundo
# dado em garantia do limite do cartão da obra) é lido da planilha a cada rodada.
INVESTIMENTO_BLOQUEADO_TOTAL = 74887.76

def compute_financiamento_obra(months, entradas_caixa, saidas_caixa,
                                ref_month_index=REF_MONTH_INDEX,
                                saldo_disponivel=SALDO_DISPONIVEL_IMEDIATO, investimento_total=INVESTIMENTO_BLOQUEADO_TOTAL,
                                historical_start_balance=None, historical_start_index=0):
    """O fundo da obra e a conta corrente são, na prática, a mesma reserva: o extrato
    real mostra resgate automático do fundo cobrindo CADA saída (cartão inteiro, boletos,
    Pix — não só a parte da obra) e a Gabriela recompondo depois via Pix (linha
    'Reembolso Gabriela', dentro de entradas_caixa) quando o salário dela cai — não há
    uma separação real "salário paga isso, fundo paga aquilo". Por isso o saldo do fundo
    é simplesmente entradas_caixa + saidas_caixa acumulados a partir do saldo real
    conhecido em ref_month_index (confirmado com o usuário em 2026-09-28, reconciliando
    contra o extrato bancário item a item).

    historical_start_balance: se informado (ex.: R$144.007,23, a posição bruta do fundo
    em jul./26 antes da obra consumi-lo), reconstrói os meses ANTES de ref_month_index
    com a mesma soma a partir desse saldo inicial — em vez de ficarem "achatados" no
    saldo atual (investimento_total). ref_month_index em diante continua ancorado
    exatamente no saldo real e vivo lido da planilha, sem mudança."""
    n = len(months)
    saldo_mes = [0.0] * n
    saldo_investimento = [investimento_total] * n
    running = investimento_total
    for i in range(n):
        if i > ref_month_index:
            delta = entradas_caixa[i] + saidas_caixa[i]
            running += delta
            saldo_mes[i] = delta
        saldo_investimento[i] = running

    if historical_start_balance is not None:
        hrunning = historical_start_balance
        for i in range(historical_start_index, ref_month_index):
            delta = entradas_caixa[i] + saidas_caixa[i]
            hrunning += delta
            saldo_mes[i] = delta
            saldo_investimento[i] = hrunning

    return {"saldo_mes": saldo_mes, "saldo_investimento": saldo_investimento,
            "saldo_disponivel_imediato": saldo_disponivel, "investimento_bloqueado_total": investimento_total}


def group_sum(data, group_name, n_months, groups=GROUPS):
    tot = [0.0] * n_months
    for label, group in groups:
        if group == group_name:
            vals = data.get(label, [0.0] * n_months)
            tot = [a + b for a, b in zip(tot, vals)]
    return tot


def compute_totals(months, data, cartao_tipo, cartao_obra_mensal=None, obra_pix_mensal=None):
    """Shared monthly totals used by DRE_Mensal, Fluxo_Caixa and the dashboard JSON.
    cartao_obra_mensal (from Fluxo_Apto_Realizado!linha 'Cartão', já alinhada a `months`)
    folds into Custos Variáveis alongside the personal cartão-por-tipo breakdown.
    obra_pix_mensal (linha 'Pix' da mesma aba, via load_pix_obra_mensal) é o valor real
    do Pix da obra — a linha 'Pix Pagamentos Obra' de Projeção Gastos_Atualizados fica
    sempre zerada (nunca mantida pelo usuário), então usa-se essa fonte quando informada;
    cai pro group_sum (zerado) só se nenhuma for passada, por compatibilidade."""
    n = len(months)
    cartao_pessoal_total = [0.0] * n
    for vals in cartao_tipo.values():
        cartao_pessoal_total = [a + b for a, b in zip(cartao_pessoal_total, vals)]
    cartao_obra_mensal = cartao_obra_mensal or [0.0] * n

    receita_bruta = data.get("Salário Bruto", [0.0] * n)
    deducoes = group_sum(data, "DEDUCOES", n)
    receita_liquida = [a + b for a, b in zip(receita_bruta, deducoes)]
    fixo = group_sum(data, "FIXO", n)
    fixo_gabi = group_sum(data, "FIXO_GABI", n)
    moradia_gabi = group_sum(data, "MORADIA_GABI", n)
    variavel_sem_cartao = group_sum(data, "VARIAVEL", n)
    variavel = [a + b for a, b in zip(variavel_sem_cartao, cartao_pessoal_total)]
    obra_pix = obra_pix_mensal if obra_pix_mensal is not None else group_sum(data, "VARIAVEL_OBRA", n)
    variavel_obra = [a + b for a, b in zip(obra_pix, cartao_obra_mensal)]
    outras_receitas = group_sum(data, "OUTRAS_RECEITAS", n)
    investimentos = group_sum(data, "INVESTIMENTOS", n)

    # moradia_gabi e fixo_gabi são informativos só (pagos pela Gabi) — excluídos da
    # margem (visão "quanto sobra se cada um bancasse só o que é seu"). Mas, na prática,
    # o extrato mostra que TUDO sai da mesma reserva (resgate automático cobre cada
    # boleto, inclusive Condomínio/IPTU/Financiamento) e a Gabriela recompõe depois via
    # Pix (linha "Reembolso Gabriela", em Outras Receitas) — por isso saidas_caixa
    # inclui moradia_gabi/fixo_gabi de volta: é o fluxo de caixa real da conta/fundo
    # combinados, usado por compute_financiamento_obra, não a margem informativa do Luiz.
    margem_liquida = [
        rl + orc + f + v + vo + inv
        for rl, orc, f, v, vo, inv in zip(receita_liquida, outras_receitas, fixo, variavel, variavel_obra, investimentos)
    ]
    entradas = [rl + orc for rl, orc in zip(receita_liquida, outras_receitas)]
    saidas = [f + v + vo for f, v, vo in zip(fixo, variavel, variavel_obra)]
    saidas_caixa = [s + fg + mg for s, fg, mg in zip(saidas, fixo_gabi, moradia_gabi)]
    saldo_liquido = [e + s for e, s in zip(entradas, saidas)]
    saldo_liquido_caixa = [e + s for e, s in zip(entradas, saidas_caixa)]
    return {
        "receita_bruta": receita_bruta, "deducoes": deducoes, "receita_liquida": receita_liquida,
        "fixo": fixo, "fixo_gabi": fixo_gabi, "moradia_gabi": moradia_gabi, "variavel_sem_cartao": variavel_sem_cartao,
        "cartao_pessoal_total": cartao_pessoal_total, "cartao_obra_mensal": cartao_obra_mensal,
        "variavel": variavel, "obra_pix": obra_pix, "variavel_obra": variavel_obra,
        "outras_receitas": outras_receitas,
        "investimentos": investimentos, "margem_liquida": margem_liquida,
        "entradas": entradas, "saidas": saidas, "saldo_liquido": saldo_liquido,
        "saidas_caixa": saidas_caixa, "saldo_liquido_caixa": saldo_liquido_caixa,
    }


_NUM_RE = re.compile(r"^\(?-?\s*[\d\.\s]*,?\d*\s*%?\)?$")


def br_to_float(s):
    """Parse a Brazilian-formatted number string (thousands '.', decimal ',',
    negatives in parentheses) into a float. Returns 0.0 for blank/non-numeric."""
    if s is None:
        return 0.0
    s = s.strip()
    if s in ("", "-", "--"):
        return 0.0
    negative = s.startswith("(") and s.endswith(")")
    s = s.strip("()").strip()
    if s.upper().startswith("R$"):
        s = s[2:].strip()
    is_pct = s.endswith("%")
    if is_pct:
        s = s[:-1].strip()
    s = s.replace(".", "").replace(" ", "")
    s = s.replace(",", ".")
    if s.startswith("-"):
        negative = True
        s = s[1:]
    try:
        val = float(s)
    except ValueError:
        return 0.0
    if negative:
        val = -val
    return val


def red_negative_rule(sheet_id, n_rows, n_cols, start_row=0, start_col=0):
    """Conditional format request: any cell whose text starts with '(' (our
    fmt_brl negative convention) renders in red — used across all derived sheets."""
    return {
        "addConditionalFormatRule": {
            "rule": {
                "ranges": [{
                    "sheetId": sheet_id, "startRowIndex": start_row, "endRowIndex": n_rows,
                    "startColumnIndex": start_col, "endColumnIndex": n_cols,
                }],
                "booleanRule": {
                    "condition": {"type": "TEXT_STARTS_WITH", "values": [{"userEnteredValue": "("}]},
                    "format": {"textFormat": {"foregroundColor": {"red": 0.78, "green": 0.14, "blue": 0.11}}},
                },
            },
            "index": 0,
        }
    }


def fmt_brl(v):
    """Format a float back into Brazilian style with parentheses for negatives."""
    neg = v < 0
    v = abs(v)
    s = f"{v:,.2f}"
    s = s.replace(",", "X").replace(".", ",").replace("X", ".")
    return f"({s})" if neg else s
