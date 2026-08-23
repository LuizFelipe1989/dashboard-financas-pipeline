"""Lê a aba Investimentos (posição atual já pré-calculada pela própria planilha nas
colunas J/K/L=Qtd/PM$/R$ atuais, O/P=rentabilidade acumulada R$/%, Q=% participação) e
mantém uma aba auxiliar Investimentos_Cotacoes com fórmulas GOOGLEFINANCE — o "conector"
de cotação em tempo real pedido: a cada abertura/recálculo da planilha (e a cada rodada
do pipeline, 1x/dia às 7h) o Google Sheets busca o preço atual de cada ação via
GOOGLEFINANCE, e este módulo lê o valor já calculado de volta."""
import re

from finlib import get_clients, br_to_float, fmt_brl

SRC_TAB = "Investimentos"
LIVE_TAB = "Investimentos_Cotacoes"

# Estrutura fixa da aba Investimentos: (linha da categoria, linhas dos itens-filho),
# 0-indexado a partir de get_all_values(). Categoria = linha de subtotal (fórmula SUM
# sobre os filhos); colunas: B=nome(1), J=Qtd atual(9), K=PM$ atual(10), L=R$ atual(11),
# O=Rent Acum R$(14), P=Rent Acum %(15), Q=% Part(16).
STRUCTURE = [
    (1, [2, 3, 4]),      # Renda Fixa: BB LCAs, BB Tes. Direto, BB LCIs
    (5, [6]),            # Fundos de Investimento: BB RF Ref DI Plus
    (7, [8, 9]),          # Previdência Privada: Brasil Prev., Boticario Prev.
    (10, [11, 12, 13, 14, 15, 16]),  # Ações Nacionais: 6 tickers BB
    (17, [18]),           # Ações Int. + Cryptos: Binance
]
TOTAL_ROW = 19

TICKER_RE = re.compile(r"([A-Z]{4}\d{1,2})F?\b")


def extract_ticker(nome):
    m = TICKER_RE.search(nome)
    return m.group(1) if m else None


def _parse_row(values, row_idx):
    row = values[row_idx] if row_idx < len(values) else []
    def cell(col):
        return row[col] if col < len(row) else ""
    return {
        "nome": cell(1).strip(),
        "qtd": br_to_float(cell(9)),
        "pm": br_to_float(cell(10)),
        "valor_atual": br_to_float(cell(11)),
        "rent_acum_rs": br_to_float(cell(14)),
        "rent_acum_pct": br_to_float(cell(15)),
        "pct_part": br_to_float(cell(16)),
    }


def load_investimentos(ws):
    values = ws.get_all_values()
    categorias = []
    for cat_row, child_rows in STRUCTURE:
        cat = _parse_row(values, cat_row)
        cat["itens"] = [_parse_row(values, r) for r in child_rows]
        for it in cat["itens"]:
            it["ticker"] = extract_ticker(it["nome"])
        categorias.append(cat)
    total = _parse_row(values, TOTAL_ROW)
    return categorias, total


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


def compute_highlights(categorias, total, quotes):
    """Alertas/observações curtas sobre a carteira — concentração, liquidez travada,
    exposição zerada a renda variável e comparação preço médio vs cotação ao vivo para
    quem tiver posição aberta hoje."""
    highlights = []

    total_atual = total["valor_atual"] or 1.0
    for cat in categorias:
        if cat["pct_part"] >= 60:
            highlights.append({
                "icon": "⚠️",
                "text": f"{cat['nome']} concentra {cat['pct_part']:.1f}% da carteira — pouca diversificação entre classes de ativo.",
            })

    acoes_cat = next((c for c in categorias if c["nome"] == "Ações Nacionais"), None)
    if acoes_cat and acoes_cat["valor_atual"] == 0:
        highlights.append({
            "icon": "📉",
            "text": "Carteira sem exposição a ações no momento — posições liquidadas em 2026; considere reavaliar exposição a renda variável para diversificar o retorno.",
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
            "text": f"{fmt_brl(fundos_cat['valor_atual'])} em Fundos de Investimento seguem dados em garantia do limite do cartão da obra — liquidez reduzida até a obra terminar.",
        })

    if total["rent_acum_pct"]:
        icon = "✅" if total["rent_acum_pct"] >= 0 else "⚠️"
        highlights.append({
            "icon": icon,
            "text": f"Rentabilidade acumulada da carteira: {total['rent_acum_pct']:.1f}% ({fmt_brl(total['rent_acum_rs'])}).",
        })

    return highlights[:6]


def main():
    sh, sheets_api = get_clients()
    ws = sh.worksheet(SRC_TAB)
    categorias, total = load_investimentos(ws)

    tickers = sorted({it["ticker"] for cat in categorias for it in cat["itens"] if it["ticker"]})
    quotes = ensure_live_quotes(sh, sheets_api, tickers)
    highlights = compute_highlights(categorias, total, quotes)

    print(f"Investimentos: total atual {fmt_brl(total['valor_atual'])} | rentabilidade acumulada {total['rent_acum_pct']:.1f}%")
    for cat in categorias:
        print(f"  {cat['nome']}: {fmt_brl(cat['valor_atual'])} ({cat['pct_part']:.1f}%)")
    print(f"Cotações ao vivo (GOOGLEFINANCE): {quotes}")
    print(f"Highlights gerados: {len(highlights)}")
    for h in highlights:
        print(f"  {h['icon']} {h['text']}")


if __name__ == "__main__":
    main()
