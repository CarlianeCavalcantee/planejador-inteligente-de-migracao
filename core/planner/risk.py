"""
Risk Score, heatmap, gargalos, SPOFs e sugestões de movimentação.
Extraído de output.py.
"""
from collections import defaultdict

_DOMINIOS_CRITICOS: list[tuple[str, list[str]]] = [
    ("Auth/IAM",        ["auth", "iam", "identity", "login", "oauth", "sso", "keycloak", "autenticacao"]),
    ("PIX",             ["pix"]),
    ("Conta Digital",   ["conta", "account", "contadigital"]),
    ("Cartão",          ["cartao", "card", "cartoes"]),
    ("Crédito/CCB",     ["credito", "ccb", "emprestimo", "loan"]),
    ("Onboarding PJ",   ["onboarding", "aberturaconta", "pessoajuridica", "pj-onboard"]),
    ("Pagamentos",      ["pagamento", "payment", "boleto", "ted", "cobranca"]),
    ("Fiscal/SPED",     ["sped", "nfse", "fiscal", "reinf", "esocial"]),
    ("Integrações Core", ["gateway", "integration", "integracao", "broker", "middleware"]),
    ("Banco de Dados Core", ["schema", "migration", "flyway", "liquibase", "db-core"]),
]


def build_gargalos(matriz: list[dict], ordem_migracao: list[dict]) -> list[dict]:
    repo_fluxos: dict[str, set] = defaultdict(set)
    for m in matriz:
        f = m.get("fluxo")
        if f:
            repo_fluxos[m["repositorio"]].add(f)

    total_fluxos = len({m.get("fluxo") for m in matriz if m.get("fluxo")})
    if total_fluxos == 0:
        return []

    passo_map = {s["modulo"]: s["passo"] for s in ordem_migracao}
    alta_map  = {s["modulo"]: s["impactos_alta_complexidade"] for s in ordem_migracao}

    gargalos = []
    for repo, fluxos in repo_fluxos.items():
        n = len(fluxos)
        pct = n / total_fluxos
        if n < 3 and pct < 0.30:
            continue
        if pct >= 0.60 or n >= 10:
            nivel = "Crítico"
        elif pct >= 0.40 or n >= 6:
            nivel = "Alto"
        else:
            nivel = "Médio"
        gargalos.append({
            "repositorio": repo,
            "n_fluxos": n,
            "pct_fluxos": round(pct * 100),
            "fluxos": sorted(fluxos),
            "nivel": nivel,
            "passo_migracao": passo_map.get(repo),
            "impactos_alta": alta_map.get(repo, 0),
            "alerta": f"Atraso neste repo impacta {n} fluxo(s) ({round(pct*100)}% do total).",
        })

    gargalos.sort(key=lambda x: (-x["n_fluxos"], -x["impactos_alta"]))
    return gargalos


def build_spof(matriz: list[dict], ordem_migracao: list[dict]) -> list[dict]:
    passo_map = {s["modulo"]: s["passo"] for s in ordem_migracao}
    alta_map  = {s["modulo"]: s["impactos_alta_complexidade"] for s in ordem_migracao}
    repos_com_impacto = {m["repositorio"] for m in matriz}

    resultado: list[dict] = []
    for dominio, keywords in _DOMINIOS_CRITICOS:
        matches = [
            r for r in repos_com_impacto
            if any(kw in r.lower().replace("-", "").replace("_", "") for kw in keywords)
        ]
        if len(matches) == 1:
            repo = matches[0]
            resultado.append({
                "repositorio": repo,
                "dominio": dominio,
                "motivo": f"Único repo com impacto no domínio '{dominio}'. Sem substituto se atrasar.",
                "passo_migracao": passo_map.get(repo),
                "impactos_alta": alta_map.get(repo, 0),
                "alerta": f"SPOF: atraso em '{repo}' bloqueia todo o domínio {dominio}.",
            })

    resultado.sort(key=lambda x: (-x["impactos_alta"], x["dominio"]))
    return resultado


def build_heatmap_risco(
    ordem_migracao: list[dict],
    gargalos: list[dict],
    spof: list[dict],
    trilhas: dict,
) -> list[dict]:
    if not ordem_migracao:
        return []
    gargalo_por_repo = {g["repositorio"]: g for g in gargalos}
    spof_repos       = {s["repositorio"] for s in spof}
    _NIVEL_PESO      = {"Médio": 1, "Alto": 2, "Crítico": 3}
    partidos_repos: set[str] = set()
    for fp in (trilhas or {}).get("fluxos_partidos", []):
        partidos_repos.update(fp.get("repositorios", []))

    sprints: list[dict] = []
    for s in ordem_migracao:
        repo  = s["modulo"]
        alta  = s["impactos_alta_complexidade"]
        score = alta * 2
        fatores: list[str] = []
        if repo in spof_repos:
            score += 5
            fatores.append("SPOF")
        g = gargalo_por_repo.get(repo)
        if g:
            score += 3 * _NIVEL_PESO.get(g["nivel"], 1)
            fatores.append(f"Gargalo {g['nivel']}")
        if repo in partidos_repos:
            score += 4
            fatores.append("Fluxo partido")
        sprints.append({"passo": s["passo"], "modulo": repo,
                        "score": score, "impactos_alta": alta, "fatores": fatores})

    max_score = max(s["score"] for s in sprints) or 1
    for s in sprints:
        s["score_normalizado"] = round(s["score"] / max_score * 100)
        raw = s["score_normalizado"]
        s["nivel_risco"] = "Crítico" if raw >= 75 else "Alto" if raw >= 50 else "Médio" if raw >= 25 else "Baixo"
    return sprints


