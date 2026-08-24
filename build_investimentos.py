"""Lê a aba Investimentos (posição atual já pré-calculada pela própria planilha nas
colunas J/K/L=Qtd/PM$/R$ atuais, O/P=rentabilidade acumulada R$/%, Q=% participação),
inclusive a seção "Carteira Maria" (mesmo layout de colunas, mais abaixo na aba) e
mantém uma aba auxiliar Investimentos_Cotacoes com fórmulas GOOGLEFINANCE — o
"conector" de cotação em tempo real pedido: a cada abertura/recálculo da planilha (e a
cada rodada do pipeline, 1x/dia às 7h) o Google Sheets busca o preço atual de cada ação
via GOOGLEFINANCE, e este módulo lê o valor já calculado de volta.

Rentabilidade acumulada (colunas O/P) só é comparável quando a linha tinha posição no
início do período E ainda tem posição hoje — uma linha liquidada em 2026 (ex: Renda Fixa,
zerada para financiar o apartamento) mostra "-100%" na planilha, o que parece uma perda,
mas é só o resgate integral, não rentabilidade negativa. O mesmo vale ao contrário para
uma linha que começou em zero (ex: Fundos de Investimento, dinheiro novo) — mostraria um
"+100%" artificial. Por isso o headline de rentabilidade só soma linhas com posição tanto
na base original quanto hoje; as demais aparecem marcadas como liquidadas/novas na tabela,
sem % de rentabilidade. A seção "Carteira Maria" tem esse mesmo problema nas colunas O/P
(fórmula quebrada mostrando -100% mesmo com posição praticamente estável) — por isso a
rentabilidade dela é recalculada direto de valor atual vs. original, não lida do O/P."""
import re

from finlib import get_clients, br_to_float, fmt_brl

SRC_TAB = "Investimentos"
LIVE_TAB = "Investimentos_Cotacoes"

# Estrutura fixa da aba Investimentos: (linha da categoria, linhas dos itens-filho),
# 0-indexado a partir de get_all_values(). Categoria = linha de subtotal (fórmula SUM
# sobre os filhos). Colunas: B=nome(1), F=R$ original/baseline(5), J=Qtd atual(9),
# K=PM$ atual(10), L=R$ atual(11), O=Rent Acum R$(14), P=Rent Acum %(15), Q=% Part(16).
# "Carteira Maria" usa o mesmo layout, só que numa seção própria mais abaixo, com seu
# próprio subtotal (% Part relativo ao total dela, não ao do portfólio principal).
STRUCTURE = [
    ("Renda Fixa", 1, [2, 3, 4]),
    ("Fundos de Investimento", 5, [6]),
    ("Previdência Privada", 7, [8, 9]),
    ("Ações Nacionais", 10, [11, 12, 13, 14, 15, 16]),
    ("Ações Int. + Cryptos", 17, [18]),
    ("Carteira Maria", 24, [25, 26, 27, 28]),
]
TOTAL_ROW = 19

TICKER_RE = re.compile(r"([A-Z]{4}\d{1,2}|CMIG4)F?\b")


def extract_ticker(nome):
    m = TICKER_RE.search(nome)
    return m.group(1) if m else None


def _parse_row(values, row_idx):
    row = values[row_idx] if row_idx < len(values) else []
    def cell(col):
        return row[col] if col < len(row) else ""
    valor_original = br_to_float(cell(5))
    valor_atual = br_to_float(cell(11))
    return {
        "nome": cell(1).strip(),
        "qtd": br_to_float(cell(9)),
        "pm": br_to_float(cell(10)),
        "valor_original": valor_original,
        "valor_atual": valor_atual,
        "rent_acum_rs": br_to_float(cell(14)),
        "rent_acum_pct": br_to_float(cell(15)),
        "pct_part": br_to_float(cell(16)),
        # comparável = tinha posição no início E ainda tem hoje — só nesse caso a
        # rentabilidade acumulada da planilha reflete ganho/perda real, não um
        # resgate integral (liquidado) ou aporte novo (started_zero).
        "liquidado": valor_original > 0 and valor_atual == 0,
        "started_zero": valor_original == 0 and valor_atual > 0,
    }


