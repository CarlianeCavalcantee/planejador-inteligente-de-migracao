"""Helpers de negócio: descrições técnicas por padrão e agrupamento de impactos."""
import re
from collections import defaultdict

# ── Mapeamento padrão → descrição técnica ─────────────────────────────────────
_PATTERN_DESCRIPTIONS = [
    (r"VARCHAR\s*\(\s*1[0-4]\s*\)",
     "Coluna declarada como VARCHAR({n}) — insuficiente para CNPJ alfanumérico (até 18 chars com máscara). Ampliar para VARCHAR(20)."),
    (r"CHAR\s*\(\s*1[0-4]\s*\)",
     "Coluna CHAR({n}) com tamanho fixo numérico. Converter para VARCHAR(20) para suportar formato alfanumérico."),
    (r"NUMBER\s*\(\s*1[0-4]\s*\)",
     "Coluna NUMBER({n}) armazena CNPJ como inteiro — perderá zeros à esquerda e não suporta letras. Migrar para VARCHAR(20)."),
    (r"@Column.*length\s*=\s*1[0-4]",
     "Anotação JPA @Column(length={n}) restringe o campo a 14 caracteres. Atualizar para length=20 e regenerar schema."),
    (r"BigInteger|Long",
     "Tipo numérico (BigInteger/Long) usado para armazenar CNPJ — incompatível com caracteres alfanuméricos. Migrar para String."),
    (r"\\d\{14\}|\\d{14}",
     "Regex \\d{14} aceita apenas dígitos. Substituir por padrão alfanumérico: [A-Z0-9]{14}."),
    (r"Pattern\.compile|matches\(",
     "Pattern.compile ou String.matches com regex numérica restritiva. Atualizar expressão para aceitar [A-Z0-9]."),
    (r"@CPF|@CNPJ|@CpfCnpj|CpfCnpjValidator|CnpjValidator",
     "Bean Validation com anotação de validação de CNPJ numérico. Atualizar biblioteca ou implementação para suportar formato alfanumérico."),
    (r"CpfCnpjUtils|CnpjUtils|CpfUtils|DocumentoUtils",
     "Classe utilitária de CPF/CNPJ com lógica de validação numérica. Refatorar algoritmo de dígito verificador para aceitar base alfanumérica."),
    (r"substring\s*\(\s*0\s*,\s*[89]|slice\s*\(\s*0\s*,\s*[89]|\.substring\(8",
     "Acesso posicional por índice fixo (substring/slice) assumindo CNPJ de 14 dígitos. Refatorar para usar parsing semântico."),
    (r"inputMode.*numeric|type.*number|mask.*\d.*\d.*\d",
     "Campo de input com inputMode='numeric' ou type='number' bloqueará letras. Alterar para inputMode='text' com validação customizada."),
    (r"##\.###\.###/####-##|\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}",
     "Máscara de formatação exclusivamente numérica (##.###.###/####-##). Atualizar para máscara dinâmica que aceite [A-Z0-9]."),
    (r"Flyway|Liquibase|V\d+__",
     "Script de migração de banco (Flyway/Liquibase) com tipo de coluna incompatível. Criar nova migration para ampliar o campo."),
    (r"openapi|swagger|@ApiModel|@Schema",
     "Schema OpenAPI/Swagger com pattern numérico (^\\d{14}$). Atualizar pattern para ^[A-Z0-9]{14}$ e maxLength para 20."),
    (r"\.proto|protobuf|message\s+\w+",
     "Definição Protobuf com campo CNPJ tipado como int64 ou com validação numérica. Migrar para string com validação no serviço."),
    (r"kafka|KafkaTemplate|@KafkaListener|ProducerRecord",
     "Produtor/consumidor Kafka com payload contendo CNPJ. Validar schema do tópico e atualizar Schema Registry se aplicável."),
    (r"RabbitMQ|@RabbitListener|AmqpTemplate|rabbitTemplate",
     "Integração RabbitMQ com mensagem contendo CNPJ numérico. Atualizar contrato de mensagem e validação do consumidor."),
    (r"SQS|SNS|@SqsListener",
     "Integração AWS SQS/SNS com payload CNPJ. Atualizar schema de mensagem e validação do handler."),
    (r"SOAP|wsdl|XSD|xs:pattern",
     "Schema XSD/WSDL com xs:pattern restritivo a dígitos. Atualizar pattern para aceitar caracteres alfanuméricos."),
    (r"CNAB|remessa|retorno|layout.*fixo|posicao.*\d",
     "Layout de arquivo CNAB/posicional com campo CNPJ de tamanho fixo 14. Ampliar campo e atualizar parser de posições."),
    (r"SPED|NFS-e|NFe|CTe|eSocial|EFD",
     "Arquivo fiscal (SPED/NFS-e/NFe) com campo CNPJ em layout fixo. Verificar versão do schema fiscal e atualizar gerador."),
    (r"Jasper|\.jrxml|JasperReport",
     "Template JasperReports (.jrxml) com máscara numérica de CNPJ. Atualizar expressão de formatação no template."),
    (r"Freemarker|Velocity|\.ftl|\.vm",
     "Template Freemarker/Velocity com formatação numérica de CNPJ. Atualizar expressão de formatação no template."),
    (r"hardcoded|[0-9]{2}\.[0-9]{3}\.[0-9]{3}/[0-9]{4}-[0-9]{2}",
     "CNPJ real hardcoded no código-fonte — violação de LGPD. Substituir por variável de ambiente ou massa sintética e auditar histórico git."),
    (r"DTO|Request|Response|record\s+\w+",
     "DTO/Record com campo CNPJ tipado como numérico ou com validação restritiva. Atualizar tipo para String e ajustar validações."),
    (r"@Entity|@Table|@MappedSuperclass",
     "Entidade JPA com campo CNPJ mapeado com restrição numérica. Atualizar @Column e executar migration de schema."),
    (r"SELECT|INSERT|UPDATE|WHERE.*cnpj|JOIN.*cnpj",
     "Query SQL com filtro ou comparação de CNPJ assumindo formato numérico. Revisar predicados e índices para suportar alfanumérico."),
]

