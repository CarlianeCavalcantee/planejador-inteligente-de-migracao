"""
Engine de análise: scan_file, deduplicação, chamadores estimados.
"""

import logging
import os
import re

from core.config import DUAL_COMPAT_RES, get_sql_alias_columns, FALSE_POSITIVE_RES

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Campos sensíveis ao domínio do documento
# ---------------------------------------------------------------------------

_SENSITIVE_FIELD = re.compile(
    r"(?i)\b(cnpj|cpfCnpj|cpf_cnpj|taxId|tax_id|federalId|federal_id"
    r"|docNumber|doc_number|nrDoc|nr_doc|numDoc|num_doc"
    r"|documentoFederal|documento_federal|nrDocumento|nr_documento"
    r"|corporateId|corporate_id|companyId|company_id|registrationNumber|registration_number"
    r"|documento|empresa|company)\b"
)

# ---------------------------------------------------------------------------
# Operações que realmente dependem do formato do documento
# (qualquer uma dessas na linha → pode ser impacto real)
# ---------------------------------------------------------------------------

_RELEVANT_OP = re.compile(
    r"(?i)("
    # manipulação de string
    r"\.replaceAll\s*\(|\.replace\s*\(|\.replaceFirst\s*\("
    r"|\.substring\s*\(|\.substr\s*\(|\.slice\s*\(|\.charAt\s*\("
    r"|\.startsWith\s*\(|\.endsWith\s*\(|\.contains\s*\(|\.indexOf\s*\("
    r"|\.matches\s*\("
    r"|\.length\s*\(\s*\)\s*[=!<>]|\.length\s*[=!<>]"
    r"|\.size\s*\(\s*\)\s*[=!<>]|\.size\s*[=!<>]"
    r"|\.len\s*[=!<>]|\blength\s*[=!<>]|\bsize\s*[=!<>]"
    # conversão numérica
    r"|Long\.parseLong|Integer\.parseInt"
    r"|BigInteger\s*\(|BigDecimal\s*\("
    r"|\btoLong\s*\(|\btoInt\s*\(|\bparseInt\s*\(|\bparseFloat\s*\(|Number\s*\("
    # regex / pattern
    r"|Pattern\.compile|\bcompile\s*\(|new\s+RegExp"
    r"|/\^?\[0-9\]|/\^?\\d|\\d\{14\}|\[0-9\]\{14\}"
    # validação
    r"|(?:validar|validate|check|calcular)(?:Cnpj|CpfCnpj|Documento|Document)"
    r"|validarCNPJ|validateCNPJ"
    r"|isCpf\b|isCnpj\b"
    r"|CpfCnpjValidator|CnpjValidator|DocumentoUtils"
    r"|@IsCNPJ|@ValidateCNPJ|@CnpjValid"
    r"|@Pattern\s*\(|@Digits\b|@Size\s*\(|@Min\s*\(|@Max\s*\(|@Positive\b"
    # formatação / máscara
    r"|formataCNPJ|formatarCNPJ|maskCNPJ|unmaskCnpj|formatCNPJ|formatCpfCnpj"
    r"|String\.format\s*\("
    r"|\bpadStart\s*\(|\bpadEnd\s*\(|\blpad\s*\(|\brpad\s*\("
    r"|StringUtils\.leftPad|StringUtils\.rightPad|CNPJ_FORMATADOR"
    # remoção de não-dígitos
    r"|\[\^0-9\]|/\\D/g"
    r"|onlyNumbers|onlyDigits|digitsOnly|somenteNumeros|apenasNumeros|removeNonDigits"
    # tipo numérico / DDL
    r"|\bNUMBER\s*\(|\bBIGINT\s*\(|\bNUMERIC\s*\("
    r"|VARCHAR\s*\(\s*1[0-9]|CHAR\s*\(\s*14"
    r"|columnDefinition|CellType\.NUMERIC"
    # anotações ORM / schema
    r"|@Column\s*\(|@Convert\s*\(|@JsonDeserialize|@JsonSerialize|@Serializable"
    # comparação / ordenação
    r"|compareTo\s*\(|Collections\.sort|\bsortBy\b|\borderBy\b|ORDER\s+BY"
    # cache / hash / criptografia
    r"|\bMD5\b|\bSHA256\b|SHA-256|\bSHA1\b|DigestUtils|MessageDigest"
    r"|cache\.put|cache\.get|cache\.set|redisTemplate|RedisTemplate|@Cacheable"
    # padding numérico
    r"|%0?1[0-9]d"
    # índice posicional fixo
    r"|\[\s*(?:0|1[0-3]|[2-9])\s*\]"
    r")"
)