def _fix_direct_rentabilidade(row):
    """Recalcula rent_acum direto de valor atual vs. original — usado só pra 'Carteira
    Maria', cujas colunas O/P vêm com fórmula quebrada (mostram -100% mesmo com posição
    quase estável)."""
    rent_rs = row["valor_atual"] - row["valor_original"]
    row["rent_acum_rs"] = rent_rs
    row["rent_acum_pct"] = (rent_rs / row["valor_original"] * 100) if row["valor_original"] else 0.0
    row["liquidado"] = row["valor_original"] > 0 and row["valor_atual"] == 0
    row["started_zero"] = row["valor_original"] == 0 and row["valor_atual"] > 0


def load_investimentos(ws):
    values = ws.get_all_values()
    categorias = []
    for nome, cat_row, child_rows in STRUCTURE:
        cat = _parse_row(values, cat_row)
        cat["itens"] = [_parse_row(values, r) for r in child_rows]
        for it in cat["itens"]:
            it["ticker"] = extract_ticker(it["nome"])
            if nome == "Carteira Maria":
                _fix_direct_rentabilidade(it)
        if nome == "Carteira Maria":
            _fix_direct_rentabilidade(cat)
        categorias.append(cat)
    total = _parse_row(values, TOTAL_ROW)
    return categorias, total


def get_fundo_obra_balance(categorias):
    """Saldo atual do 'BB RF Ref DI Plus' (categoria Fundos de Investimento) — o fundo
    dado em garantia do limite do cartão da obra. Era ~R$144k no início (posição
    consumida ao longo de 2026 conforme as parcelas do cartão superam o salário do mês);
    esta função lê o saldo já atualizado direto da aba Investimentos a cada rodada, em
    vez de um valor fixo desatualizado no código."""
    cat = next((c for c in categorias if c["nome"] == "Fundos de Investimento"), None)
    return cat["valor_atual"] if cat else None


def ensure_live_quotes(sh, sheets_api, tickers):
    """Escreve/atualiza a aba Investimentos_Cotacoes com uma linha GOOGLEFINANCE por
    ticker e lê de volta o preço já calculado pelo Sheets. Sempre reescreve (idempotente)
    para acompanhar mudanças na carteira sem deixar tickers órfãos."""
    header = ["Ticker", "Cotação Atual (BRL)", "Atualizado em"]
    rows = [header]
    for t in tickers:
        rows.append([t, f'=GOOGLEFINANCE("BVMF:{t}")', "=NOW()"])

    try:
        ws = sh.worksheet(LIVE_TAB)
        ws.clear()
    except Exception:
        ws = sh.add_worksheet(title=LIVE_TAB, rows=len(rows) + 5, cols=4)

    if len(rows) > 1:
        ws.update(values=rows, range_name="A1", value_input_option="USER_ENTERED")
    else:
        ws.update(values=[header], range_name="A1")

    values = ws.get_all_values()
    quotes = {}
    for row in values[1:]:
        if len(row) < 2 or not row[0].strip():
            continue
        quotes[row[0].strip()] = br_to_float(row[1])
    return quotes


def compute_rentabilidade_ativa(categorias):
    """Rentabilidade acumulada só sobre linhas comparáveis (posição na base original E
    hoje) — evita o -100% artificial de linhas liquidadas e o +100% artificial de linhas
    que começaram em zero (dinheiro novo). Carteira Maria fica de fora — é uma carteira
    à parte, não deveria se misturar no headline da carteira do Luiz."""
    comparaveis = [
        c for c in categorias
        if c["nome"] != "Carteira Maria" and not c["liquidado"] and not c["started_zero"] and c["valor_atual"] > 0
    ]
    rent_rs = sum(c["rent_acum_rs"] for c in comparaveis)
    valor = sum(c["valor_atual"] for c in comparaveis)
    custo = valor - rent_rs
    rent_pct = (rent_rs / custo * 100) if custo else None
    return {"rent_rs": rent_rs, "rent_pct": rent_pct, "valor_base": valor, "n_categorias": len(comparaveis)}


