"""
Orquestrador do planner: recebe a matriz de impactos e retorna o plano completo.
Substitui as funções _build_* de output.py que fazem planejamento.
"""
from collections import defaultdict

from core.config import area_priority
from .dependencies import infer_dependencies, topological_sort, AREA_PESO_DEP
from .trails import build_trails
from .risk import (
    build_gargalos, build_spof, build_heatmap_risco,
    build_risk_score, build_sugestoes_movimentacao,
)
from .metrics import build_metrics
from .simulation import simulate_trails

_AREA_RATIONALE = {
    "Segurança/LGPD":      "Remover dados reais do código antes de qualquer outra mudança.",
    "Banco de Dados":      "Migrar schema primeiro — todas as camadas dependem do tipo da coluna.",
    "API/Contrato":        "Versionar contratos antes de alterar implementação para não quebrar consumidores.",
    "Infraestrutura/CI":   "Atualizar pipelines para que builds e testes usem o novo formato.",
    "Configuração":        "Externalizar CNPJs fixos antes de subir nova versão em produção.",
    "Integrações":         "Comunicar e alinhar parceiros externos antes de alterar payloads.",
    "Processamento/Batch": "Atualizar layouts de arquivo e validações de ETL após schema de BD.",
    "Backend":             "Refatorar validadores e lógica de negócio após BD e contratos estabilizados.",
    "Testes/Qualidade":    "Atualizar massa de dados e fixtures para cobrir o novo formato.",
    "Documentação":        "Atualizar docs e exemplos após implementação concluída.",
    "Frontend":            "Atualizar máscaras e validações de UI por último (menor risco de bloqueio).",
    "Pessoa Jurídica/PJ":  "Revisar entidades, DTOs e fluxos PJ após BD e contratos estabilizados.",
}


def build_ordem_migracao(matriz: list[dict], cfg: dict) -> list[dict]:
    """Topological sort com dependências inferidas. Retorna lista ordenada de módulos."""
    priority = area_priority(cfg)

    repos: dict[str, list] = {}
    for m in matriz:
        repos.setdefault(m["repositorio"], []).append(m)

    repo_areas: dict[str, set] = {r: {m["area"] for m in itens} for r, itens in repos.items()}
    repo_alta:  dict[str, int] = {r: sum(1 for m in itens if m["complexidade"] == "Alta") for r, itens in repos.items()}

    deps = infer_dependencies(repos, repo_areas, matriz)
    sorted_repos = topological_sort(repos, deps, repo_alta)

    result = []
    for step, repo in enumerate(sorted_repos, start=1):
        itens = repos[repo]
        areas_no_repo = sorted(repo_areas[repo], key=lambda a: priority.get(a, 999))
        areas_detalhes = []
        for area in areas_no_repo:
            area_itens = [m for m in itens if m["area"] == area]
            areas_detalhes.append({
                "area": area,
                "total_impactos": len(area_itens),
                "impactos_alta_complexidade": sum(1 for m in area_itens if m["complexidade"] == "Alta"),
                "requerem_compatibilidade_dual": sum(1 for m in area_itens if m["requer_compatibilidade_dual"]),
                "rationale": _AREA_RATIONALE.get(area, ""),
            })
        predecessores = sorted(deps.get(repo, set()) & repos.keys())
        result.append({
            "passo": step,
            "modulo": repo,
            "total_impactos": len(itens),
            "impactos_alta_complexidade": repo_alta[repo],
            "requerem_compatibilidade_dual": sum(1 for m in itens if m["requer_compatibilidade_dual"]),
            "depende_de": predecessores,
            "areas": areas_detalhes,
        })
    return result


def build_plan(matriz: list[dict], cfg: dict) -> dict:
    """
    Ponto de entrada principal do planner.
    Retorna o plano completo: ordem, trilhas, métricas, simulação, risco.
    """
    ordem_migracao = build_ordem_migracao(matriz, cfg)
    gargalos       = build_gargalos(matriz, ordem_migracao)
    spof           = build_spof(matriz, ordem_migracao)
    trilhas        = build_trails(ordem_migracao, cfg, matriz)
    metrics        = build_metrics(ordem_migracao, trilhas, gargalos, spof, matriz)
    simulation     = simulate_trails(ordem_migracao, cfg, matriz)

    return {
        "ordem_migracao":        ordem_migracao,
        "trilhas":               trilhas,
        "gargalos":              gargalos,
        "spof":                  spof,
        "heatmap_risco":         build_heatmap_risco(ordem_migracao, gargalos, spof, trilhas),
        "risk_score":            build_risk_score(ordem_migracao, gargalos, spof, trilhas, matriz),
        "sugestoes_movimentacao": build_sugestoes_movimentacao(trilhas, ordem_migracao),
        "esforco":               metrics["esforco"],
        "coordination_cost":     metrics["coordination_cost"],
        "critical_path":         metrics["critical_path"],
        "bottleneck_index":      metrics["bottleneck_index"],
        "migration_readiness":   metrics["migration_readiness"],
        "simulation":            simulation,
    }