# Padrões que indicam linha sem operação relevante (propagação pura)
_PURE_PROPAGATION = re.compile(
    r"""(?ix)
    # declaração de campo: private String cnpj;
    ^\s*(?:private|public|protected|val|var|let|const|readonly)\s+\w+\s+\w+\s*;
    # return simples: return cnpj; / return this.cnpj;
    |^\s*return\s+(?:this\.)?\w+\s*;
    # atribuição simples: this.cnpj = cnpj; / x = y;
    |^\s*(?:this\.)?\w+\s*=\s*(?:this\.)?\w+\s*;
    # chamada de getter isolada: empresa.getCnpj() / obj.getDocumento()
    |^\s*[\w.]+\.get\w+\s*\(\s*\)\s*;
    # chamada de setter isolada: dto.setCnpj(cnpj);
    |^\s*[\w.]+\.set\w+\s*\([^)]*\)\s*;
    # builder fluente: .cnpj(cnpj) / .documento(doc)
    |^\s*\.\w+\s*\([^)]*\)\s*$
    # map/json put com getter: map.put("cnpj", x.getCnpj())
    |^\s*[\w.]+\.put\s*\([^)]*\)\s*;
    # assinatura de getter/setter
    |^\s*(?:public|private|protected)?\s*\w+\s+(?:get|set)\w+\s*\(
    """
)


def _has_relevant_operation(line: str) -> bool:
    """Retorna True se a linha contém uma operação que depende do formato do documento."""
    return bool(_RELEVANT_OP.search(line))


def _is_pure_propagation(line: str) -> bool:
    """Retorna True se a linha apenas transporta o valor sem operar sobre ele."""
    return bool(_PURE_PROPAGATION.match(line))


def is_false_positive(line: str) -> bool:
    """Descarta linhas que não representam risco real de migração."""
    stripped = line.strip()
    if not stripped:
        return True
    # comentários e imports
    if any(pat.match(line) for pat in FALSE_POSITIVE_RES):
        return True
    # linha contém campo sensível mas nenhuma operação relevante → falso positivo
    if _SENSITIVE_FIELD.search(line) and not _has_relevant_operation(line):
        return True
    # propagação pura (getter/setter/return/atribuição simples)
    if _is_pure_propagation(line):
        return True
    return False


def scan_file(content: str, filepath: str, rule: dict) -> list[dict]:
    """Aplica os padrões pré-compilados da regra linha a linha."""
    compiled = rule.get("_compiled", [])
    matches = []
    for lineno, line in enumerate(content.splitlines(), start=1):
        if is_false_positive(line):
            continue
        for pat in compiled:
            if pat.search(line):
                matches.append({
                    "linha": lineno,
                    "trecho_codigo": line.strip()[:200],
                    "pattern_matched": pat.pattern,
                })
                break
    if not matches:
        log.debug("scan_file: 0 matches em %s (regra %s, %d padrões)",
                  filepath, rule.get('id', '?'), len(compiled))
    return matches


# ---------------------------------------------------------------------------
# Detector estrutural SQL: colunas VARCHAR(14)/CHAR(14) em tabelas que
# co-existem com colunas 'cnpj' — captura aliases como 'documento', 'taxId'
# ---------------------------------------------------------------------------

