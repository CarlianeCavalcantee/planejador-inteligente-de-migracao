from ..styles import heading, para, table, PRETO, LARANJA, page_break


def build_testes(doc, data, num=13):
    heading(doc, "Plano de Testes Integrados", level=1, numbered=num)

    telas = data.get("telas_qa", [])
    if telas:
        para(doc, f"Telas/Fluxos identificados para QA: {len(telas)}", italic=True, size=9.5, color=LARANJA)
        rows = []
        for t in sorted(telas, key=lambda x: x.get("prioridade", "P9")):
            rows.append([
                t.get("tela", "—"),
                t.get("prioridade", "—"),
                str(t.get("total_impactos", 0)),
                "Sim" if t.get("requer_compatibilidade_dual") else "Não",
                ", ".join(t.get("areas_impactadas", [])),
                ", ".join(t.get("repositorios", [])[:3]) + ("…" if len(t.get("repositorios", [])) > 3 else ""),
            ])
        table(doc, ["TELA / FLUXO", "PRIO", "IMPACTOS", "DUAL", "ÁREAS", "REPOSITÓRIOS"],
              rows, col_widths=[4.5, 1.2, 1.8, 1.2, 3.5, 4.8])

    para(doc, "Tipos de Teste Necessários", bold=True, color=PRETO)
    table(doc,
        ["TIPO", "DESCRIÇÃO", "COBERTURA MÍNIMA"],
        [
            ["Unitário",
             "Cenários de regex com CNPJs fictícios alfanuméricos e numéricos.",
             "100% dos validadores refatorados"],
            ["Contrato (CDC)",
             "Validação estrutural de payloads de API contra o Gateway.",
             "Todos os endpoints com campo CNPJ"],
            ["Integração",
             "Fluxo completo com CNPJ alfanumérico de ponta a ponta.",
             "Fluxos P1 e P2 das telas QA"],
            ["Regressão",
             "CNPJ numérico antigo continua funcionando após migração.",
             "100% dos fluxos existentes"],
            ["Carga / Estresse",
             "Processamento batch volumoso com chaves alfanuméricas.",
             "Índices e queries críticas"],
            ["UI",
             "Campo CNPJ aceita alfanumérico e exibe máscara correta.",
             "Todos os formulários com campo CNPJ"],
        ],
        col_widths=[3, 8, 6]
    )
    page_break(doc)


def build_criterios(doc, data, num=14):
    heading(doc, "Critérios de Aceite para Go-Live", level=1, numbered=num)
    para(doc,
         "Todos os itens abaixo devem ser formalmente validados antes da entrada em produção:",
         size=10)

    criterios = data.get("criterios_aceite", [
        "Todos os pontos de processamento de CNPJ identificados e mapeados.",
        "Atualização de todas as tabelas e schemas relacionais efetuada.",
        "Testes de estresse e performance de buscas e índices aprovados.",
        "Homologação formal realizada com todos os parceiros críticos.",
        "Feature Flag enableAlphaCNPJ testada em HML por no mínimo 5 dias úteis.",
        "Plano de rollback documentado e validado pelo time de operações.",
        "Monitoramento e alertas configurados para métricas de CNPJ alfanumérico.",
    ])

    rows = [[f"☐  {c}"] for c in criterios]
    table(doc, ["CRITÉRIO DE ACEITE"], rows, col_widths=[17])
    page_break(doc)
