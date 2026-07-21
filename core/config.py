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
