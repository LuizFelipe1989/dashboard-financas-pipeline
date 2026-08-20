import re
from collections import OrderedDict

import gspread
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

SPREADSHEET_ID = "1GtYvjDoTNBq7nBxlB21wWs6hfL1Xc80kIZb1uAR_x4w"
KEY_FILE = "swift-shore-505201-b3-e6c16d2ee287.json"
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

PROJ_TAB = "Projeção Gastos_Atualizados"
CONTAS_TAB = "Contas"

CARD_TABLE_COL_DESC = 9   # 0-indexed: col J
CARD_TABLE_COL_VALOR = 10
CARD_TABLE_COL_TIPO = 11
CARD_TABLE_COL_BANCO = 12
CARD_TABLE_FIRST_ROW = 3  # 1-indexed sheet row

REF_MONTH_INDEX = 1  # 'ago./26' — mês de referência para contar parcelas restantes; ajuste aqui se necessário
PARCELA_RE = re.compile(r"[Pp]arcela\s+(\d+)\s*/\s*(\d+)")

# Canonical row taxonomy for Projeção Gastos_Atualizados -> DRE groups.
# (row label in source, DRE group). Shared by build_dre.py, build_fluxo_caixa.py,
# extract_dashboard_data.py so all 3 views agree on what's Fixo vs Variável.
GROUPS = [
    ("RECEITA BRUTA", None),
    ("Salário Bruto", "RECEITA_BRUTA"),
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
    ("13º Salário", "DEDUCOES"),
    ("(-) CUSTOS FIXOS", None),
    ("Financiamento VM", "FIXO"),
    ("Condominio VM", "FIXO"),
    ("IPTU", "FIXO"),
    ("Energia Eletrica VM", "FIXO"),
    ("ComGás VM", "FIXO"),
    ("Internet VM", "FIXO"),
    ("Aluguel Saúde Saúde", "FIXO"),
    ("Condominio + Gás + Agua Saúde", "FIXO"),
    ("Enel Saúde", "FIXO"),
    ("Internet - Saúde", "FIXO"),
    ("Cartão Crédito Casa", "FIXO"),
    ("Seguro Carro Taos", "FIXO"),
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
    ("(-) OBRA (REFORMA)", None),
    # "Parcelas Cartão Crédito - Obra" (estimativa antiga da Projeção) é deliberadamente
    # omitida: os itens de cartão de obra já entram, detalhados, via Contas!Cartão Pessoal
    # (tipo "Obra Apto") e são rastreados em Obra_Consolidado — somar aqui também duplicaria.
    ("Pix Pagamentos Obra", "OBRA"),
    ("(+) OUTRAS RECEITAS / APORTES", None),
    ("Gabriela", "OUTRAS_RECEITAS"),
    ("(-) INVESTIMENTOS", None),
    ("Investimentos", "INVESTIMENTOS"),
]


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
        if not desc or desc.upper().startswith("TOTAL"):
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
        items.append({"desc": desc, "valor_parcela": valor, "tipo": tipo, "banco": banco, "restantes": restantes})
        r += 1
    return items


def distribute(items, n_months, ref_month_index=REF_MONTH_INDEX):
    """Return list of (item, monthly_values[n_months]) — each item's per-installment
    value placed as a negative (expense) in its remaining months from ref_month_index."""
    out = []
    for it in items:
        vals = [0.0] * n_months
        for k in range(it["restantes"]):
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


def group_sum(data, group_name, n_months, groups=GROUPS):
    tot = [0.0] * n_months
    for label, group in groups:
        if group == group_name:
            vals = data.get(label, [0.0] * n_months)
            tot = [a + b for a, b in zip(tot, vals)]
    return tot


def compute_totals(months, data, cartao_tipo):
    """Shared monthly totals used by DRE_Mensal, Fluxo_Caixa and the dashboard JSON."""
    n = len(months)
    cartao_total = [0.0] * n
    for vals in cartao_tipo.values():
        cartao_total = [a + b for a, b in zip(cartao_total, vals)]

    receita_bruta = data.get("Salário Bruto", [0.0] * n)
    deducoes = group_sum(data, "DEDUCOES", n)
    receita_liquida = [a + b for a, b in zip(receita_bruta, deducoes)]
    fixo = group_sum(data, "FIXO", n)
    variavel_sem_cartao = group_sum(data, "VARIAVEL", n)
    variavel = [a + b for a, b in zip(variavel_sem_cartao, cartao_total)]
    obra = group_sum(data, "OBRA", n)
    outras_receitas = group_sum(data, "OUTRAS_RECEITAS", n)
    investimentos = group_sum(data, "INVESTIMENTOS", n)

    margem_liquida = [
        rl + orc + f + v + o + inv
        for rl, orc, f, v, o, inv in zip(receita_liquida, outras_receitas, fixo, variavel, obra, investimentos)
    ]
    return {
        "receita_bruta": receita_bruta, "deducoes": deducoes, "receita_liquida": receita_liquida,
        "fixo": fixo, "variavel_sem_cartao": variavel_sem_cartao, "cartao_total": cartao_total,
        "variavel": variavel, "obra": obra, "outras_receitas": outras_receitas,
        "investimentos": investimentos, "margem_liquida": margem_liquida,
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


def fmt_brl(v):
    """Format a float back into Brazilian style with parentheses for negatives."""
    neg = v < 0
    v = abs(v)
    s = f"{v:,.2f}"
    s = s.replace(",", "X").replace(".", ",").replace("X", ".")
    return f"({s})" if neg else s