_RULE_AREA_MAP = {
    "SEC-001": "Segurança/LGPD",
    "CFG-001": "Configuração",
    "INFRA-001": "Infraestrutura/CI",
    "JPA-001": "Banco de Dados",
    "DB-001": "Banco de Dados",
    "MIGRATION-001": "Banco de Dados",
    "API-001": "API/Contrato",
    "INT-001": "Integrações",
    "XSD-001": "Integrações",
    "BE-001": "Backend",
    "STR-001": "Backend",
    "BATCH-001": "Processamento/Batch",
    "JASPER-001": "Processamento/Batch",
    "TEMPLATE-001": "Processamento/Batch",
    "TEST-001": "Testes/Qualidade",
    "FE-001": "Frontend",
    "DOC-001": "Documentação",
}

_RULE_DESCRIPTIONS = {
    "SEC-001": "CNPJ real hardcoded no código-fonte — violação de LGPD. Substituir por variável de ambiente ou massa sintética e auditar histórico git.",
    "CFG-001": "Arquivo de configuração (application.yml/.env) com CNPJ fixo. Externalizar para variável de ambiente.",
    "INFRA-001": "Dockerfile/Jenkinsfile com CNPJ em variável de ambiente hardcoded. Externalizar para secrets manager.",
    "JPA-001": "Entidade JPA com @Column(length=14) — insuficiente para CNPJ alfanumérico. Atualizar para length=20 e criar migration.",
    "DB-001": "Coluna de banco com tipo/tamanho incompatível (VARCHAR(14), NUMBER(14)). Ampliar para VARCHAR(20).",
    "MIGRATION-001": "Script Flyway/Liquibase com tipo de coluna incompatível. Criar nova migration para ampliar o campo.",
    "API-001": "Schema OpenAPI/Swagger/Protobuf com pattern numérico (^\\d{14}$). Atualizar para ^[A-Z0-9]{14}$ e maxLength=20.",
    "INT-001": "Integração (Kafka/SQS/SOAP/REST) com payload CNPJ numérico. Atualizar contrato e validação do consumidor.",
    "XSD-001": "Schema XSD/WSDL com xs:pattern restritivo a dígitos. Atualizar pattern para aceitar alfanumérico.",
    "BE-001": "Validador, formatador ou regex \\d{14} no backend. Atualizar para aceitar [A-Z0-9]{14}.",
    "STR-001": "Acesso posicional por índice fixo (substring/slice) assumindo 14 dígitos. Refatorar para parsing semântico.",
    "BATCH-001": "Job/ETL/SPED/NFS-e com campo CNPJ em layout fixo. Ampliar campo e atualizar parser de posições.",
    "JASPER-001": "Template JasperReports (.jrxml) com máscara numérica. Atualizar expressão de formatação.",
    "TEMPLATE-001": "Template Freemarker/Velocity com formatação numérica de CNPJ. Atualizar expressão de formatação.",
    "TEST-001": "Fixture/mock/seed com CNPJ hardcoded numérico. Atualizar massa de testes para incluir CNPJs alfanuméricos.",
    "FE-001": "Máscara, validação ou inputMode='numeric' no frontend. Atualizar para aceitar [A-Z0-9] com máscara dinâmica.",
    "DOC-001": "README/documentação com CNPJ exclusivamente numérico como exemplo. Atualizar exemplos para incluir formato alfanumérico.",
}


