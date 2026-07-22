"""
Metrics Engine: camada desacoplada de métricas reutilizáveis.
Qualquer dashboard ou exportador usa este módulo diretamente.
"""
import math
from collections import defaultdict

# Esforço estimado em dias por impacto, por área e complexidade
_ESFORCO_DIAS: dict[str, dict[str, float]] = {
    "Banco de Dados":      {"Alta": 3.0, "Média": 1.5, "Baixa": 0.5},
    "API/Contrato":        {"Alta": 2.5, "Média": 1.0, "Baixa": 0.5},
    "Backend":             {"Alta": 2.0, "Média": 1.0, "Baixa": 0.5},
    "Frontend":            {"Alta": 1.5, "Média": 0.5, "Baixa": 0.25},
    "Integrações":         {"Alta": 3.0, "Média": 1.5, "Baixa": 0.5},
    "Processamento/Batch": {"Alta": 2.5, "Média": 1.0, "Baixa": 0.5},
    "Segurança/LGPD":      {"Alta": 2.0, "Média": 1.0, "Baixa": 0.5},
    "Infraestrutura/CI":   {"Alta": 1.5, "Média": 0.5, "Baixa": 0.25},
    "Configuração":        {"Alta": 1.0, "Média": 0.5, "Baixa": 0.25},
    "Testes/Qualidade":    {"Alta": 1.5, "Média": 0.5, "Baixa": 0.25},
    "Documentação":        {"Alta": 0.5, "Média": 0.25, "Baixa": 0.25},
    "Pessoa Jurídica/PJ":  {"Alta": 2.0, "Média": 1.0, "Baixa": 0.5},
}
_OVERHEAD_MODULO_DIAS = 2.0
_FATOR_DUAL = 1.3
_FIB = [1, 2, 3, 5, 8, 13, 21, 34]


def effort(ordem_migracao: list[dict], matriz: list[dict]) -> list[dict]:
    """Esforço em dias e story points por módulo."""
    repo_impactos: dict[str, list] = defaultdict(list)
    for m in matriz:
        repo_impactos[m["repositorio"]].append(m)

    resultado = []
    for s in ordem_migracao:
        repo   = s["modulo"]
        itens  = repo_impactos.get(repo, [])
        dias_base = 0.0
        por_area: dict[str, dict] = {}

        for m in itens:
            area  = m["area"]
            compl = m["complexidade"]
            d = _ESFORCO_DIAS.get(area, {"Alta": 2.0, "Média": 1.0, "Baixa": 0.5}).get(compl, 1.0)
            if m.get("requer_compatibilidade_dual"):
                d *= _FATOR_DUAL
            dias_base += d
            if area not in por_area:
                por_area[area] = {"dias": 0.0, "impactos": 0}
            por_area[area]["dias"] += d
            por_area[area]["impactos"] += 1

        dias_total = round(dias_base + _OVERHEAD_MODULO_DIAS, 1)
        sp_raw = math.ceil(dias_total / 0.5)
        story_points = next((f for f in _FIB if f >= sp_raw), _FIB[-1])

        resultado.append({
            "passo": s["passo"],
            "modulo": repo,
            "dias_estimados": dias_total,
            "story_points": story_points,
            "overhead_dias": _OVERHEAD_MODULO_DIAS,
            "requer_dual": s["requerem_compatibilidade_dual"] > 0,
            "esforco_por_area": [
                {"area": a, "dias": round(v["dias"], 1), "impactos": v["impactos"]}
                for a, v in sorted(por_area.items(), key=lambda x: -x[1]["dias"])
            ],
        })
    return resultado


