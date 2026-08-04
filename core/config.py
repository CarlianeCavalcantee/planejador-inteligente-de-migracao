"""
Carrega scanner-config.json ou scanner-config.yaml, valida o schema e pré-compila todos os regex das regras.
"""

import json
import logging
import re
import sys

import yaml

log = logging.getLogger(__name__)

_REQUIRED_TOP = {"sistema_escopo", "github_org", "output_file", "output_markdown", "ignore_paths", "prioridade_area", "regras"}

# Defaults genéricos usados quando o config não define os campos opcionais
_DEFAULT_TITULO = "Análise de Impacto"
_DEFAULT_NOME_CAMPO = "campo monitorado"
_DEFAULT_CHECKPOINT = "docs/output/scan.checkpoint.json"
_REQUIRED_RULE = {"area", "extensoes", "padroes", "descricao_impacto", "complexidade"}
_VALID_COMPLEXIDADE = {"Alta", "Média", "Baixa"}


def _validate_config(cfg: dict, path: str) -> None:
    """Valida campos obrigatórios e tipos básicos. Aborta com mensagem clara se inválido."""
    missing_top = _REQUIRED_TOP - cfg.keys()
    if missing_top:
        log.error("[config] %s: campos obrigatórios ausentes: %s", path, missing_top)
        sys.exit(1)

    if not isinstance(cfg["regras"], list) or not cfg["regras"]:
        log.error("[config] %s: 'regras' deve ser uma lista não-vazia.", path)
        sys.exit(1)

    for i, rule in enumerate(cfg["regras"]):
        missing = _REQUIRED_RULE - rule.keys()
        if missing:
            log.error("[config] regra[%d] campos ausentes: %s", i, missing)
            sys.exit(1)
        if rule["complexidade"] not in _VALID_COMPLEXIDADE:
            log.error("[config] regra[%d] complexidade inválida: '%s'. Use: %s", i, rule["complexidade"], _VALID_COMPLEXIDADE)
            sys.exit(1)
        if not isinstance(rule["padroes"], list) or not rule["padroes"]:
            log.error("[config] regra[%d] 'padroes' deve ser lista não-vazia.", i)
            sys.exit(1)


def load_config(path: str = "scanner-config.yaml") -> dict:
    with open(path, encoding="utf-8") as f:
        cfg = yaml.safe_load(f) if path.endswith((".yaml", ".yml")) else json.load(f)
    _validate_config(cfg, path)
    _compile_rules(cfg)
    _compile_compatibility_rules(cfg)
    return cfg


def _compile_rules(cfg: dict) -> None:
    """Pré-compila padrões de cada regra e os armazena em _compiled."""
    for rule in cfg.get("regras", []):
        rule["_compiled"] = []
        for pattern in rule["padroes"]:
            try:
                rule["_compiled"].append(re.compile(pattern, re.IGNORECASE))
            except re.error:
                pass  # padrão inválido — ignora silenciosamente


def get_titulo(cfg: dict) -> str:
    return cfg.get("titulo_analise") or _DEFAULT_TITULO


def get_nome_campo(cfg: dict) -> str:
    return cfg.get("nome_campo") or _DEFAULT_NOME_CAMPO


def get_checkpoint_file(cfg: dict) -> str:
    return cfg.get("checkpoint_file") or _DEFAULT_CHECKPOINT


def get_area_rationale(cfg: dict) -> dict:
    return cfg.get("area_rationale") or {}


def get_rollback_area(cfg: dict) -> dict:
    return cfg.get("rollback_area") or {}


def get_riscos_area(cfg: dict) -> dict:
    return cfg.get("riscos_area") or {}


def get_criterios_area(cfg: dict) -> dict:
    return cfg.get("criterios_area") or {}


def get_parceiros_conhecidos(cfg: dict) -> dict:
    return cfg.get("parceiros_conhecidos") or {}


def get_pontos_cegos(cfg: dict) -> list:
    return cfg.get("pontos_cegos") or []


def get_tela_keywords(cfg: dict) -> list:
    """Retorna lista de [keywords_list, nome_tela] do config, ou [] se não definido."""
    raw = cfg.get("tela_keywords") or []
    return [(entry["keywords"], entry["nome"]) for entry in raw if "keywords" in entry and "nome" in entry]


def get_compatibility_rules(cfg: dict) -> list[dict]:
    """Retorna regras de compatibilidade pré-compiladas."""
    return cfg.get("_compiled_compat", [])


def _compile_compatibility_rules(cfg: dict) -> None:
    """Pré-compila padrões das regras de compatibilidade."""
    compiled = []
    for rule in cfg.get("compatibility_rules", []):
        try:
            compiled.append({
                "id": rule["id"],
                "motivo": rule.get("motivo", rule["id"]),
                "_pat": re.compile(rule["match"], re.IGNORECASE),
            })
        except re.error as e:
            log.warning("[config] compatibility_rule %s regex inválido: %s", rule.get("id"), e)
    cfg["_compiled_compat"] = compiled


def get_sql_alias_columns(cfg: dict) -> str | None:
    """Retorna regex de aliases de coluna SQL configurados, ou None."""
    aliases = cfg.get("sql_alias_columns")
    if not aliases:
        return None
    escaped = "|".join(re.escape(a) for a in aliases)
    return f"(?i)\\b({escaped})\\b"


def get_secoes_extras(cfg: dict) -> list:
    return cfg.get("secoes_extras") or []


def get_rollback_base(cfg: dict) -> list:
    return cfg.get("rollback_base") or []


def area_priority(cfg: dict) -> dict[str, int]:
    order = cfg.get("prioridade_area", [])
    return {area: i for i, area in enumerate(order)}


# Padrões de falso positivo — compilados uma vez no import
FALSE_POSITIVE_RES = [
    re.compile(r"^\s*//"),
    re.compile(r"^\s*/\*"),
    re.compile(r"^\s*\*"),
    re.compile(r"^\s*#"),
    re.compile(r"^\s*import\s+(?!.*cnpj\s*=|.*cnpj\s*:)", re.IGNORECASE),
]

# Padrões que indicam necessidade de compatibilidade dual — compilados uma vez
DUAL_COMPAT_RES = [
    re.compile(r"(?i)(validar|validate|check|calcular)Cnpj|validarCNPJ|validateCNPJ"),
    re.compile(r"(?i)(formataCNPJ|cnpjSemFormatacao|aplicaMascaraCNPJ|unmaskCnpj|maskCnpj)"),
    re.compile(r"(?i)@(RestController|Controller|FeignClient|WebService|Endpoint)"),
    re.compile(r"(?i)(soap|wsdl|feign|resttemplate|webclient|httpclient).{0,40}cnpj"),
    re.compile(r"(?i)(kafka|rabbit|sqs|sns|pubsub|eventbridge).{0,60}cnpj"),
    re.compile(r"(?i)@(XmlElement|XmlType).{0,30}[Cc]npj"),
]