def compute_highlights(categorias, total, quotes, rent_ativa):
    """Alertas/observações curtas sobre a carteira — concentração, liquidez travada,
    exposição zerada a renda variável e comparação preço médio vs cotação ao vivo para
    quem tiver posição aberta hoje."""
    highlights = []

    total_atual = total["valor_atual"] or 1.0
    for cat in categorias:
        if cat["nome"] == "Carteira Maria":
            continue  # % Part dela é relativa à própria carteira, não à do Luiz
        if cat["pct_part"] >= 60:
            highlights.append({
                "icon": "⚠️",
                "text": f"{cat['nome']} concentra {cat['pct_part']:.1f}% da carteira — pouca diversificação entre classes de ativo.",
            })

    liquidadas = [c["nome"] for c in categorias if c["liquidado"] and c["nome"] != "Carteira Maria"]
    if liquidadas:
        highlights.append({
            "icon": "ℹ️",
            "text": f"{', '.join(liquidadas)} {'foi liquidada' if len(liquidadas) == 1 else 'foram liquidadas'} em 2026 (resgate integral, não rentabilidade negativa) — provavelmente para financiar o apartamento/obra.",
        })

    for cat in categorias:
        for it in cat["itens"]:
            if it["ticker"] and it["qtd"] > 0 and it["ticker"] in quotes and quotes[it["ticker"]]:
                cotacao = quotes[it["ticker"]]
                gap_pct = (cotacao / it["pm"] - 1) * 100 if it["pm"] else 0
                if gap_pct <= -10:
                    highlights.append({
                        "icon": "🔻",
                        "text": f"{it['ticker']}: cotação atual R$ {cotacao:.2f} está {abs(gap_pct):.1f}% abaixo do preço médio de compra (R$ {it['pm']:.2f}).",
                    })
                elif gap_pct >= 15:
                    highlights.append({
                        "icon": "🔺",
                        "text": f"{it['ticker']}: cotação atual R$ {cotacao:.2f} está {gap_pct:.1f}% acima do preço médio de compra (R$ {it['pm']:.2f}) — ganho não realizado relevante.",
                    })

    fundos_cat = next((c for c in categorias if c["nome"] == "Fundos de Investimento"), None)
    if fundos_cat and fundos_cat["valor_atual"] / total_atual > 0.5:
        highlights.append({
            "icon": "🔒",
            "text": f"R$ {fmt_brl(fundos_cat['valor_atual'])} em Fundos de Investimento seguem dados em garantia do limite do cartão da obra — liquidez reduzida até a obra terminar.",
        })

    if rent_ativa["rent_pct"] is not None:
        icon = "✅" if rent_ativa["rent_rs"] >= 0 else "⚠️"
        highlights.append({
            "icon": icon,
            "text": f"Rentabilidade das posições ativas (comparáveis com a base original): {rent_ativa['rent_pct']:.1f}% (R$ {fmt_brl(rent_ativa['rent_rs'])}).",
        })

    return highlights[:6]


def main():
    sh, sheets_api = get_clients()
    ws = sh.worksheet(SRC_TAB)
    categorias, total = load_investimentos(ws)

    tickers = sorted({it["ticker"] for cat in categorias for it in cat["itens"] if it["ticker"]})
    quotes = ensure_live_quotes(sh, sheets_api, tickers)
    rent_ativa = compute_rentabilidade_ativa(categorias)
    highlights = compute_highlights(categorias, total, quotes, rent_ativa)

    print(f"Investimentos: total atual {fmt_brl(total['valor_atual'])}")
    for cat in categorias:
        tag = " [LIQUIDADO]" if cat["liquidado"] else (" [NOVO]" if cat["started_zero"] else "")
        print(f"  {cat['nome']}: {fmt_brl(cat['valor_atual'])} ({cat['pct_part']:.1f}%){tag}")
    print(f"Rentabilidade posições ativas (sem Carteira Maria): {rent_ativa}")
    print(f"Cotações ao vivo (GOOGLEFINANCE): {quotes}")
    print(f"Highlights gerados: {len(highlights)}")
    for h in highlights:
        print(f"  {h['icon']} {h['text']}")


if __name__ == "__main__":
    main()