def coordination_cost(trilhas: dict) -> dict:
    """
    Custo de coordenação: quantos fluxos exigem sincronização entre equipes.
    Retorna score 0–100 (menor = mais barato coordenar).
    """
    partidos = trilhas.get("fluxos_partidos", [])
    total_fluxos = len(
        {f for t in trilhas.get("trilhas", []) for f in t.get("fluxos", [])}
    ) or 1
    _PESO = {"Crítico": 4, "Alto": 3, "Médio": 2, "Baixo": 1}
    custo_raw = sum(_PESO.get(fp.get("gravidade", "Baixo"), 1) for fp in partidos)
    max_custo = total_fluxos * 4
    score = round(custo_raw / max_custo * 100) if max_custo else 0
    return {
        "score": score,
        "nivel": "Crítico" if score >= 75 else "Alto" if score >= 50 else "Médio" if score >= 25 else "Baixo",
        "fluxos_partidos": len(partidos),
        "total_fluxos": total_fluxos,
        "detalhes": [
            {"fluxo": fp["fluxo"], "gravidade": fp["gravidade"],
             "trilhas": fp["trilhas"], "n_repos": fp["n_repositorios"]}
            for fp in partidos
        ],
    }


def critical_path(ordem_migracao: list[dict], esforco: list[dict]) -> dict:
    """
    Caminho crítico: sequência de módulos com maior soma de dias estimados
    considerando dependências (depende_de).
    Retorna o caminho e o total de dias no caminho crítico.
    """
    dias_map = {e["modulo"]: e["dias_estimados"] for e in esforco}
    deps_map = {s["modulo"]: s.get("depende_de", []) for s in ordem_migracao}
    repos = [s["modulo"] for s in ordem_migracao]

    # DP: dist[r] = maior soma de dias até r (incluindo r)
    dist: dict[str, float] = {}
    prev: dict[str, str | None] = {}

    for r in repos:
        d_r = dias_map.get(r, 0.0)
        predecessores = [p for p in deps_map.get(r, []) if p in dist]
        if predecessores:
            melhor_pred = max(predecessores, key=lambda p: dist[p])
            dist[r] = dist[melhor_pred] + d_r
            prev[r] = melhor_pred
        else:
            dist[r] = d_r
            prev[r] = None

    # Nó final = maior dist
    if not dist:
        return {"caminho": [], "dias_totais": 0.0}

    fim = max(dist, key=lambda r: dist[r])
    caminho = []
    cur = fim
    while cur is not None:
        caminho.append(cur)
        cur = prev.get(cur)
    caminho.reverse()

    return {
        "caminho": caminho,
        "dias_totais": round(dist[fim], 1),
        "n_modulos": len(caminho),
    }


def bottleneck_index(gargalos: list[dict], spof: list[dict], ordem_migracao: list[dict]) -> list[dict]:
    """
    Índice de gargalo por módulo: combina gargalo arquitetural + SPOF + posição na ordem.
    Score 0–100 (maior = mais crítico para o cronograma).
    """
    _NIVEL_PESO = {"Crítico": 3, "Alto": 2, "Médio": 1}
    total_passos = len(ordem_migracao) or 1
    gargalo_map = {g["repositorio"]: g for g in gargalos}
    spof_repos  = {s["repositorio"] for s in spof}

    resultado = []
    for s in ordem_migracao:
        repo  = s["modulo"]
        passo = s["passo"]
        raw   = 0

        g = gargalo_map.get(repo)
        if g:
            raw += _NIVEL_PESO.get(g["nivel"], 1) * 30
        if repo in spof_repos:
            raw += 40
        # Repos no início da ordem têm mais impacto (bloqueiam os seguintes)
        raw += round((1 - passo / total_passos) * 30)

        resultado.append({
            "passo": passo,
            "modulo": repo,
            "bottleneck_index": min(raw, 100),
            "nivel": "Crítico" if raw >= 75 else "Alto" if raw >= 50 else "Médio" if raw >= 25 else "Baixo",
            "fatores": {
                "gargalo": g["nivel"] if g else None,
                "spof": repo in spof_repos,
                "posicao_ordem": passo,
            },
        })

    resultado.sort(key=lambda x: -x["bottleneck_index"])
    return resultado


