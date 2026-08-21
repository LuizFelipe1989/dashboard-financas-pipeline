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
FLUXO_APTO_TAB = "Fluxo_Apto_Realizado"

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
    ("(-) MORADIA SAÚDE (PAGO POR GABI — INFORMATIVO, NÃO ENTRA NA MARGEM)", None),
    ("Aluguel Saúde Saúde", "MORADIA_GABI"),
    ("Condominio + Gás + Agua Saúde", "MORADIA_GABI"),
    ("Enel Saúde", "MORADIA_GABI"),
    ("Internet - Saúde", "MORADIA_GABI"),
    ("Cartão Crédito Casa", "MORADIA_GABI"),
    ("(-) CUSTOS FIXOS", None),
    ("Financiamento VM", "FIXO"),
    ("Condominio VM", "FIXO"),
    ("IPTU", "FIXO"),
    ("Energia Eletrica VM", "FIXO"),
    ("ComGás VM", "FIXO"),
    ("Internet VM", "FIXO"),
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
    ("Pix Pagamentos Obra", "VARIAVEL"),  # obra (Pix) é despesa variável, entra no total
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


def load_cartao_obra_mensal(ws, proj_months):
    """Read Fluxo_Apto_Realizado's own 'Cartão' monthly row (linha 55 — realizado +
    parcelas futuras já agendadas do cartão de obra) and align it onto the Projeção
    month axis. Fluxo_Apto_Realizado starts one calendar month earlier than Projeção
    (verified by month-name match), so fluxo_series[i+1] lines up with proj_months[i];
    falls back to a full name-match scan if that offset ever stops holding."""
    values = ws.get_all_values()
    header_idx = None
    for i, row in enumerate(values):
        if i > 50 and len(row) > 9 and row[9].strip() == "Junho":
            header_idx = i
            break
    if header_idx is None:
        return [0.0] * len(proj_months)
    fluxo_months = [c.strip() for c in values[header_idx][9:22] if c.strip()]
    cartao_row = None
    for row in values[header_idx:header_idx + 4]:
        if len(row) > 8 and row[8].strip() == "Cartão":
            cartao_row = [br_to_float(c) for c in row[9:9 + len(fluxo_months)]]
            break
    if cartao_row is None:
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
        aligned.append(cartao_row[src_idx] if 0 <= src_idx < len(cartao_row) else 0.0)
    return aligned


def group_sum(data, group_name, n_months, groups=GROUPS):
    tot = [0.0] * n_months
    for label, group in groups:
        if group == group_name:
            vals = data.get(label, [0.0] * n_months)
            tot = [a + b for a, b in zip(tot, vals)]
    return tot


def compute_totals(months, data, cartao_tipo, cartao_obra_mensal=None):
    """Shared monthly totals used by DRE_Mensal, Fluxo_Caixa and the dashboard JSON.
    cartao_obra_mensal (from Fluxo_Apto_Realizado!linha 55, already aligned to `months`)
    folds into Custos Variáveis alongside the personal cartão-por-tipo breakdown."""
    n = len(months)
    cartao_pessoal_total = [0.0] * n
    for vals in cartao_tipo.values():
        cartao_pessoal_total = [a + b for a, b in zip(cartao_pessoal_total, vals)]
    cartao_obra_mensal = cartao_obra_mensal or [0.0] * n

    receita_bruta = data.get("Salário Bruto", [0.0] * n)
    deducoes = group_sum(data, "DEDUCOES", n)
    receita_liquida = [a + b for a, b in zip(receita_bruta, deducoes)]
    fixo = group_sum(data, "FIXO", n)
    moradia_gabi = group_sum(data, "MORADIA_GABI", n)
    variavel_sem_cartao = group_sum(data, "VARIAVEL", n)
    variavel = [a + b + c for a, b, c in zip(variavel_sem_cartao, cartao_pessoal_total, cartao_obra_mensal)]
    outras_receitas = group_sum(data, "OUTRAS_RECEITAS", n)
    investimentos = group_sum(data, "INVESTIMENTOS", n)

    # moradia_gabi is informational only (paid by Gabi) — excluded from margem_liquida.
    margem_liquida = [
        rl + orc + f + v + inv
        for rl, orc, f, v, inv in zip(receita_liquida, outras_receitas, fixo, variavel, investimentos)
    ]
    entradas = [rl + orc for rl, orc in zip(receita_liquida, outras_receitas)]
    saidas = [f + v for f, v in zip(fixo, variavel)]
    saldo_liquido = [e + s for e, s in zip(entradas, saidas)]
    return {
        "receita_bruta": receita_bruta, "deducoes": deducoes, "receita_liquida": receita_liquida,
        "fixo": fixo, "moradia_gabi": moradia_gabi, "variavel_sem_cartao": variavel_sem_cartao,
        "cartao_pessoal_total": cartao_pessoal_total, "cartao_obra_mensal": cartao_obra_mensal,
        "variavel": variavel, "outras_receitas": outras_receitas,
        "investimentos": investimentos, "margem_liquida": margem_liquida,
        "entradas": entradas, "saidas": saidas, "saldo_liquido": saldo_liquido,
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
