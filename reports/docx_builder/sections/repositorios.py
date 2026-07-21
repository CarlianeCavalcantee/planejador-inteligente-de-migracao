from ..styles import heading, para, table, LARANJA, comp_color, COR_ALTA, COR_MEDIA, COR_BAIXA, page_break
from ..helpers import impacts_by_area, group_impacts, top_files


def build(doc, data, num=8):
    heading(doc, "Impacto por Repositório", level=1, numbered=num)

    stats = data.get("estatisticas", {})
    por_repo = stats.get("impactos_por_repositorio", {})
    matriz = data.get("matriz_impacto", [])

    # Tabela resumo de todos os repositórios impactados
    rows = []
    for repo, v in sorted(por_repo.items(), key=lambda x: -x[1].get("total", 0)):
        if v.get("total", 0) == 0:
            continue
        rows.append([
            repo,
            str(v.get("total", 0)),
            (str(v.get("Alta", 0)),  COR_ALTA),
            (str(v.get("Média", 0)), COR_MEDIA),
            (str(v.get("Baixa", 0)), COR_BAIXA),
            ", ".join(v.get("areas", [])),
        ])
    table(doc, ["REPOSITÓRIO", "TOTAL", "ALTA", "MÉDIA", "BAIXA", "ÁREAS IMPACTADAS"],
          rows, col_widths=[4, 1.8, 1.5, 1.5, 1.5, 6.7])

    # Arquivos críticos
    criticos = data.get("arquivos_criticos", [])
    if criticos:
        para(doc, "Arquivos Críticos (maior concentração de impactos)", bold=True)
        top = top_files(matriz, n=20)
        crit_rows = [
            [f["arquivo"].split("/")[-1], f["repo"], str(f["count"]), f["areas"]]
            for f in top
        ]
        table(doc, ["ARQUIVO", "REPOSITÓRIO", "IMPACTOS", "ÁREAS"],
              crit_rows, col_widths=[5.5, 4, 2, 5.5])

    page_break(doc)
