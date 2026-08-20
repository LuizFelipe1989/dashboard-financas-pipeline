"""Orchestrates the daily refresh: rebuilds every derived sheet tab, extracts
the dashboard JSON, and assembles the final dashboard.html. Run this, then
(separately) let the alert agent inspect dashboard_data.json, write alerts
into it, call write_cell_notes.py for the flagged cells, and re-run just
build_dashboard_html.py to bake the alerts into the page before publishing.
"""
import time


def step(name, fn):
    print(f"\n=== {name} ===")
    t0 = time.time()
    fn()
    print(f"({name} done in {time.time() - t0:.1f}s)")


def main():
    import build_dre
    import build_obra
    import build_fluxo_caixa
    import build_gastos_tipo
    import extract_dashboard_data
    import build_dashboard_html

    step("DRE_Mensal", build_dre.main)
    step("Obra_Consolidado", build_obra.main)
    step("Fluxo_Caixa", build_fluxo_caixa.main)
    step("Gastos_Por_Tipo", build_gastos_tipo.main)
    step("extract_dashboard_data", extract_dashboard_data.main)
    step("build_dashboard_html", build_dashboard_html.main)

    print("\nPipeline completo. dashboard_data.json e dashboard.html atualizados.")
    print("Próximo passo (fora deste script): analisar dashboard_data.json em busca de")
    print("gastos excessivos/ineficiências, gravar o campo 'alerts', escrever as notas de")
    print("célula correspondentes com write_cell_notes.py, rodar build_dashboard_html.py de")
    print("novo, e publicar/atualizar o Artifact do dashboard.")


if __name__ == "__main__":
    main()
