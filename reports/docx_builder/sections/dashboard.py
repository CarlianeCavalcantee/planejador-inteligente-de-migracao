from ..styles import heading, para, table, CINZA, comp_color, COR_ALTA, COR_MEDIA, COR_BAIXA, page_break


def build(doc, data, num=2):
    heading(doc, "Dashboard Executivo de Impacto", level=1, numbered=num)
    para(doc, "Métricas consolidadas do levantamento de impacto nos repositórios ativos:", italic=True, size=9.5)

    stats = data.get("estatisticas", {})
    por_repo = stats.get("impactos_por_repositorio", {})
    por_area = stats.get("impactos_por_area", {})
    por_comp = stats.get("impactos_por_complexidade", {})
    total = stats.get("total_impactos_encontrados", 0)

    alta  = por_comp.get("Alta", 0)
    media = por_comp.get("Média", 0)
    baixa = por_comp.get("Baixa", 0)

    pct = lambda n: f"{n/total*100:.1f}%" if total else "0%"

    table(doc,
        ["MÉTRICA", "VALOR", "OBSERVAÇÃO"],
        [
            ["Repositórios analisados",  str(stats.get("total_repositorios_analisados", "—")), ""],
            ["Repositórios impactados",  str(stats.get("total_repositorios_com_impacto", "—")),
             f"{stats.get('total_repositorios_sem_impacto',0)} sem impacto"],
            ["Total de impactos",        str(total), ""],
            [("Impactos ALTA complexidade",  COR_ALTA),  (str(alta),  COR_ALTA),  (pct(alta),  COR_ALTA)],
            [("Impactos MÉDIA complexidade", COR_MEDIA), (str(media), COR_MEDIA), (pct(media), COR_MEDIA)],
            [("Impactos BAIXA complexidade", COR_BAIXA), (str(baixa), COR_BAIXA), (pct(baixa), COR_BAIXA)],
            ["Requerem compatibilidade dual", str(stats.get("requerem_compatibilidade_dual", "—")), ""],
            ["Arquivos críticos",        str(stats.get("arquivos_criticos", "—")), ""],
            ["Chamadores críticos estimados", str(stats.get("chamadores_criticos_total", "—")), ""],
        ],
        col_widths=[7, 3, 7]
    )

    para(doc, "Distribuição por Área", bold=True, color=CINZA)
    area_rows = [
        [area, str(qtd), pct(qtd)]
        for area, qtd in sorted(por_area.items(), key=lambda x: -x[1]) if qtd > 0
    ]
    table(doc, ["ÁREA", "IMPACTOS", "% DO TOTAL"], area_rows, col_widths=[9, 3, 5])

    para(doc, "Top 10 Repositórios por Volume de Impacto", bold=True, color=CINZA)
    top10 = sorted(por_repo.items(), key=lambda x: -x[1].get("total", 0))[:10]
    repo_rows = [
        [
            repo,
            str(v.get("total", 0)),
            (str(v.get("Alta", 0)),  COR_ALTA),
            str(v.get("Média", 0)),
            str(v.get("Baixa", 0)),
            ", ".join(v.get("areas", [])),
        ]
        for repo, v in top10
    ]
    table(doc, ["REPOSITÓRIO", "TOTAL", "ALTA", "MÉDIA", "BAIXA", "ÁREAS"],
          repo_rows, col_widths=[4, 1.8, 1.5, 1.5, 1.5, 6.7])
    page_break(doc)
