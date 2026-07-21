from ..styles import heading, para, table, PRETO, LARANJA, comp_color, page_break


_CAMADAS_DEFAULT = [
    ("Frontend",      "Alteração de máscaras de input e regex de validação visual.",                                    "Média"),
    ("Mobile",        "Atualização das views de cadastro, regras locais e liberação em stores.",                        "Alta"),
    ("Backend",       "Refatoração de classes utilitárias de validação e lógica de negócios.",                          "Alta"),
    ("Banco de Dados","Alteração de colunas de VARCHAR(14) para VARCHAR(20) em tabelas transacionais e de histórico.",   "Alta"),
    ("APIs",          "Atualização de schemas OpenAPI/Swagger e validações nos controllers dos gateways.",               "Alta"),
    ("Mensageria",    "Validação de payloads de eventos assíncronos para evitar rejeição em tópicos de produção.",       "Média"),
    ("ETL/Batch",     "Revisão de rotinas de reconciliação financeira, CNAB e processamento noturno.",                   "Alta"),
    ("Integrações",   "Alinhamento com parceiros externos, atualização de schemas XSD/WSDL e contratos SOAP/REST.",      "Alta"),
]


def build_camadas(doc, data, num=5):
    heading(doc, "Análise de Impacto por Camada", level=1, numbered=num)

    stats = data.get("estatisticas", {})
    por_area = stats.get("impactos_por_area", {})
    por_comp = stats.get("impactos_por_complexidade", {})

    # Enriquecer camadas com contagem real do JSON
    _area_map = {
        "Frontend": ["Frontend"],
        "Mobile": ["Frontend"],
        "Backend": ["Backend"],
        "Banco de Dados": ["Banco de Dados"],
        "APIs": ["API/Contrato", "Integrações"],
        "Mensageria": ["Integrações"],
        "ETL/Batch": ["Processamento/Batch"],
        "Integrações": ["Integrações"],
    }

    rows = []
    for camada, desc, comp_default in _camadas_default(data):
        areas = _area_map.get(camada, [])
        qtd = sum(por_area.get(a, 0) for a in areas)
        qtd_str = str(qtd) if qtd else "—"
        rows.append([camada, desc, qtd_str, (comp_default, comp_color(comp_default))])

    table(doc, ["CAMADA", "DESCRIÇÃO DO IMPACTO", "IMPACTOS", "COMPLEXIDADE"],
          rows, col_widths=[3, 9.5, 2, 2.5])
    page_break(doc)


def _camadas_default(data):
    """Retorna camadas com complexidade derivada dos dados reais quando possível."""
    stats = data.get("estatisticas", {})
    por_area = stats.get("impactos_por_area", {})

    def comp(areas):
        total = sum(por_area.get(a, 0) for a in areas)
        if total > 200:
            return "Alta"
        if total > 50:
            return "Média"
        return "Baixa"

    return [
        ("Frontend",       "Alteração de máscaras de input e regex de validação visual.",
         comp(["Frontend"])),
        ("Mobile",         "Atualização das views de cadastro, regras locais e liberação em stores.",
         "Alta"),
        ("Backend",        "Refatoração de classes utilitárias de validação e lógica de negócios.",
         comp(["Backend"])),
        ("Banco de Dados", "Alteração de colunas de VARCHAR(14) para VARCHAR(20) em tabelas transacionais e de histórico.",
         comp(["Banco de Dados"])),
        ("APIs",           "Atualização de schemas OpenAPI/Swagger e validações nos controllers dos gateways.",
         comp(["API/Contrato", "Integrações"])),
        ("Mensageria",     "Validação de payloads de eventos assíncronos para evitar rejeição em tópicos de produção.",
         "Média"),
        ("ETL/Batch",      "Revisão de rotinas de reconciliação financeira, CNAB e processamento noturno.",
         comp(["Processamento/Batch"])),
        ("Integrações",    "Alinhamento com parceiros externos, atualização de schemas XSD/WSDL e contratos SOAP/REST.",
         comp(["Integrações"])),
        ("Segurança/LGPD", "Remoção de CNPJs reais hardcoded e auditoria de histórico git.",
         comp(["Segurança/LGPD"])),
    ]


def build_estrategia(doc, data, num=6):
    heading(doc, "Estratégia de Compatibilidade Dual", level=1, numbered=num)

    para(doc, "Tratamento de Entrada", bold=True)
    para(doc,
         "Todas as portas de entrada (APIs públicas/privadas, telas de cadastro) devem aceitar as duas "
         "variações de formato, limpando caracteres especiais antes de trafegar na rede de microsserviços.")

    para(doc, "Modelo de Persistência", bold=True)
    para(doc,
         "Colunas de CNPJ devem ser expandidas para VARCHAR(20) para suportar o formato alfanumérico "
         "com máscara (AB.12C.D34/0001-EF = 18 chars) e futuras variações.")

    para(doc, "Contrato de APIs", bold=True)
    para(doc, 'Payload aceito: { "cnpj": "12345678000195" } ou { "cnpj": "AB12CD340001EF" }',
         italic=True, size=9.5)

    para(doc, "Feature Flag", bold=True)
    para(doc,
         "A ativação do processamento alfanumérico é governada pela flag enableAlphaCNPJ de forma "
         "granular por ambiente: DEV → QA → HML → PROD.")

    stats = data.get("estatisticas", {})
    dual = stats.get("requerem_compatibilidade_dual", 0)
    total = stats.get("total_impactos_encontrados", 1)
    para(doc,
         f"⚠ {dual} impactos ({dual/total*100:.1f}% do total) requerem implementação de compatibilidade dual "
         "explícita — estes componentes processam CNPJ de forma que uma simples alteração de tipo não é suficiente.",
         italic=True, size=9.5, color=LARANJA)
    page_break(doc)