_SQL_ALIAS_COL = re.compile(
    r"(?i)^\s*(\w+)\s+(VARCHAR2?|CHAR|NVARCHAR2?)\s*\(\s*(1[0-9]|20)\s*\)",
)
_SQL_TABLE_START = re.compile(r"(?i)(CREATE|ALTER)\s+TABLE\s+(\S+)")
_SQL_CNPJ_COL = re.compile(r"(?i)\bcnpj\b")
_SQL_ALIAS_NAMES_DEFAULT = re.compile(
    r"(?i)\b(documento|doc_number|nr_doc|num_doc|tax_id|taxid|federal_id|federalid"
    r"|cpf_cnpj|cpfcnpj|company_id|corporate_id|registration_number|documento_federal)\b"
)


def scan_sql_structural(content: str, filepath: str, cfg: dict | None = None) -> list[dict]:
    """
    Detecta colunas com aliases configurados (VARCHAR 14-20) em tabelas que já
    possuem outra coluna com o campo principal no nome, ou colunas cujo nome
    bate diretamente com os aliases conhecidos.
    """
    alias_pattern_str = get_sql_alias_columns(cfg) if cfg else None
    alias_re = re.compile(alias_pattern_str) if alias_pattern_str else _SQL_ALIAS_NAMES_DEFAULT
    matches = []
    lines = content.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        tbl_m = _SQL_TABLE_START.search(line)
        if not tbl_m:
            i += 1
            continue
        block_start = i
        block_lines = []
        while i < len(lines):
            block_lines.append((i + 1, lines[i]))
            if ";" in lines[i] and i > block_start:
                break
            i += 1
        i += 1

        block_text = "\n".join(l for _, l in block_lines)
        table_has_main_col = bool(_SQL_CNPJ_COL.search(block_text))

        for lineno, bline in block_lines:
            if is_false_positive(bline):
                continue
            col_m = _SQL_ALIAS_COL.match(bline)
            if not col_m:
                continue
            col_name = col_m.group(1)
            is_alias = bool(alias_re.search(col_name))
            if table_has_main_col or is_alias:
                matches.append({
                    "linha": lineno,
                    "trecho_codigo": bline.strip()[:200],
                    "pattern_matched": "structural:sql_alias_column",
                })
    return matches


def requires_dual_compat(area: str, trecho: str) -> bool:
    if area in ("API/Contrato", "Integrações"):
        return True
    return any(pat.search(trecho) for pat in DUAL_COMPAT_RES)


_DUAL_COMPAT_MOTIVOS = [
    (re.compile(r"(?i)(validar|validate|check|calcular)Cnpj|validarCNPJ|validateCNPJ"), "Validador de CNPJ — precisa aceitar ambos os formatos durante transição"),
    (re.compile(r"(?i)(formataCNPJ|cnpjSemFormatacao|aplicaMascaraCNPJ|unmaskCnpj|maskCnpj)"), "Função de formatação/máscara — deve suportar entrada numérica e alfanumérica"),
    (re.compile(r"(?i)@(RestController|Controller|FeignClient|WebService|Endpoint)"), "Endpoint de API exposto — consumidores podem enviar formato antigo ou novo"),
    (re.compile(r"(?i)(soap|wsdl|feign|resttemplate|webclient|httpclient).{0,40}cnpj"), "Client HTTP/SOAP — integração externa pode receber qualquer formato"),
    (re.compile(r"(?i)(kafka|rabbit|sqs|sns|pubsub|eventbridge).{0,60}cnpj"), "Mensageria — mensagens em trânsito podem conter formato antigo"),
    (re.compile(r"(?i)@(XmlElement|XmlType).{0,30}[Cc]npj"), "Contrato XML/SOAP — schema deve aceitar ambos os formatos"),
]


def dual_compat_motivo(area: str, trecho: str) -> str:
    if area in ("API/Contrato", "Integrações"):
        return f"Área '{area}' requer compatibilidade dual por padrão — consumidores externos podem usar formato antigo ou novo"
    for pat, motivo in _DUAL_COMPAT_MOTIVOS:
        if pat.search(trecho):
            return motivo
    return "Padrão de código indica necessidade de suporte a ambos os formatos durante período de transição"


