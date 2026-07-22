"""
Estratégias de planejamento de trilhas.
Cada estratégia implementa cost(trail_idx, cluster, state) → float.
Menor custo = melhor alocação.
"""
from collections import defaultdict


class GreedyStrategy:
    """
    Estratégia atual: 40% carga + 60% fluxos partidos.
    Equilibra carga e mantém fluxos completos na mesma trilha.
    """
    name = "Greedy"
    description = "Equilibra carga (40%) e minimiza fluxos partidos (60%)"

    def cost(self, t_idx: int, cluster: list, state: dict) -> float:
        carga = state["carga"]
        max_carga = state["max_carga"] or 1
        fluxo_repos = state["fluxo_repos"]
        fluxo_repos_map = state["fluxo_repos_map"]
        trilhas = state["trilhas"]
        n_trilhas = len(trilhas)

        nova_carga = carga[t_idx] + sum(r["alta"] for r in cluster)
        carga_norm = nova_carga / max_carga

        fluxos_cluster = {f for r in cluster for f in fluxo_repos.get(r["modulo"], frozenset())}
        repos_outras = {r["modulo"] for ti, repos_t in enumerate(trilhas) if ti != t_idx for r in repos_t}
        partidos = sum(
            1 for f in fluxos_cluster
            if fluxo_repos_map.get(f, set()) & repos_outras
        )
        total_fluxos = len(fluxo_repos_map) or 1

        return 0.4 * (carga_norm) + 0.6 * (partidos / total_fluxos)


class BalancedStrategy:
    """
    Prioriza equilíbrio de carga (80%) sobre fluxos partidos (20%).
    Ideal quando as equipes têm capacidade similar e o prazo é apertado.
    """
    name = "Balanced"
    description = "Prioriza equilíbrio de carga (80%) sobre fluxos partidos (20%)"

    def cost(self, t_idx: int, cluster: list, state: dict) -> float:
        carga = state["carga"]
        max_carga = state["max_carga"] or 1
        fluxo_repos = state["fluxo_repos"]
        fluxo_repos_map = state["fluxo_repos_map"]
        trilhas = state["trilhas"]

        nova_carga = carga[t_idx] + sum(r["alta"] for r in cluster)
        carga_norm = nova_carga / max_carga

        fluxos_cluster = {f for r in cluster for f in fluxo_repos.get(r["modulo"], frozenset())}
        repos_outras = {r["modulo"] for ti, repos_t in enumerate(trilhas) if ti != t_idx for r in repos_t}
        partidos = sum(
            1 for f in fluxos_cluster
            if fluxo_repos_map.get(f, set()) & repos_outras
        )
        total_fluxos = len(fluxo_repos_map) or 1

        return 0.8 * carga_norm + 0.2 * (partidos / total_fluxos)


class MinDependenciesStrategy:
    """
    Minimiza fluxos partidos (90%) — aceita desequilíbrio de carga.
    Ideal quando coordenação entre equipes é o maior risco.
    """
    name = "MinDependencies"
    description = "Minimiza fluxos partidos (90%) — aceita desequilíbrio de carga"

    def cost(self, t_idx: int, cluster: list, state: dict) -> float:
        carga = state["carga"]
        max_carga = state["max_carga"] or 1
        fluxo_repos = state["fluxo_repos"]
        fluxo_repos_map = state["fluxo_repos_map"]
        trilhas = state["trilhas"]

        nova_carga = carga[t_idx] + sum(r["alta"] for r in cluster)
        carga_norm = nova_carga / max_carga

        fluxos_cluster = {f for r in cluster for f in fluxo_repos.get(r["modulo"], frozenset())}
        repos_outras = {r["modulo"] for ti, repos_t in enumerate(trilhas) if ti != t_idx for r in repos_t}
        partidos = sum(
            1 for f in fluxos_cluster
            if fluxo_repos_map.get(f, set()) & repos_outras
        )
        total_fluxos = len(fluxo_repos_map) or 1

        return 0.1 * carga_norm + 0.9 * (partidos / total_fluxos)


class CriticalFirstStrategy:
    """
    Concentra repos de alta complexidade na Trilha 1.
    Ideal quando há uma equipe sênior disponível para os casos mais difíceis.
    """
    name = "CriticalFirst"
    description = "Concentra repos de alta complexidade na Trilha 1 (equipe sênior)"

    def cost(self, t_idx: int, cluster: list, state: dict) -> float:
        carga = state["carga"]
        max_carga = state["max_carga"] or 1
        fluxo_repos = state["fluxo_repos"]
        fluxo_repos_map = state["fluxo_repos_map"]
        trilhas = state["trilhas"]

        nova_carga = carga[t_idx] + sum(r["alta"] for r in cluster)
        carga_norm = nova_carga / max_carga

        # Penaliza alocar repos de alta carga em trilhas != 0
        cluster_alta = sum(r["alta"] for r in cluster)
        senior_penalty = 0.0 if t_idx == 0 else (cluster_alta / (max_carga or 1)) * 0.5

        fluxos_cluster = {f for r in cluster for f in fluxo_repos.get(r["modulo"], frozenset())}
        repos_outras = {r["modulo"] for ti, repos_t in enumerate(trilhas) if ti != t_idx for r in repos_t}
        partidos = sum(
            1 for f in fluxos_cluster
            if fluxo_repos_map.get(f, set()) & repos_outras
        )
        total_fluxos = len(fluxo_repos_map) or 1

        return 0.3 * carga_norm + 0.4 * (partidos / total_fluxos) + 0.3 * senior_penalty


STRATEGIES = {
    "greedy":          GreedyStrategy,
    "balanced":        BalancedStrategy,
    "min_dependencies": MinDependenciesStrategy,
    "critical_first":  CriticalFirstStrategy,
}


def get_strategy(name: str = "greedy"):
    cls = STRATEGIES.get(name, GreedyStrategy)
    return cls()
