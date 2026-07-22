"""
Engine de análise: scan_file, deduplicação, chamadores estimados.
"""

import logging
import os
import re

from core.config import DUAL_COMPAT_RES, get_sql_alias_columns, FALSE_POSITIVE_RES

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Falsos positivos estruturais — padrões que o regex de regra acerta mas
# que NÃO representam risco real de migração
# ---------------------------------------------------------------------------

_FP_NUMERIC_CONST = re.compile(
    r"(?i)(static\s+final|const|val|let|var)\s+\w*cnpj\w*\s*=\s*\d"
)
_FP_UI_LABEL = re.compile(
    r'(?i)["\']\s*(cpf[/\\]?cnpj|cnpj\s+do|cnpj:\s|campo\s+cnpj|preencher\s+com\s+cnpj)["\']'
)
_FP_CLASS_DECL_ONLY = re.compile(
    r"(?i)^\s*(public|private|protected|abstract|final)?\s*(class|interface|enum)\s+\w*[Cc]npj\w*\s*(extends\s+\w+|implements\s+[\w,\s]+)?\s*\{?\s*$"
)
_FP_BUFFER_PROP_ORDER = re.compile(
    r'(?i)@Buffer\s*\(.*propOrder\s*=\s*\{[^}]*cnpj[^}]*\}'
)
_FP_TRIVIAL_ACCESSOR = re.compile(
    r"(?i)^\s*(return\s+this\.cnpj\s*;|this\.cnpj\s*=\s*cnpj\s*;)\s*$"
)
_FP_COLUMN_NAME_ONLY = re.compile(
    r'(?i)@Column\s*\(\s*name\s*=\s*["\'][^"\']*(cnpj)[^"\']* ["\']\s*\)\s*$'
)
_FP_MASK_LITERAL_COMMENT = re.compile(
    r"(?i)^\s*(/[/*]|\*|#|<!--).{0,80}9{2}\.9{3}\.9{3}/9{4}-9{2}"
)
_FP_LOG_STATEMENT = re.compile(
    r"(?i)(log|logger|logging|console|print|println|printf|System\.out)\s*[.(].{0,60}cnpj"
)
_FP_GETTER_SETTER = re.compile(
    r"(?i)^\s*(get|set)[Cc]npj\s*\("
)

_STRUCTURAL_FP = [
    _FP_NUMERIC_CONST,
    _FP_UI_LABEL,
    _FP_CLASS_DECL_ONLY,
    _FP_BUFFER_PROP_ORDER,
    _FP_TRIVIAL_ACCESSOR,
    _FP_COLUMN_NAME_ONLY,
    _FP_MASK_LITERAL_COMMENT,
    _FP_LOG_STATEMENT,
    _FP_GETTER_SETTER,
]


def is_false_positive(line: str) -> bool:
    """Descarta linhas que são comentários, imports sem contexto ou ruído estrutural."""
    if not line.strip():
        return True
    if any(pat.match(line) for pat in FALSE_POSITIVE_RES):
        return True
    return any(pat.search(line) for pat in _STRUCTURAL_FP)


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