# ---------------------------------------------------------------------------
# Chamadores: conta referências ao símbolo detectado na linha, não ao arquivo
# ---------------------------------------------------------------------------

# Extrai o símbolo mais relevante de uma linha de código
_SYMBOL_RES = [
    re.compile(r"(?:public|private|protected)?\s+\w+\s+(\w+)\s*\("),  # método
    re.compile(r"(?:public|private|protected)?\s+\w+\s+(\w+)\s*;"),   # campo
    re.compile(r"class\s+(\w+)"),                                       # classe
    re.compile(r"(\w+)\s*\("),                                          # chamada
]


def _extract_symbol(trecho: str) -> str | None:
    """Extrai o nome do método/campo/classe mais relevante do trecho."""
    for pat in _SYMBOL_RES:
        m = pat.search(trecho)
        if m:
            sym = m.group(1)
            # Ignora símbolos genéricos demais
            if len(sym) >= 5 and sym.lower() not in (
                "string", "boolean", "integer", "object", "return", "false", "true",
                "void", "static", "final", "class", "public", "private"
            ):
                return sym
    return None


def count_callers(all_content: str, trecho: str, filepath: str) -> int:
    """
    Conta referências ao símbolo detectado no trecho.
    Fallback para nome do arquivo se nenhum símbolo for extraído.
    Subtrai 1 para excluir a própria definição.
    """
    symbol = _extract_symbol(trecho)
    if not symbol:
        # fallback: nome do arquivo sem extensão
        symbol = re.sub(r"\.[a-z]+$", "", os.path.basename(filepath), flags=re.IGNORECASE)
    if len(symbol) < 4:
        return 0
    try:
        return max(0, len(re.findall(r"\b" + re.escape(symbol) + r"\b", all_content)) - 1)
    except re.error:
        return 0


def deduplicate(impacts: list[dict], priority: dict[str, int]) -> list[dict]:
    """Por (repo, filepath, linha) mantém o impacto da área mais prioritária."""
    best: dict[tuple, dict] = {}
    for imp in impacts:
        key = (imp["repositorio"], imp["filepath"], imp["match"]["linha"])
        prio = priority.get(imp["_rule"]["area"], 999)
        if key not in best or prio < priority.get(best[key]["_rule"]["area"], 999):
            best[key] = imp
    return list(best.values())


def process_repo(
    repo: str,
    candidates: list[tuple],
    content_map: dict[str, str],
    priority: dict[str, int],
    cfg: dict | None = None,
) -> list[dict]:
    """Escaneia todos os candidatos e retorna impactos deduplicados com chamadores."""
    raw = []
    for filepath, _sha, matched_rules in candidates:
        content = content_map.get(filepath)
        if not content:
            continue
        for rule in matched_rules:
            for m in scan_file(content, filepath, rule):
                raw.append({
                    "_rule": rule,
                    "repositorio": repo,
                    "filepath": filepath,
                    "match": m,
                })
        # Varredura estrutural SQL (independente de regra)
        if filepath.lower().endswith(".sql"):
            _SQL_STRUCT_RULE = {
                "id": "DB-ALIAS-001",
                "area": "Banco de Dados",
                "complexidade": "Alta",
                "descricao_impacto": (
                    "Coluna com alias de CNPJ (documento, taxId, cpfCnpj, etc.) detectada "
                    "por análise estrutural SQL. Campo pode armazenar CNPJ sem usar a palavra "
                    "'cnpj' no nome — fora do escopo da Search API."
                ),
                "_compiled": [],
            }
            for m in scan_sql_structural(content, filepath, cfg):
                raw.append({
                    "_rule": _SQL_STRUCT_RULE,
                    "repositorio": repo,
                    "filepath": filepath,
                    "match": m,
                })

    impacts = deduplicate(raw, priority)

    all_content = "\n".join(content_map.values())
    for imp in impacts:
        trecho = imp["match"]["trecho_codigo"]
        callers = count_callers(all_content, trecho, imp["filepath"])
        imp["chamadores_estimados"] = callers
        imp["arquivo_critico"] = callers > 50

    return impacts
