"""
Simulador de estratégias de trilhas.
Compara N=2..7 trilhas e múltiplas estratégias, calcula score composto
e recomenda a melhor configuração.
"""
from .trails import build_trails
from .strategies import STRATEGIES

# Pesos do score composto (0–100):
# - Menos fluxos partidos = melhor coordenação
# - Menos desequilíbrio = carga mais justa entre equipes
# - Menos dias = entrega mais rápida
_W_PARTIDOS     = 0.45
_W_EQUILIBRIO   = 0.30
_W_DIAS         = 0.25

# Esforço base por impacto Alta (dias) — usado para estimar duração da trilha mais longa
_DIAS_POR_ALTA  = 2.5
_OVERHEAD_REPO  = 2.0


def _estimar_dias(trilhas_data: dict) -> float:
    """Duração estimada = trilha mais longa (caminho crítico)."""
    max_dias = 0.0
    for t in trilhas_data.get("trilhas", []):
        dias = t["carga_alta"] * _DIAS_POR_ALTA + len(t["repositorios"]) * _OVERHEAD_REPO
        if dias > max_dias:
            max_dias = dias
    return round(max_dias, 1)


def _score(n_partidos: int, desequilibrio_pct: int, dias: float,
           max_partidos: int, max_desequilibrio: int, max_dias: float) -> int:
    """Score 0–100: maior = melhor."""
    def norm(v, mx): return v / mx if mx else 0.0
    penalty = (
        _W_PARTIDOS   * norm(n_partidos, max_partidos) +
        _W_EQUILIBRIO * norm(desequilibrio_pct, max_desequilibrio) +
        _W_DIAS       * norm(dias, max_dias)
    )
    return round((1 - penalty) * 100)


def simulate_trails(
    ordem_migracao: list[dict],
    cfg: dict,
    matriz: list[dict],
    n_range: range = range(2, 8),
    strategies: list[str] | None = None,
) -> dict:
    """
    Simula todas as combinações de (n_trilhas × estratégia) e retorna:
    - tabela comparativa
    - recomendação (melhor score)
    - melhor por estratégia
    """
    if strategies is None:
        strategies = list(STRATEGIES.keys())

    resultados = []
    for n in n_range:
        for strat_name in strategies:
            strategy = STRATEGIES[strat_name]()
            cfg_sim = {**cfg, "trilhas": n, "strategy": strat_name}
            try:
                t = build_trails(ordem_migracao, cfg_sim, matriz, strategy=strategy)
            except Exception:
                continue

            n_partidos    = len(t.get("fluxos_partidos", []))
            desequilibrio = t.get("desequilibrio_pct", 0)
            dias          = _estimar_dias(t)

            resultados.append({
                "n_trilhas":        n,
                "strategy":         strat_name,
                "strategy_label":   strategy.description,
                "fluxos_partidos":  n_partidos,
                "desequilibrio_pct": desequilibrio,
                "dias_estimados":   dias,
                "score":            0,   # calculado abaixo
                "recomendada":      False,
            })

    if not resultados:
        return {"resultados": [], "recomendacao": None, "melhor_por_estrategia": {}}

    max_partidos     = max(r["fluxos_partidos"]  for r in resultados) or 1
    max_desequilibrio = max(r["desequilibrio_pct"] for r in resultados) or 1
    max_dias         = max(r["dias_estimados"]    for r in resultados) or 1

    for r in resultados:
        r["score"] = _score(
            r["fluxos_partidos"], r["desequilibrio_pct"], r["dias_estimados"],
            max_partidos, max_desequilibrio, max_dias,
        )

    # Recomendação global
    melhor = max(resultados, key=lambda r: r["score"])
    melhor["recomendada"] = True

    # Melhor por estratégia (menor n_trilhas com score >= 90% do melhor da estratégia)
    melhor_por_estrategia: dict[str, dict] = {}
    for strat_name in strategies:
        candidatos = [r for r in resultados if r["strategy"] == strat_name]
        if candidatos:
            melhor_strat = max(candidatos, key=lambda r: r["score"])
            melhor_por_estrategia[strat_name] = melhor_strat

    # Tabela ordenada por score desc
    resultados.sort(key=lambda r: (-r["score"], r["n_trilhas"]))

    return {
        "resultados": resultados,
        "recomendacao": {
            "n_trilhas":       melhor["n_trilhas"],
            "strategy":        melhor["strategy"],
            "score":           melhor["score"],
            "fluxos_partidos": melhor["fluxos_partidos"],
            "desequilibrio_pct": melhor["desequilibrio_pct"],
            "dias_estimados":  melhor["dias_estimados"],
            "justificativa": (
                f"{melhor['n_trilhas']} trilhas com estratégia '{melhor['strategy']}' "
                f"obteve o melhor score ({melhor['score']}/100): "
                f"{melhor['fluxos_partidos']} fluxos partidos, "
                f"{melhor['desequilibrio_pct']}% desequilíbrio, "
                f"~{melhor['dias_estimados']} dias estimados."
            ),
        },
        "melhor_por_estrategia": melhor_por_estrategia,
    }
