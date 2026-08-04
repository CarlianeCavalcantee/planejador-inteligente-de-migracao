"""
Análise orientada a fluxo de negócio.

Lê a seção `flows` do config e produz, para cada fluxo:
  - contagem de compatíveis / revisão / impactos
  - score de maturidade (0–100%)
  - status de homologação
  - matriz área × repo dentro do fluxo
"""

from __future__ import annotations


def get_flows(cfg: dict) -> dict:
    """Retorna o dict `flows` do config, ou {} se não definido."""
    return cfg.get("flows") or {}


def repos_for_flow(flow_id: str, cfg: dict) -> list[str]:
    """Lista de repos de um fluxo específico. Retorna [] se o fluxo não existe."""
    flows = get_flows(cfg)
    if flow_id not in flows:
        return []
    entry = flows[flow_id]
    return list(entry.get("repos") or [])


def all_flow_repos(cfg: dict) -> set[str]:
    """Conjunto de todos os repos mapeados em qualquer fluxo."""
    repos: set[str] = set()
    for entry in get_flows(cfg).values():
        repos.update(entry.get("repos") or [])
    return repos


# ---------------------------------------------------------------------------
# Maturidade por fluxo
# ---------------------------------------------------------------------------

_STATUS_ORDER = {"impacto": 0, "revisao": 1, "compativel": 2}


def _repo_summary(repo: str, impacts: list[dict]) -> dict:
    """Resumo de um repo dentro de um fluxo: contagens + áreas."""
    repo_impacts = [m for m in impacts if m["repositorio"] == repo]
    by_area: dict[str, dict] = {}
    for m in repo_impacts:
        area = m["area"]
        if area not in by_area:
            by_area[area] = {"compativel": 0, "revisao": 0, "impacto": 0}
        status = m.get("status_migracao", "impacto")
        by_area[area][status] = by_area[area].get(status, 0) + 1

    total = len(repo_impacts)
    compativeis = sum(1 for m in repo_impacts if m.get("status_migracao") == "compativel")
    revisao = sum(1 for m in repo_impacts if m.get("status_migracao") == "revisao")
    impactos = sum(1 for m in repo_impacts if m.get("status_migracao", "impacto") == "impacto")

    return {
        "repo": repo,
        "total": total,
        "compativel": compativeis,
        "revisao": revisao,
        "impacto": impactos,
        "areas": by_area,
    }


def _flow_status(score: float, impactos: int, revisao: int) -> str:
    if impactos == 0 and revisao == 0:
        return "Pronto para homologação"
    if impactos == 0:
        return "Requer revisão"
    if score >= 80:
        return "Em progresso — riscos residuais"
    return "Não recomendado para homologação"


def build_flow_analysis(matriz: list[dict], cfg: dict) -> list[dict]:
    """
    Retorna lista de análises por fluxo, ordenada por score ascendente
    (fluxos mais críticos primeiro).
    """
    flows = get_flows(cfg)
    if not flows:
        return []

    result = []
    for flow_id, flow_def in flows.items():
        name = flow_def.get("name") or flow_id
        flow_repos = list(flow_def.get("repos") or [])

        # Impactos que pertencem a este fluxo
        flow_impacts = [m for m in matriz if m["repositorio"] in flow_repos]

        total = len(flow_impacts)
        compativeis = sum(1 for m in flow_impacts if m.get("status_migracao") == "compativel")
        revisao = sum(1 for m in flow_impacts if m.get("status_migracao") == "revisao")
        impactos = sum(1 for m in flow_impacts if m.get("status_migracao", "impacto") == "impacto")

        # Score: arquivos sem impacto ativo / total analisados
        # Usa total de ocorrências (compativel + revisao + impacto) como denominador
        score = round((compativeis / total * 100) if total > 0 else 100.0, 1)

        # Matriz por repo
        repos_summary = [_repo_summary(r, flow_impacts) for r in flow_repos]

        # Matriz por área dentro do fluxo
        areas: dict[str, dict] = {}
        for m in flow_impacts:
            area = m["area"]
            if area not in areas:
                areas[area] = {"compativel": 0, "revisao": 0, "impacto": 0}
            status = m.get("status_migracao", "impacto")
            areas[area][status] = areas[area].get(status, 0) + 1

        result.append({
            "id": flow_id,
            "name": name,
            "repos": flow_repos,
            "total_ocorrencias": total,
            "compativel": compativeis,
            "revisao": revisao,
            "impacto": impactos,
            "score": score,
            "status": _flow_status(score, impactos, revisao),
            "repos_summary": repos_summary,
            "areas": areas,
        })

    # Fluxos mais críticos (menor score) primeiro
    result.sort(key=lambda f: (f["score"], f["name"]))
    return result
