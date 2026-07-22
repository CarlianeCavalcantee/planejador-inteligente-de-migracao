"""
Construção de trilhas paralelas.
Extraído de output.py (_build_trilhas) e refatorado para usar Strategy.
"""
from collections import defaultdict
from .strategies import GreedyStrategy, get_strategy


def build_trails(
    ordem_migracao: list[dict],
    cfg: dict,
    matriz: list[dict] | None = None,
    strategy=None,
) -> dict:
    """
    Agrupa repos por afinidade e divide em N trilhas paralelas.
    N configurável via cfg['trilhas'] (padrão: 2).
    strategy: instância de uma Strategy (padrão: GreedyStrategy).
    """
    if strategy is None:
        strategy = get_strategy(cfg.get("strategy", "greedy"))

    n_trilhas = int(cfg.get("trilhas", 2))

    # Mapa repo → fluxos
    repo_fluxos: dict[str, frozenset] = {}
    fluxo_repos: dict[str, set] = defaultdict(set)
    if matriz:
        tmp: dict[str, set] = {}
        for m in matriz:
            f = m.get("fluxo")
            if f:
                tmp.setdefault(m["repositorio"], set()).add(f)
                fluxo_repos[f].add(m["repositorio"])
        repo_fluxos = {r: frozenset(fs) for r, fs in tmp.items()}

    def afinidade(a, b):
        def jaccard(x, y):
            if not x and not y:
                return 1.0
            return len(x & y) / len(x | y)
        j_areas  = jaccard(a["areas"], b["areas"])
        j_fluxos = jaccard(repo_fluxos.get(a["modulo"], frozenset()),
                           repo_fluxos.get(b["modulo"], frozenset()))
        return 0.4 * j_areas + 0.6 * j_fluxos

    repos = [
        {
            "modulo": m["modulo"],
            "passo":  m["passo"],
            "total":  m["total_impactos"],
            "alta":   m["impactos_alta_complexidade"],
            "dual":   m["requerem_compatibilidade_dual"],
            "areas":  frozenset(a["area"] for a in m["areas"]),
        }
        for m in ordem_migracao
    ]

    # Clustering por afinidade >= 0.4
    clusters, used = [], set()
    for i, r in enumerate(repos):
        if i in used:
            continue
        cluster = [r]
        used.add(i)
        for j, s in enumerate(repos):
            if j not in used and afinidade(r, s) >= 0.4:
                cluster.append(s)
                used.add(j)
        clusters.append(cluster)
    clusters.sort(key=lambda c: sum(r["alta"] for r in c), reverse=True)

    # Divisão greedy em N trilhas usando a estratégia injetada
    trilhas = [[] for _ in range(n_trilhas)]
    carga   = [0] * n_trilhas
    max_carga = sum(r["alta"] for r in repos) or 1

    for cluster in clusters:
        state = {
            "carga": carga,
            "max_carga": max_carga,
            "fluxo_repos": repo_fluxos,
            "fluxo_repos_map": fluxo_repos,
            "trilhas": trilhas,
        }
        t = min(range(n_trilhas), key=lambda i: strategy.cost(i, cluster, state))
        trilhas[t].extend(cluster)
        carga[t] += sum(r["alta"] for r in cluster)

    # Mapa repo → trilha
    repo_trilha = {r["modulo"]: t for t, repos_t in enumerate(trilhas) for r in repos_t}

    # Fluxos completos vs partidos
    fluxos_completos: dict[int, list] = defaultdict(list)
    fluxos_partidos: list[dict] = []
    for fluxo, repos_do_fluxo in fluxo_repos.items():
        trilhas_do_fluxo = {repo_trilha[r] for r in repos_do_fluxo if r in repo_trilha}
        if len(trilhas_do_fluxo) == 1:
            fluxos_completos[list(trilhas_do_fluxo)[0]].append(fluxo)
        elif len(trilhas_do_fluxo) > 1:
            n_repos = len(repos_do_fluxo)
            n_t = len(trilhas_do_fluxo)
            if n_repos <= 2 or (n_t == 2 and n_repos <= 3):
                gravidade = "Baixo"
            elif n_repos <= 5 and n_t <= 2:
                gravidade = "Médio"
            elif n_repos <= 10 and n_t <= 3:
                gravidade = "Alto"
            else:
                gravidade = "Crítico"
            fluxos_partidos.append({
                "fluxo": fluxo,
                "trilhas": sorted(t + 1 for t in trilhas_do_fluxo),
                "repositorios": sorted(repos_do_fluxo),
                "n_repositorios": n_repos,
                "n_trilhas_envolvidas": n_t,
                "gravidade": gravidade,
                "alerta": "Fluxo partido entre trilhas — coordenar entrega conjunta antes do go-live.",
            })

    _GRAVIDADE_ORDER = {"Crítico": 0, "Alto": 1, "Médio": 2, "Baixo": 3}
    fluxos_partidos.sort(key=lambda x: (_GRAVIDADE_ORDER.get(x["gravidade"], 9), x["fluxo"]))

    # Dependências cruzadas (BD e API)
    criticos = {"Banco de Dados", "API/Contrato"}
    cross: dict = defaultdict(list)
    for r in repos:
        for area in r["areas"] & criticos:
            cross[area].append(r["modulo"])
    dependencias = [
        {"area": area, "repositorios": mods}
        for area, mods in cross.items()
        if len(mods) > 1
    ]

    ABBREV = {
        "Banco de Dados": "BD", "Backend": "BE", "API/Contrato": "API",
        "Frontend": "FE", "Integrações": "INT", "Processamento/Batch": "BATCH",
        "Segurança/LGPD": "SEC", "Infraestrutura/CI": "INFRA",
        "Configuração": "CFG", "Testes/Qualidade": "TEST",
        "Documentação": "DOC", "Pessoa Jurídica/PJ": "PJ",
    }

    grupos = []
    for i, cluster in enumerate(clusters, 1):
        areas_union = frozenset().union(*(r["areas"] for r in cluster))
        cluster_fluxos = sorted({f for r in cluster for f in repo_fluxos.get(r["modulo"], frozenset())})
        grupos.append({
            "grupo": i,
            "perfil": " + ".join(ABBREV.get(a, a[:4]) for a in sorted(areas_union)),
            "total_alta": sum(r["alta"] for r in cluster),
            "total_impactos": sum(r["total"] for r in cluster),
            "fluxos": cluster_fluxos,
            "repositorios": [
                {"modulo": r["modulo"], "passo": r["passo"],
                 "alta": r["alta"], "total": r["total"], "dual": r["dual"],
                 "fluxos": sorted(repo_fluxos.get(r["modulo"], frozenset()))}
                for r in sorted(cluster, key=lambda x: -x["alta"])
            ],
        })

    # Grafo de dependências entre trilhas
    arestas: dict[tuple[int, int], list[str]] = defaultdict(list)
    for fp in fluxos_partidos:
        repos_por_trilha = defaultdict(int)
        for r in fp["repositorios"]:
            t_idx = repo_trilha.get(r)
            if t_idx is not None:
                repos_por_trilha[t_idx + 1] += 1
        if len(repos_por_trilha) >= 2:
            provedora = max(repos_por_trilha, key=lambda t: repos_por_trilha[t])
            for t in fp["trilhas"]:
                if t != provedora:
                    arestas[(provedora, t)].append(fp["fluxo"])

    for dep in dependencias:
        for repo in dep["repositorios"]:
            t_prov = repo_trilha.get(repo)
            if t_prov is None:
                continue
            for t_other in range(n_trilhas):
                if t_other != t_prov and trilhas[t_other]:
                    chave = (t_prov + 1, t_other + 1)
                    motivo = f"{dep['area']} em {repo}"
                    if motivo not in arestas[chave]:
                        arestas[chave].append(motivo)

    grafo_nos = [
        {"trilha": t + 1, "carga_alta": carga[t],
         "total_impactos": sum(r["total"] for r in trilhas[t])}
        for t in range(n_trilhas)
    ]
    grafo_arestas = [
        {"de": de, "para": para, "motivos": motivos,
         "descricao": f"Trilha {de} deve ser concluída antes da Trilha {para}"}
        for (de, para), motivos in sorted(arestas.items())
    ]

    delta = abs(carga[0] - carga[1]) if n_trilhas >= 2 else 0
    total_alta = sum(carga)

    return {
        "n_trilhas": n_trilhas,
        "strategy": strategy.name,
        "desequilibrio_pct": round(delta / total_alta * 100) if total_alta else 0,
        "grupos": grupos,
        "trilhas": [
            {
                "trilha": t + 1,
                "carga_alta": carga[t],
                "total_impactos": sum(r["total"] for r in trilhas[t]),
                "fluxos_completos": sorted(fluxos_completos.get(t, [])),
                "fluxos": sorted({f for r in trilhas[t] for f in repo_fluxos.get(r["modulo"], frozenset())}),
                "repositorios": [
                    {"modulo": r["modulo"], "passo": r["passo"],
                     "alta": r["alta"], "total": r["total"],
                     "perfil": " + ".join(ABBREV.get(a, a[:4]) for a in sorted(r["areas"])),
                     "fluxos": sorted(repo_fluxos.get(r["modulo"], frozenset()))}
                    for r in sorted(trilhas[t], key=lambda x: x["passo"])
                ],
            }
            for t in range(n_trilhas)
        ],
        "fluxos_partidos": fluxos_partidos,
        "dependencias_cruzadas": dependencias,
        "grafo_dependencias": {"nos": grafo_nos, "arestas": grafo_arestas},
    }