def migration_readiness(
    ordem_migracao: list[dict],
    trilhas: dict,
    gargalos: list[dict],
    spof: list[dict],
    matriz: list[dict],
) -> dict:
    """
    Migration Readiness Score: indicador executivo 0–100.
    Combina 6 dimensões com pesos iguais.

    Dimensões:
    1. Ordem válida (sem ciclos detectados)
    2. Dependências consistentes (todos os depende_de estão na ordem)
    3. Fluxos partidos (menos = melhor)
    4. Carga equilibrada (desequilíbrio baixo = melhor)
    5. Poucos SPOFs
    6. Poucos gargalos críticos
    """
    checks = []

    # 1. Ordem válida
    modulos = {s["modulo"] for s in ordem_migracao}
    ciclos = any(
        dep not in modulos
        for s in ordem_migracao
        for dep in s.get("depende_de", [])
    )
    checks.append({
        "dimensao": "Ordem válida",
        "ok": not ciclos,
        "detalhe": "Todos os módulos têm predecessores na ordem de migração." if not ciclos
                   else "Existem dependências fora do escopo do scan.",
        "peso": 1,
    })

    # 2. Dependências consistentes
    deps_ok = all(
        dep in modulos
        for s in ordem_migracao
        for dep in s.get("depende_de", [])
    )
    checks.append({
        "dimensao": "Dependências consistentes",
        "ok": deps_ok,
        "detalhe": "Todas as dependências estão no escopo." if deps_ok
                   else "Algumas dependências estão fora do escopo do scan.",
        "peso": 1,
    })

    # 3. Fluxos partidos
    n_partidos = len(trilhas.get("fluxos_partidos", []))
    total_fluxos = len({m.get("fluxo") for m in matriz if m.get("fluxo")}) or 1
    pct_partidos = n_partidos / total_fluxos
    partidos_ok = pct_partidos <= 0.30
    checks.append({
        "dimensao": "Fluxos partidos",
        "ok": partidos_ok,
        "detalhe": f"{n_partidos}/{total_fluxos} fluxos partidos ({round(pct_partidos*100)}%).",
        "peso": 1,
    })

    # 4. Carga equilibrada
    desequilibrio = trilhas.get("desequilibrio_pct", 0)
    equilibrio_ok = desequilibrio <= 25
    checks.append({
        "dimensao": "Carga equilibrada",
        "ok": equilibrio_ok,
        "detalhe": f"Desequilíbrio de carga: {desequilibrio}%.",
        "peso": 1,
    })

    # 5. Poucos SPOFs
    n_spof = len(spof)
    spof_ok = n_spof <= 2
    checks.append({
        "dimensao": "Poucos SPOFs",
        "ok": spof_ok,
        "detalhe": f"{n_spof} SPOF(s) detectado(s).",
        "peso": 1,
    })

    # 6. Poucos gargalos críticos
    n_criticos = sum(1 for g in gargalos if g["nivel"] == "Crítico")
    gargalos_ok = n_criticos == 0
    checks.append({
        "dimensao": "Sem gargalos críticos",
        "ok": gargalos_ok,
        "detalhe": f"{n_criticos} gargalo(s) crítico(s) detectado(s).",
        "peso": 1,
    })

    total_peso = sum(c["peso"] for c in checks)
    score_raw  = sum(c["peso"] for c in checks if c["ok"])
    score      = round(score_raw / total_peso * 100)

    nivel = "Pronto" if score >= 80 else "Atenção" if score >= 60 else "Risco" if score >= 40 else "Crítico"

    return {
        "score": score,
        "nivel": nivel,
        "checks": [
            {**c, "status": "✔" if c["ok"] else "⚠"}
            for c in checks
        ],
        "resumo": f"Migration Readiness: {score}% ({nivel}). "
                  f"{score_raw}/{total_peso} dimensões aprovadas.",
    }


def build_metrics(
    ordem_migracao: list[dict],
    trilhas: dict,
    gargalos: list[dict],
    spof: list[dict],
    matriz: list[dict],
) -> dict:
    """Ponto de entrada único: retorna todas as métricas calculadas."""
    esforco_data = effort(ordem_migracao, matriz)
    return {
        "esforco":            esforco_data,
        "coordination_cost":  coordination_cost(trilhas),
        "critical_path":      critical_path(ordem_migracao, esforco_data),
        "bottleneck_index":   bottleneck_index(gargalos, spof, ordem_migracao),
        "migration_readiness": migration_readiness(ordem_migracao, trilhas, gargalos, spof, matriz),
    }
