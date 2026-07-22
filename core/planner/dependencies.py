"""
Inferência de dependências entre repositórios.
Extraído de output.py (_build_ordem_migracao).
"""
from collections import defaultdict

# Áreas que bloqueiam outras — quem tem BD/API deve migrar antes de quem tem só BE/FE
AREA_PESO_DEP = {
    "Banco de Dados":      0,
    "API/Contrato":        1,
    "Infraestrutura/CI":   2,
    "Configuração":        2,
    "Integrações":         3,
    "Processamento/Batch": 4,
    "Backend":             5,
    "Segurança/LGPD":      5,
    "Testes/Qualidade":    6,
    "Documentação":        6,
    "Frontend":            7,
    "Pessoa Jurídica/PJ":  7,
}

_PROVIDER_SUFFIXES = ("-lib", "-client", "-common", "-sdk", "-core")


def infer_dependencies(
    repos: dict[str, list],
    repo_areas: dict[str, set],
    matriz: list[dict],
) -> dict[str, set]:
    """
    Retorna deps[repo] = {repos que repo depende}.

    Regras:
    1. Sufixo lib/client/common → consumidor depende do provedor.
    2. Fluxos compartilhados: repo com BD/API precede repo com só BE/FE.
    """
    deps: dict[str, set] = defaultdict(set)

    # 1. Provedores por sufixo
    providers = {r for r in repos if any(r.endswith(s) for s in _PROVIDER_SUFFIXES)}
    for consumer in repos:
        if consumer in providers:
            continue
        for prov in providers:
            base = prov.split("-")[0]
            if base in consumer and prov != consumer:
                deps[consumer].add(prov)

    # 2. Fluxos compartilhados
    fluxo_repos_map: dict[str, list] = defaultdict(list)
    for m in matriz:
        f = m.get("fluxo")
        if f:
            fluxo_repos_map[f].append(m["repositorio"])

    for repos_fluxo in fluxo_repos_map.values():
        repos_uniq = list(dict.fromkeys(repos_fluxo))

        def _min_peso(r):
            return min((AREA_PESO_DEP.get(a, 9) for a in repo_areas.get(r, set())), default=9)

        repos_uniq.sort(key=_min_peso)
        for i, r_after in enumerate(repos_uniq[1:], 1):
            r_before = repos_uniq[i - 1]
            if r_before != r_after:
                deps[r_after].add(r_before)

    return deps


def topological_sort(
    repos: dict[str, list],
    deps: dict[str, set],
    repo_alta: dict[str, int],
) -> list[str]:
    """Kahn com desempate por carga Alta desc. Ciclos vão para o final."""
    import heapq
    from collections import defaultdict

    in_degree = {r: 0 for r in repos}
    adj: dict[str, set] = defaultdict(set)
    for r, predecessores in deps.items():
        for p in predecessores:
            if p in repos:
                adj[p].add(r)
                in_degree[r] += 1

    heap = [(-repo_alta.get(r, 0), r) for r, d in in_degree.items() if d == 0]
    heapq.heapify(heap)

    sorted_repos: list[str] = []
    while heap:
        _, r = heapq.heappop(heap)
        sorted_repos.append(r)
        for successor in sorted(adj.get(r, set())):
            in_degree[successor] -= 1
            if in_degree[successor] == 0:
                heapq.heappush(heap, (-repo_alta.get(successor, 0), successor))

    remaining = sorted(
        [r for r in repos if r not in sorted_repos],
        key=lambda r: (-repo_alta.get(r, 0), -len(repos[r])),
    )
    sorted_repos.extend(remaining)
    return sorted_repos