def build_risk_score(
    ordem_migracao: list[dict],
    gargalos: list[dict],
    spof: list[dict],
    trilhas: dict,
    matriz: list[dict],
) -> list[dict]:
    _NIVEL_PESO = {"Crítico": 8, "Alto": 5, "Médio": 3}
    gargalo_map = {g["repositorio"]: g for g in gargalos}
    spof_repos  = {s["repositorio"] for s in spof}
    partidos_map: dict[str, int] = {}
    for fp in (trilhas or {}).get("fluxos_partidos", []):
        for r in fp.get("repositorios", []):
            partidos_map[r] = partidos_map.get(r, 0) + 1

    repo_imp: dict[str, list] = defaultdict(list)
    for m in matriz:
        repo_imp[m["repositorio"]].append(m)

    scores = []
    for s in ordem_migracao:
        repo  = s["modulo"]
        itens = repo_imp.get(repo, [])
        alta  = s["impactos_alta_complexidade"]
        media = sum(1 for m in itens if m["complexidade"] == "Média")
        dual  = s["requerem_compatibilidade_dual"]
        deps  = len(s.get("depende_de", []))

        raw = alta * 3 + media * 1
        fatores: list[dict] = [
            {"fator": "Impactos Alta",  "pontos": alta * 3,  "detalhe": f"{alta} × 3"},
            {"fator": "Impactos Média", "pontos": media * 1, "detalhe": f"{media} × 1"},
        ]

        if repo in spof_repos:
            raw += 10
            fatores.append({"fator": "SPOF", "pontos": 10, "detalhe": "Único repo no domínio"})

        g = gargalo_map.get(repo)
        if g:
            pts = _NIVEL_PESO.get(g["nivel"], 3)
            raw += pts
            fatores.append({"fator": f"Gargalo {g['nivel']}", "pontos": pts,
                            "detalhe": f"{g['n_fluxos']} fluxos ({g['pct_fluxos']}%)"})

        n_partidos = partidos_map.get(repo, 0)
        if n_partidos:
            pts = n_partidos * 6
            raw += pts
            fatores.append({"fator": "Fluxos partidos", "pontos": pts,
                            "detalhe": f"{n_partidos} fluxo(s) partido(s)"})

        if dual:
            raw += 4
            fatores.append({"fator": "Compatibilidade dual", "pontos": 4,
                            "detalhe": f"{dual} impacto(s) dual"})

        if deps:
            raw += 2
            fatores.append({"fator": "Dependências", "pontos": 2,
                            "detalhe": f"{deps} dependência(s)"})

        scores.append({
            "passo": s["passo"],
            "modulo": repo,
            "score_raw": raw,
            "fatores": [f for f in fatores if f["pontos"] > 0],
        })

    max_raw = max((s["score_raw"] for s in scores), default=1) or 1
    for s in scores:
        s["score"] = round(s["score_raw"] / max_raw * 100)
        raw = s["score"]
        s["nivel"] = "Crítico" if raw >= 75 else "Alto" if raw >= 50 else "Médio" if raw >= 25 else "Baixo"
    return scores


def build_sugestoes_movimentacao(trilhas: dict, ordem_migracao: list[dict]) -> list[dict]:
    if not trilhas:
        return []
    partidos = trilhas.get("fluxos_partidos", [])
    if not partidos:
        return []

    repo_trilha: dict[str, int] = {}
    carga_trilha: dict[int, int] = {}
    for t in trilhas.get("trilhas", []):
        tid = t["trilha"]
        carga_trilha[tid] = t["carga_alta"]
        for r in t["repositorios"]:
            repo_trilha[r["modulo"]] = tid

    alta_map = {s["modulo"]: s["impactos_alta_complexidade"] for s in ordem_migracao}

    sugestoes = []
    for fp in partidos:
        if fp.get("gravidade") not in ("Alto", "Crítico"):
            continue
        repos_fluxo = fp["repositorios"]
        from collections import Counter
        contagem = Counter(repo_trilha.get(r) for r in repos_fluxo if repo_trilha.get(r))
        if len(contagem) < 2:
            continue
        trilha_destino = contagem.most_common(1)[0][0]
        candidatos = [r for r in repos_fluxo if repo_trilha.get(r) and repo_trilha[r] != trilha_destino]
        if not candidatos:
            continue
        repo_mover = min(candidatos, key=lambda r: alta_map.get(r, 0))
        trilha_origem = repo_trilha[repo_mover]
        delta_carga = alta_map.get(repo_mover, 0)
        sugestoes.append({
            "fluxo": fp["fluxo"],
            "gravidade": fp["gravidade"],
            "repo": repo_mover,
            "de_trilha": trilha_origem,
            "para_trilha": trilha_destino,
            "impactos_alta_repo": delta_carga,
            "nova_carga_trilha_origem": carga_trilha.get(trilha_origem, 0) - delta_carga,
            "nova_carga_trilha_destino": carga_trilha.get(trilha_destino, 0) + delta_carga,
            "justificativa": (
                f"Mover '{repo_mover}' da Trilha {trilha_origem} para a Trilha {trilha_destino} "
                f"consolida o fluxo '{fp['fluxo']}' em uma única trilha, "
                f"eliminando necessidade de sincronização entre equipes."
            ),
        })
    return sugestoes
