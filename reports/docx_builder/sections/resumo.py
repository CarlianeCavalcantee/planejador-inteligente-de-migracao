from ..styles import heading, para, table, PRETO, LARANJA, CINZA, page_break


def build(doc, data, num=1):
    heading(doc, "Resumo Executivo", level=1, numbered=num)

    stats = data.get("estatisticas", {})
    total = stats.get("total_impactos_encontrados", 0)
    repos_imp = stats.get("total_repositorios_com_impacto", 0)
    repos_total = stats.get("total_repositorios_analisados", 0)
    dual = stats.get("requerem_compatibilidade_dual", 0)
    sistema = data.get("sistema_escopo", "BScash")
    limite = data.get("data_limite_migracao", "—")

    para(doc, "Objetivo", bold=True, color=PRETO)
    para(doc,
         f"Adequar todos os ecossistemas e microsserviços do {sistema} para suportar o novo padrão de "
         f"CNPJ Alfanumérico estabelecido pela Receita Federal. O levantamento identificou {total} impactos "
         f"distribuídos em {repos_imp} de {repos_total} repositórios analisados, com prazo limite de migração "
         f"em {limite}.")

    para(doc, "Motivação", bold=True, color=PRETO)
    para(doc,
         "A Receita Federal do Brasil oficializou a transição para o CNPJ Alfanumérico devido à escassez de "
         "combinações estritamente numéricas. Esta mudança afeta toda a cadeia de processamento de dados onde "
         "o CNPJ é utilizado como chave de identificação, busca ou regra de negócio.")

    por_area = stats.get("impactos_por_area", {})
    areas_impactadas = ", ".join(
        f"{a} ({n})" for a, n in sorted(por_area.items(), key=lambda x: -x[1]) if n > 0
    )
    para(doc, f"Camadas impactadas: {areas_impactadas}.",
         italic=True, size=9.5, color=LARANJA)

    doc.add_paragraph()
    para(doc, "Escopo do Projeto", bold=True, color=PRETO)
    table(doc,
        ["INCLUÍDO NO ESCOPO", "FORA DO ESCOPO"],
        [
            ["Adequação de schemas e migrações em Bancos de Dados",
             "Migração retroativa de dados históricos estáticos"],
            ["Refatoração de APIs internas e Gateways",
             "Alterações estruturais nos sistemas de parceiros externos"],
            ["Atualização das aplicações Mobile e Frontend Web",
             "Ajustes em aplicações e serviços previamente descontinuados"],
            [f"Revisão de Schemas de Mensageria e Eventos ({dual} impactos requerem compatibilidade dual)", ""],
            ["Validações de regex e regras de negócio de backend", ""],
        ],
        col_widths=[8.5, 8.5]
    )
    page_break(doc)
