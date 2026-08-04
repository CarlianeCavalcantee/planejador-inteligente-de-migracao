"""
flow_validator.py — gate de qualidade por fluxo de negócio.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal

# ---------------------------------------------------------------------------
# Checks declarativos
# ---------------------------------------------------------------------------

_BUILTIN_CHECKS: list[dict] = [
    {
        "id": "CHK-001",
        "label": "Nenhuma conversao numerica (parseLong/parseInt)",
        "patterns": [
            r"(?i)(Long\.parseLong|Integer\.parseInt|toLong\s*\(|toInt\s*\()\s*.{0,40}(cnpj|cpfCnpj|cpf_cnpj|taxId|documento)",
            r"(?i)(cnpj|cpfCnpj|cpf_cnpj|taxId|documento).{0,40}(Long\.parseLong|Integer\.parseInt|toLong\s*\(|toInt\s*\()",
        ],
        "severity": "critical",
    },
    {
        "id": "CHK-002",
        "label": r"Nenhuma regex exclusivamente numerica (\d{14}, [0-9]{14})",
        "patterns": [
            r"(?i)(\\d\{14\}|\[0-9\]\{14\})",
            r"(?i)\^\[0-9\]\+\$|\^\\d\+\$",
        ],
        "severity": "critical",
    },
    {
        "id": "CHK-003",
        "label": "Nenhuma remocao de nao-digitos (replaceAll([^0-9]), /\\D/g)",
        "patterns": [
            r'(?i)(replaceAll|replace)\s*\(\s*"[^"]*\[\^0-9\][^"]*"\s*,\s*""\s*\)',
            r"(?i)\.replace\s*\(/\\D/g\s*,\s*['\"]['\"]",
            r"(?i)(onlyNumbers|onlyDigits|digitsOnly|somenteNumeros|removeNonDigits)\s*\(",
        ],
        "severity": "critical",
    },
    {
        "id": "CHK-004",
        "label": "Nenhuma mascara numerica antiga (99.999.999/9999-99)",
        "patterns": [
            r"[\"']9{2}\.9{3}\.9{3}/9{4}-9{2}[\"']",
            r"[\"']0{2}\.0{3}\.0{3}/0{4}-0{2}[\"']",
            r"\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}",
        ],
        "severity": "review",
    },
    {
        "id": "CHK-005",
        "label": "Nenhum padding numerico (padStart/lpad com '0')",
        "patterns": [
            r"(?i)(padStart|padEnd|lpad|leftPad).{0,20}(14|18).{0,10}[\"']0[\"']",
            r"(?i)String\.format\s*\(\s*[\"']%0?1[0-9]d[\"'].{0,40}(cnpj|cpfCnpj|taxId|documento)",
        ],
        "severity": "critical",
    },
    {
        "id": "CHK-006",
        "label": "Nenhuma comparacao de tamanho fixo (length == 14)",
        "patterns": [
            r"(?i)(cnpj|cpfCnpj|cpf_cnpj|taxId|documento).{0,20}\.length\s*[=!]{1,3}\s*14",
            r"(?i)(cnpj|cpfCnpj|cpf_cnpj|taxId|documento).{0,20}(length|size|len)\s*[=!<>]{1,3}\s*14",
        ],
        "severity": "review",
    },
    {
        "id": "CHK-007",
        "label": "Validacao compativel presente (CnpjUtils ou [A-Z0-9]{14})",
        "patterns": [],
        "severity": "review",
        "is_positive": True,
    },
]


# ---------------------------------------------------------------------------
# Estruturas de resultado
# ---------------------------------------------------------------------------

@dataclass
class CheckResult:
    id: str
    label: str
    passed: bool
    severity: Literal["critical", "review"]
    findings: list[dict] = field(default_factory=list)
    is_positive: bool = False


@dataclass
class FlowValidationResult:
    flow_id: str
    flow_name: str
    repos: list[str]
    checks: list[CheckResult]
    total_points: int
    migrated: int
    pending: int
    score: float
    status: str
    critical_failures: int
    review_failures: int


# ---------------------------------------------------------------------------
# Helpers: lêem campos independente da estrutura
#   - crua:     {_rule, repositorio, filepath, match: {status_migracao, trecho_codigo, linha}}
#   - achatada: {repositorio, arquivo, linha, trecho, status_migracao}  (matriz_impacto do JSON)
# ---------------------------------------------------------------------------

def _status(imp: dict) -> str:
    return imp.get("status_migracao") or imp.get("match", {}).get("status_migracao", "impacto")


def _trecho(imp: dict) -> str:
    return (
        imp.get("trecho")
        or imp.get("linha_conteudo")
        or imp.get("trecho_codigo")
        or imp.get("match", {}).get("trecho_codigo")
        or ""
    )


def _loc(imp: dict) -> tuple[str, str, str]:
    repo = imp.get("repositorio", "")
    arquivo = imp.get("arquivo") or imp.get("filepath", "")
    linha = str(imp.get("linha") or imp.get("match", {}).get("linha", ""))
    return repo, arquivo, linha


# ---------------------------------------------------------------------------
# Lógica de validação
# ---------------------------------------------------------------------------

def _compile_checks(cfg: dict) -> list[dict]:
    checks = list(_BUILTIN_CHECKS)
    for extra in cfg.get("flow_checks") or []:
        checks.append(extra)
    return checks


def _check_against_impacts(check: dict, flow_impacts: list[dict]) -> CheckResult:
    compiled = [re.compile(p, re.IGNORECASE) for p in check.get("patterns", [])]
    findings = []
    for imp in flow_impacts:
        trecho = _trecho(imp)
        for pat in compiled:
            if pat.search(trecho):
                repo, arquivo, linha = _loc(imp)
                findings.append({"repo": repo, "arquivo": arquivo, "linha": linha, "trecho": trecho[:120]})
                break
    return CheckResult(
        id=check["id"],
        label=check["label"],
        passed=len(findings) == 0,
        severity=check["severity"],
        findings=findings,
        is_positive=False,
    )


def _check_positive(check: dict, flow_impacts: list[dict]) -> CheckResult:
    compat = [i for i in flow_impacts if _status(i) == "compativel"]
    return CheckResult(
        id=check["id"],
        label=check["label"],
        passed=len(compat) > 0,
        severity=check["severity"],
        findings=[],
        is_positive=True,
    )


def _compute_status(score: float, critical: int, review: int, pending: int) -> str:
    if critical > 0:
        return "REPROVADO"
    if pending == 0 and review == 0:
        return "APROVADO"
    if score >= 90:
        return "QUASE PRONTO"
    return "REQUER REVISAO"


def _build_result(
    flow_id: str,
    flow_name: str,
    repos: list[str],
    impacts: list[dict],
    cfg: dict,
) -> FlowValidationResult:
    checks_def = _compile_checks(cfg)
    check_results: list[CheckResult] = []
    for chk in checks_def:
        if chk.get("is_positive"):
            check_results.append(_check_positive(chk, impacts))
        else:
            check_results.append(_check_against_impacts(chk, impacts))

    total = len(impacts)
    migrated = sum(1 for i in impacts if _status(i) == "compativel")
    pending = sum(1 for i in impacts if _status(i) == "impacto")
    score = round(migrated / total * 100, 1) if total > 0 else 100.0
    critical_failures = sum(1 for c in check_results if not c.passed and c.severity == "critical")
    review_failures = sum(1 for c in check_results if not c.passed and c.severity == "review")

    return FlowValidationResult(
        flow_id=flow_id,
        flow_name=flow_name,
        repos=repos,
        checks=check_results,
        total_points=total,
        migrated=migrated,
        pending=pending,
        score=score,
        status=_compute_status(score, critical_failures, review_failures, pending),
        critical_failures=critical_failures,
        review_failures=review_failures,
    )


# ---------------------------------------------------------------------------
# Modos de validação
# ---------------------------------------------------------------------------

def validate_flow_from_json(
    flow_id: str,
    scan_json: dict,
    cfg: dict,
) -> "FlowValidationResult | None":
    """Valida um fluxo a partir de um JSON de scan já gerado."""
    from core.flow import get_flows

    flows = get_flows(cfg)
    if flow_id not in flows:
        return None

    flow_def = flows[flow_id]
    flow_name = flow_def.get("name") or flow_id
    flow_repos = list(flow_def.get("repos") or [])

    matriz: list[dict] = scan_json.get("matriz_impacto") or []
    flow_impacts = [m for m in matriz if m.get("repositorio") in set(flow_repos)]

    return _build_result(flow_id, flow_name, flow_repos, flow_impacts, cfg)


def validate_flow_local(
    flow_id: str,
    local_dir: str,
    cfg: dict,
) -> "FlowValidationResult | None":
    """Re-escaneia os repos do fluxo (definidos no config) localmente e valida."""
    from core.flow import get_flows
    from core.engine import process_repo
    from core.local_client import scan_repo_local
    from core.config import area_priority

    flows = get_flows(cfg)
    if flow_id not in flows:
        return None

    flow_def = flows[flow_id]
    flow_name = flow_def.get("name") or flow_id
    flow_repos = list(flow_def.get("repos") or [])
    priority = area_priority(cfg)
    all_impacts: list[dict] = []

    for repo in flow_repos:
        try:
            candidates, content_map = scan_repo_local(
                repo, local_dir, cfg["ignore_paths"], cfg["regras"],
                include_large=False, bridge=None,
            )
            all_impacts.extend(process_repo(repo, candidates, content_map, priority, cfg))
        except Exception:
            pass

    return _build_result(flow_id, flow_name, flow_repos, all_impacts, cfg)


def _flow_path_keywords(flow_id: str, cfg: dict) -> list[str]:
    """
    Mapeia flow_id para keywords de caminho via tela_keywords do config.
    Fallback: usa o próprio flow_id como keyword.
    """
    flow_id_lower = flow_id.lower()
    for entry in cfg.get("tela_keywords") or []:
        kws = [k.lower() for k in (entry.get("keywords") or [])]
        if any(k in flow_id_lower or flow_id_lower in k for k in kws):
            return kws
    return [flow_id_lower]


def validate_repo(
    repo_path: str,
    cfg: dict,
    flow_id: str | None = None,
) -> FlowValidationResult:
    """
    Escaneia um repositório local e valida compatibilidade com CNPJ alfanumérico.

    repo_path : caminho para o repo clonado
    flow_id   : se informado, filtra arquivos cujo path contenha keywords do fluxo
    """
    import os
    from core.engine import process_repo
    from core.local_client import scan_repo_local
    from core.config import area_priority

    repo_path = os.path.normpath(repo_path)
    local_dir = os.path.dirname(repo_path) or "."
    repo_name = os.path.basename(repo_path)

    priority = area_priority(cfg)
    candidates, content_map = scan_repo_local(
        repo_name, local_dir, cfg["ignore_paths"], cfg["regras"],
        include_large=False, bridge=None,
    )

    if flow_id:
        keywords = _flow_path_keywords(flow_id, cfg)
        def _matches(fp: str) -> bool:
            return any(kw in fp.lower() for kw in keywords)
        candidates = [(fp, sha, rules) for fp, sha, rules in candidates if _matches(fp)]
        content_map = {fp: c for fp, c in content_map.items() if _matches(fp)}

    impacts = process_repo(repo_name, candidates, content_map, priority, cfg)
    flow_name = flow_id or repo_name

    return _build_result(flow_id or repo_name, flow_name, [repo_name], impacts, cfg)


# ---------------------------------------------------------------------------
# Renderização no terminal
# ---------------------------------------------------------------------------

_GREEN  = "\033[92m"
_RED    = "\033[91m"
_YELLOW = "\033[93m"
_BOLD   = "\033[1m"
_RESET  = "\033[0m"


def _icon(passed: bool, is_positive: bool = False) -> str:
    if is_positive:
        return f"{_GREEN}\u2714{_RESET}" if passed else f"{_YELLOW}~{_RESET}"
    return f"{_GREEN}\u2714{_RESET}" if passed else f"{_RED}\u2718{_RESET}"


def print_validation_result(result: FlowValidationResult, files_scanned: int = 0) -> None:
    w = 56
    print(f"\n{'─'*w}")
    if len(result.repos) == 1:
        print(f"{_BOLD}  Repositorio: {result.repos[0]}{_RESET}")
    if result.flow_id != (result.repos[0] if result.repos else ""):
        print(f"  Fluxo: {result.flow_name}")
    if files_scanned:
        print(f"  Arquivos analisados: {files_scanned}")
    elif len(result.repos) > 1:
        print(f"  Repos: {', '.join(result.repos)}")
    print(f"{'─'*w}")

    print(f"\n{_BOLD}  Verificacoes{_RESET}")
    for chk in result.checks:
        icon = _icon(chk.passed, chk.is_positive)
        print(f"  {icon}  {chk.label}")
        if not chk.passed and chk.findings:
            for finding in chk.findings[:3]:
                loc = f"{finding['repo']}/{finding['arquivo']}:{finding['linha']}"
                print(f"       {_YELLOW}\u21b3 {loc}{_RESET}")
                if finding["trecho"]:
                    print(f"         {finding['trecho'][:100]}")
            if len(chk.findings) > 3:
                print(f"       {_YELLOW}\u21b3 ... +{len(chk.findings) - 3} ocorrencia(s){_RESET}")

    bar_len = 30
    filled = int(bar_len * result.score / 100) if result.total_points > 0 else bar_len
    bar = f"{'█' * filled}{'░' * (bar_len - filled)}"

    print(f"\n{_BOLD}  Pontos analisados: {result.total_points}{_RESET}")
    print(f"  Migrados  .............. {result.migrated}")
    print(f"  Pendentes .............. {result.pending}")
    print(f"  Compatibilidade ........ {result.score:.0f}%  [{bar}]")

    print(f"\n{_BOLD}  Impactos{_RESET}")
    print(f"  {_RED}{result.critical_failures} critico(s){_RESET}")
    print(f"  {_YELLOW}{result.review_failures} revisao{_RESET}")

    color = _GREEN if result.status == "APROVADO" else (
        _RED if result.status == "REPROVADO" else _YELLOW
    )
    print(f"\n  Status: {color}{_BOLD}{result.status}{_RESET}")
    print(f"{'─'*w}\n")
