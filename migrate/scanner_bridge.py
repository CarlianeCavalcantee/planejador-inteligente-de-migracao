"""
scanner_bridge.py — integração com o scanner de impacto existente.

Lê o JSON gerado por scanner.py (impacto_cnpj.json) e retorna a lista de
repos ordenada por prioridade de migração (Alta desc → total desc), com
metadados úteis para o migrador.

Uso:
    from migrate.scanner_bridge import load_scan, repos_from_scan

    repos = repos_from_scan("impacto_cnpj.json", repos_root="repos/")
    # repos = [RepoInfo(name="backoffice", path="repos/backoffice", ...), ...]
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass
class RepoInfo:
    name: str
    path: str          # caminho local (repos/<name>)
    alta: int          # impactos de complexidade Alta
    total: int         # total de impactos
    areas: list[str]   # áreas impactadas (ordenadas)
    priority: int      # posição na ordem_migracao do scanner (1 = primeiro)


def load_scan(scan_json: str) -> dict:
    """Carrega e valida o JSON do scanner."""
    path = Path(scan_json)
    if not path.exists():
        raise FileNotFoundError(f"Scan JSON não encontrado: {scan_json}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if "matriz_impacto" not in data:
        raise ValueError(f"Arquivo não parece ser um scan válido: {scan_json}")
    return data


def repos_from_scan(scan_json: str, repos_root: str = "repos") -> list[RepoInfo]:
    """
    Retorna repos com impacto, ordenados pela ordem_migracao do scanner.
    Apenas repos cujo diretório local existe em `repos_root` são incluídos.
    """
    data = load_scan(scan_json)
    root = Path(repos_root)

    # Índice de prioridade da ordem_migracao
    prio_index: dict[str, int] = {
        s["modulo"]: s["passo"]
        for s in data.get("ordem_migracao", [])
    }

    # Estatísticas por repo da seção impactos_por_repositorio
    stats: dict[str, dict] = data.get("estatisticas", {}).get("impactos_por_repositorio", {})

    results: list[RepoInfo] = []
    for repo_name, repo_stats in stats.items():
        repo_path = root / repo_name
        if not repo_path.is_dir():
            continue
        results.append(RepoInfo(
            name=repo_name,
            path=str(repo_path),
            alta=repo_stats.get("Alta", 0),
            total=repo_stats.get("total", 0),
            areas=repo_stats.get("areas", []),
            priority=prio_index.get(repo_name, 9999),
        ))

    results.sort(key=lambda r: (r.priority, -r.alta, -r.total))
    return results


def summary_from_scan(scan_json: str) -> dict:
    """Retorna um resumo compacto do scan para exibição no CLI."""
    data = load_scan(scan_json)
    stats = data.get("estatisticas", {})
    return {
        "scan_id":    data.get("scan_id", "—"),
        "data":       data.get("data_execucao", "—")[:19],
        "repos":      stats.get("total_repositorios_com_impacto", 0),
        "total":      stats.get("total_impactos_encontrados", 0),
        "alta":       stats.get("impactos_por_complexidade", {}).get("Alta", 0),
        "areas":      len(stats.get("impactos_por_area", {})),
    }