def describe_impact(item: dict) -> str:
    """Gera descrição técnica específica a partir do item de impacto."""
    obs = item.get("observacoes", "") or ""
    evidencia = item.get("evidencia", {}) or {}
    trecho = evidencia.get("trecho_codigo", "") or ""
    descricao_original = item.get("descricao_impacto", "") or ""

    # Extrair regra do campo observacoes
    rule_match = re.search(r"Regra:\s*([\w-]+)", obs)
    rule_id = rule_match.group(1) if rule_match else ""

    if rule_id in _RULE_DESCRIPTIONS:
        base = _RULE_DESCRIPTIONS[rule_id]
    else:
        # Tentar match por padrão no trecho de código
        base = None
        for pattern, desc in _PATTERN_DESCRIPTIONS:
            if re.search(pattern, trecho, re.IGNORECASE) or re.search(pattern, descricao_original, re.IGNORECASE):
                base = desc
                break
        if not base:
            base = descricao_original[:200] if descricao_original else "Impacto identificado pelo scanner."

    # Enriquecer com trecho de código se disponível
    if trecho and len(trecho) < 120:
        return f"{base} Trecho: `{trecho.strip()}`"
    return base


def extract_rule_id(item: dict) -> str:
    obs = item.get("observacoes", "") or ""
    m = re.search(r"Regra:\s*([\w-]+)", obs)
    return m.group(1) if m else "—"


def group_impacts(impacts: list, max_rows: int = 80) -> list:
    """
    Agrupa impactos por (repositório, componente, regra) para evitar
    centenas de linhas repetidas. Retorna lista de dicts consolidados.
    """
    groups: dict = defaultdict(lambda: {"count": 0, "linhas": [], "item": None})
    for item in impacts:
        repo = item.get("repositorio", "—")
        comp = item.get("componente", "—")
        rule = extract_rule_id(item)
        key = (repo, comp, rule)
        g = groups[key]
        g["count"] += 1
        ev = item.get("evidencia", {}) or {}
        linha = ev.get("linha")
        if linha and len(g["linhas"]) < 3:
            g["linhas"].append(str(linha))
        if g["item"] is None:
            g["item"] = item

    result = []
    for (repo, comp, rule), g in sorted(
        groups.items(), key=lambda x: (-x[1]["count"], x[0][0])
    ):
        item = g["item"]
        linhas_str = ", ".join(g["linhas"]) + ("…" if g["count"] > len(g["linhas"]) else "")
        result.append({
            "repositorio": repo,
            "componente": comp,
            "regra": rule,
            "linhas": linhas_str or "—",
            "ocorrencias": g["count"],
            "complexidade": item.get("complexidade", "—"),
            "prioridade": item.get("prioridade", "—"),
            "descricao": describe_impact(item),
            "requer_dual": item.get("requer_compatibilidade_dual", False),
        })

    # Se ainda muito grande, colapsar por (repo, regra)
    if len(result) > max_rows:
        collapsed: dict = defaultdict(lambda: {"count": 0, "comps": set(), "item": None})
        for r in result:
            key = (r["repositorio"], r["regra"])
            c = collapsed[key]
            c["count"] += r["ocorrencias"]
            c["comps"].add(r["componente"].split("/")[-1])
            if c["item"] is None:
                c["item"] = r
        result = []
        for (repo, rule), c in sorted(
            collapsed.items(), key=lambda x: (-x[1]["count"], x[0][0])
        ):
            item = c["item"]
            comps_str = ", ".join(list(c["comps"])[:3]) + ("…" if len(c["comps"]) > 3 else "")
            result.append({
                "repositorio": repo,
                "componente": comps_str,
                "regra": rule,
                "linhas": "—",
                "ocorrencias": c["count"],
                "complexidade": item["complexidade"],
                "prioridade": item["prioridade"],
                "descricao": item["descricao"],
                "requer_dual": item["requer_dual"],
            })

    return result


def impacts_by_area(matriz: list) -> dict:
    """Retorna dict {area: [items]} filtrado e ordenado."""
    result = defaultdict(list)
    for item in matriz:
        result[item.get("area", "Outros")].append(item)
    return dict(result)


def top_files(matriz: list, n: int = 20) -> list:
    """Retorna os n arquivos com mais impactos."""
    counts: dict = defaultdict(lambda: {"count": 0, "repo": "", "areas": set()})
    for item in matriz:
        ev = item.get("evidencia", {}) or {}
        f = ev.get("arquivo") or item.get("componente", "—")
        counts[f]["count"] += 1
        counts[f]["repo"] = item.get("repositorio", "—")
        counts[f]["areas"].add(item.get("area", "—"))
    return sorted(
        [{"arquivo": k, **v, "areas": ", ".join(sorted(v["areas"]))} for k, v in counts.items()],
        key=lambda x: -x["count"]
    )[:n]
