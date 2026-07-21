from ..styles import heading, para, table, PRETO, LARANJA, page_break


def build(doc, data, num=10):
    heading(doc, "Plano de Rollback Estruturado", level=1, numbered=num)

    checklist = data.get("checklist_rollback", {})

    if isinstance(checklist, dict) and checklist:
        for modulo, itens in checklist.items():
            heading(doc, modulo, level=2)
            if isinstance(itens, list):
                rows = []
                for item in itens:
                    if isinstance(item, dict):
                        rows.append([
                            item.get("acao", item.get("descricao", str(item))),
                            item.get("responsavel", "—"),
                            item.get("prazo", item.get("tempo_estimado", "—")),
                        ])
                    else:
                        rows.append([str(item), "—", "—"])
                if rows:
                    table(doc, ["AÇÃO DE ROLLBACK", "RESPONSÁVEL", "PRAZO"],
                          rows, col_widths=[9, 4, 4])
            elif isinstance(itens, dict):
                rows = [[k, str(v)] for k, v in itens.items()]
                table(doc, ["ITEM", "DETALHE"], rows, col_widths=[6, 11])
    elif isinstance(checklist, list) and checklist:
        rows = []
        for item in checklist:
            if isinstance(item, dict):
                rows.append([
                    item.get("acao", item.get("descricao", str(item))),
                    item.get("responsavel", "—"),
                    item.get("prazo", "—"),
                ])
            else:
                rows.append([str(item), "—", "—"])
        table(doc, ["AÇÃO DE ROLLBACK", "RESPONSÁVEL", "PRAZO"],
              rows, col_widths=[9, 4, 4])
    else:
        para(doc, "• Rollback de Código: Desativação imediata da Feature Flag enableAlphaCNPJ.")
        para(doc, "• Rollback de Banco: Estrutura VARCHAR(20) mantida para evitar perda de dados.")
        para(doc, "• Rollback de Mensageria: Reativação do schema anterior no Schema Registry.")

    page_break(doc)
