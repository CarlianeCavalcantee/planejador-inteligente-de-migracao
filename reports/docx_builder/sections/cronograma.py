from ..styles import heading, para, table, LARANJA, COR_ALTA, COR_BAIXA, comp_color, page_break


def _build_trilhas_section(doc, data, num):
    trilhas_data = data.get("trilhas")
    if not trilhas_data:
        return

    heading(doc, "Divisão em Trilhas Paralelas", level=1, numbered=num)
    n     = trilhas_data["n_trilhas"]
    delta = trilhas_data["desequilibrio_pct"]
    para(doc,
         f"Repos agrupados por similaridade de áreas e divididos em {n} trilhas com carga equilibrada. "
         f"Desequilíbrio de carga: {delta}%. Configure 'trilhas' no scanner-config.json para alterar.",
         italic=True, size=9.5)

    for t in trilhas_data["trilhas"]:
        heading(doc, f"Trilha {t['trilha']}  —  {t['carga_alta']} impactos difíceis  |  {t['total_impactos']} total", level=2)
        rows = [
            [str(r["passo"]), r["modulo"], str(r["alta"]), str(r["total"]), r["perfil"]]
            for r in t["repositorios"]
        ]
        table(doc, ["Ordem", "Repositório", "Difíceis", "Total", "Áreas"],
              rows, col_widths=[1.2, 4, 1.8, 1.5, 8.5])

    deps = trilhas_data.get("dependencias_cruzadas", [])
    if deps:
        heading(doc, "Coordenar antes do merge", level=2)
        for dep in deps:
            repos_str = ", ".join(dep["repositorios"])
            para(doc, f"⚠ {dep['area']}: {repos_str} — definir quem faz a migration/versão de API primeiro.")

    page_break(doc)


def build(doc, data, num=11):
    heading(doc, "Plano de Migração por Módulo", level=1, numbered=num)
    para(doc,
         "Cada módulo (repositório) é migrado de forma independente. "
         "A sequência interna de áreas segue a ordem de dependência técnica.",
         italic=True, size=9.5)

    ordem = data.get("ordem_migracao", [])
    if not ordem:
        para(doc, "Ordem de migração não disponível no JSON.", italic=True)
        page_break(doc)
        return

    # Tabela resumo de módulos
    rows = []
    for s in ordem:
        alta = s.get("impactos_alta_complexidade", 0)
        rows.append([
            str(s.get("passo", "—")),
            s.get("modulo", "—"),
            str(s.get("total_impactos", 0)),
            (str(alta), COR_ALTA if alta > 0 else COR_BAIXA),
            str(s.get("requerem_compatibilidade_dual", 0)),
            " → ".join(a["area"] for a in s.get("areas", [])),
        ])
    table(doc, ["#", "MÓDULO", "IMPACTOS", "ALTA", "DUAL", "SEQUÊNCIA DE ÁREAS"],
          rows, col_widths=[0.8, 3.5, 2, 1.5, 1.5, 7.7])

    # Detalhe por módulo (top 5 mais críticos)
    top5 = sorted(ordem, key=lambda x: -x.get("impactos_alta_complexidade", 0))[:5]
    if top5:
        para(doc, "Detalhamento dos 5 Módulos Mais Críticos", bold=True)
        for s in top5:
            heading(doc, f"Módulo: {s['modulo']} (Sprint {s['passo']})", level=2)
            areas = s.get("areas", [])
            area_rows = [
                [
                    a.get("area", "—"),
                    str(a.get("total_impactos", 0)),
                    str(a.get("impactos_alta_complexidade", 0)),
                    str(a.get("requerem_compatibilidade_dual", 0)),
                    a.get("rationale", "—"),
                ]
                for a in areas
            ]
            table(doc, ["ÁREA", "IMPACTOS", "ALTA", "DUAL", "RATIONALE"],
                  area_rows, col_widths=[3, 2, 1.5, 1.5, 9])

    page_break(doc)
