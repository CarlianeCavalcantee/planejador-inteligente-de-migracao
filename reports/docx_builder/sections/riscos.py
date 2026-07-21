from ..styles import heading, para, table, PRETO, LARANJA, COR_ALTA, COR_MEDIA, page_break


def build(doc, data, num=9):
    heading(doc, "Análise de Riscos", level=1, numbered=num)

    riscos = data.get("riscos_mapeados", [])
    if not riscos:
        para(doc, "Nenhum risco mapeado no JSON.", italic=True)
        page_break(doc)
        return

    rows = []
    for r in riscos:
        risco = r.get("risco", "—")
        impacto = r.get("impacto", "—")
        mitigacao = r.get("mitigacao", "—")
        # Colorir por severidade implícita
        cor = COR_ALTA if any(w in risco.upper() for w in ["LGPD", "CRÍTICO", "CRITICO", "REAL", "HARDCODED"]) else COR_MEDIA
        rows.append([
            (risco, cor),
            impacto,
            mitigacao,
        ])

    table(doc, ["RISCO IDENTIFICADO", "IMPACTO", "MITIGAÇÃO PROPOSTA"],
          rows, col_widths=[5.5, 5.5, 6])
    page_break(doc)
