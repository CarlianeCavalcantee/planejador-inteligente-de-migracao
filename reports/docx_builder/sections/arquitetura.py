from ..styles import heading, para, table, PRETO, LARANJA, comp_color, page_break


def build_atual(doc, data, num=3):
    heading(doc, "Arquitetura Atual", level=1, numbered=num)
    para(doc, "Fluxo atual de tráfego do CNPJ no ecossistema:", size=10)
    para(doc,
         "Cliente → Frontend Web / Mobile → API Gateway → Backend (Core) "
         "→ Banco de Dados & Mensageria / Integrações externas",
         bold=True, color=LARANJA, size=9.5)

    para(doc, "Pontos de Passagem e Tratamento do CNPJ:", bold=True, size=10)
    table(doc,
        ["CAMADA", "SITUAÇÃO ATUAL"],
        [
            ["Frontend / Mobile",
             "Entrada do dado com máscara estritamente numérica (##.###.###/####-##). "
             "Validação via regex \\d{14} ou inputMode='numeric'."],
            ["Backend",
             "Validação estrutural de dígitos verificadores com algoritmo módulo 11 clássico. "
             "Utilitários CpfCnpjUtils/CnpjValidator com lógica numérica."],
            ["Banco de Dados",
             "Persistência como VARCHAR(14) ou CHAR(14) — sem suporte a caracteres alfanuméricos. "
             "Índices e constraints baseados em 14 dígitos."],
            ["Mensageria",
             "Publicação de eventos com string numérica de 14 dígitos. "
             "Schema Registry sem suporte a formato alfanumérico."],
            ["Integrações",
             "Envio para bureaus de crédito, parceiros e órgãos reguladores em formato numérico rígido. "
             "Schemas XSD/WSDL com xs:pattern numérico."],
        ],
        col_widths=[3.5, 13.5]
    )


def build_proposta(doc, data, num=4):
    heading(doc, "Arquitetura Proposta", level=1, numbered=num)
    para(doc, "Implementação de Compatibilidade Dual para convivência entre os dois padrões:", size=10)
    para(doc,
         "Cliente → Frontend (Máscara Dinâmica) → Validação Dual → API Gateway (FF: enableAlphaCNPJ) "
         "→ Backend (Normalização) → Persistência VARCHAR(20) → Integrações / Parceiros",
         bold=True, color=LARANJA, size=9.5)

    para(doc, "Diretrizes Estratégicas:", bold=True, size=10)
    table(doc,
        ["DIRETRIZ", "DESCRIÇÃO"],
        [
            ["Convivência Harmônica",
             "O sistema aceitará CNPJ Numérico (ex: 12.345.678/0001-95) e Alfanumérico "
             "(ex: AB.12C.D34/0001-EF) de forma transparente."],
            ["Transparência Interna",
             "Microsserviços não devem quebrar ao receber o novo formato. "
             "Normalização ocorre na borda de entrada."],
            ["Feature Flag",
             "Ativação controlada por enableAlphaCNPJ nos ambientes DEV → QA → HML → PROD."],
            ["Rollback Seguro",
             "Desativação da flag restaura validação clássica sem necessidade de rollback de schema."],
        ],
        col_widths=[4, 13]
    )
    page_break(doc)
