from ..styles import heading, para, table, page_break


def build(doc, data, num=12):
    heading(doc, "Mapeamento de Integrações com Parceiros", level=1, numbered=num)

    parceiros = data.get("parceiros_externos", [])
    if not parceiros:
        para(doc, "Nenhum parceiro externo mapeado no JSON.", italic=True)
        page_break(doc)
        return

    rows = [
        [
            p.get("parceiro", "—"),
            ", ".join(p.get("repositorios", [])) or "—",
            p.get("descricao", "—"),
            p.get("status_alinhamento", "—"),
        ]
        for p in parceiros
    ]
    table(doc, ["PARCEIRO", "REPOSITÓRIOS", "DESCRIÇÃO", "STATUS ALINHAMENTO"],
          rows, col_widths=[3, 4, 7.5, 2.5])
    page_break(doc)
