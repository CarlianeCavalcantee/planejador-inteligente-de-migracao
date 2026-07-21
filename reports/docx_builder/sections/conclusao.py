from ..styles import heading, para, table, PRETO, LARANJA, page_break


def build_pendencias(doc, data, num=15):
    heading(doc, "Registro de Pendências", level=1, numbered=num)

    pendencias = data.get("pendencias_identificadas", [])
    if not pendencias:
        para(doc, "Nenhuma pendência registrada.", italic=True)
        page_break(doc)
        return

    rows = [
        [
            p.get("id", "—"),
            p.get("descricao", "—")[:200],
            p.get("responsavel", "—"),
            p.get("prazo_estimado", "—"),
        ]
        for p in pendencias
    ]
    table(doc, ["ID", "DESCRIÇÃO", "RESPONSÁVEL", "PRAZO"],
          rows, col_widths=[1.8, 9.5, 3.5, 2.2])
    page_break(doc)


def build_conclusao(doc, data, num=16):
    heading(doc, "Conclusão", level=1, numbered=num)

    stats = data.get("estatisticas", {})
    total = stats.get("total_impactos_encontrados", 0)
    repos = stats.get("total_repositorios_com_impacto", 0)
    alta  = stats.get("impactos_por_complexidade", {}).get("Alta", 0)
    dual  = stats.get("requerem_compatibilidade_dual", 0)
    sistema = data.get("sistema_escopo", "BScash")
    limite = data.get("data_limite_migracao", "—")

    para(doc,
         f"O levantamento de impacto do {sistema} identificou {total} ocorrências distribuídas em "
         f"{repos} repositórios, sendo {alta} de alta complexidade e {dual} requerendo implementação "
         f"de compatibilidade dual explícita.")

    para(doc,
         f"A estratégia de Compatibilidade Dual com Feature Flag garante migração segura e rollback "
         f"imediato sem indisponibilidade de serviços. O prazo limite para conclusão da migração é "
         f"{limite}.")

    para(doc,
         "A execução bem-sucedida deste plano garantirá que o ecossistema esteja preparado para "
         "receber CNPJs alfanuméricos de forma transparente, mantendo retrocompatibilidade com o "
         "formato numérico durante todo o período de transição do mercado.",
         italic=True, size=9.5, color=LARANJA)
