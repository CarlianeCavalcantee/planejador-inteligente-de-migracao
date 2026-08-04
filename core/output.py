"""
Consolidação de impactos e geração de relatórios JSON + Markdown.
Planejamento (ordem, trilhas, métricas, simulação) delegado a core.planner.
"""

from datetime import datetime, timezone, timedelta

from core.config import (
    DUAL_COMPAT_RES,
    get_area_rationale, get_rollback_base, get_rollback_area,
    get_riscos_area, get_criterios_area, get_parceiros_conhecidos,
    get_pontos_cegos, get_tela_keywords, get_secoes_extras, get_titulo,
)
from core.flow import build_flow_analysis
from core.planner import build_plan


def _build_parceiros_externos(matriz: list[dict], cfg: dict) -> list[dict]:
    """Detecta parceiros externos mencionados nos impactos e gera alerta de alinhamento."""
    parceiros_conhecidos = get_parceiros_conhecidos(cfg)
    if not parceiros_conhecidos:
        return []
    encontrados = {}
    for m in matriz:
        trecho = (m["evidencia"]["trecho_codigo"] + m["componente"]).lower()
        for parceiro, descricao in parceiros_conhecidos.items():
            if parceiro in trecho and parceiro not in encontrados:
                encontrados[parceiro] = {
                    "parceiro": parceiro,
                    "descricao": descricao,
                    "repositorios": set(),
                    "status_alinhamento": "pendente",
                }
            if parceiro in trecho and parceiro in encontrados:
                encontrados[parceiro]["repositorios"].add(m["repositorio"])
    result = []
    for p in sorted(encontrados.values(), key=lambda x: x["parceiro"]):
        result.append({**p, "repositorios": sorted(p["repositorios"])})
    return result


def _build_arquivos_criticos(matriz: list[dict]) -> list[dict]:
    """
    Top arquivos por chamadores_estimados.
    Esses são os pontos de entrada da migração — mudar um deles impacta
    dezenas ou centenas de outros componentes.
    """
    # Agrega por (repo, arquivo): pega o maior chamadores e lista todas as linhas
    agg: dict[tuple, dict] = {}
    for m in matriz:
        key = (m["repositorio"], m["componente"])
        callers = m["chamadores_estimados"]
        if key not in agg or callers > agg[key]["chamadores_estimados"]:
            agg[key] = {
                "repositorio": m["repositorio"],
                "arquivo": m["componente"],
                "area": m["area"],
                "chamadores_estimados": callers,
                "impactos_no_arquivo": 0,
                "linhas_afetadas": [],
                "requer_compatibilidade_dual": False,
            }
        agg[key]["impactos_no_arquivo"] += 1
        agg[key]["linhas_afetadas"].append(m["evidencia"]["linha"])
        if m["requer_compatibilidade_dual"]:
            agg[key]["requer_compatibilidade_dual"] = True

    # Ordena por chamadores desc, pega top 15
    ranked = sorted(agg.values(), key=lambda x: x["chamadores_estimados"], reverse=True)
    return ranked[:15]


def _build_trilhas(ordem_migracao: list[dict], cfg: dict, matriz: list[dict] | None = None) -> dict:
    """Delegado ao planner."""
    from core.planner.trails import build_trails
    return build_trails(ordem_migracao, cfg, matriz)


def _build_ordem_migracao(matriz: list[dict], cfg: dict) -> list[dict]:
    """Delegado ao planner."""
    from core.planner.planner import build_ordem_migracao
    return build_ordem_migracao(matriz, cfg)


def _build_gargalos(matriz, ordem_migracao):
    from core.planner.risk import build_gargalos
    return build_gargalos(matriz, ordem_migracao)


def _build_spof(matriz, ordem_migracao):
    from core.planner.risk import build_spof
    return build_spof(matriz, ordem_migracao)


def _build_heatmap_risco(ordem_migracao, gargalos, spof, trilhas):
    from core.planner.risk import build_heatmap_risco
    return build_heatmap_risco(ordem_migracao, gargalos, spof, trilhas)


def _build_esforco(ordem_migracao, matriz):
    from core.planner.metrics import effort
    return effort(ordem_migracao, matriz)


def _build_risk_score(ordem_migracao, gargalos, spof, trilhas, matriz):
    from core.planner.risk import build_risk_score
    return build_risk_score(ordem_migracao, gargalos, spof, trilhas, matriz)


def _build_sugestoes_movimentacao(trilhas, ordem_migracao):
    from core.planner.risk import build_sugestoes_movimentacao
    return build_sugestoes_movimentacao(trilhas, ordem_migracao)


def _build_criterios_aceite(matriz: list[dict], ordem_migracao: list[dict], cfg: dict) -> list[dict]:
    criterios_area = get_criterios_area(cfg)
    criterios_encerramento = cfg.get("criterios_encerramento") or []
    resultado = []
    for s in ordem_migracao:
        repo = s["modulo"]
        areas_do_repo = [a["area"] for a in s["areas"]]
        criterios_por_area = [
            {"area": area, "criterios": criterios_area.get(area, [])}
            for area in areas_do_repo
            if criterios_area.get(area)
        ]
        resultado.append({
            "passo": s["passo"],
            "modulo": repo,
            "criterios_por_area": criterios_por_area,
            "criterios_encerramento": criterios_encerramento,
        })
    return resultado


def build_diff(scan_anterior: dict, scan_atual: dict) -> dict:
    def _idx(scan: dict) -> dict[str, dict]:
        return {
            f"{m['repositorio']}:{m['evidencia']['arquivo']}:{m['evidencia']['linha']}": m
            for m in scan.get("matriz_impacto", [])
        }
    ant = _idx(scan_anterior)
    atu = _idx(scan_atual)
    todas_chaves = set(ant) | set(atu)
    novos, resolvidos, alterados = [], [], []
    for chave in sorted(todas_chaves):
        em_ant, em_atu = chave in ant, chave in atu
        if em_atu and not em_ant:
            novos.append({**atu[chave], "_diff": "novo"})
        elif em_ant and not em_atu:
            resolvidos.append({**ant[chave], "_diff": "resolvido"})
        else:
            m_ant, m_atu = ant[chave], atu[chave]
            if m_ant["complexidade"] != m_atu["complexidade"] or m_ant["area"] != m_atu["area"]:
                alterados.append({**m_atu, "_diff": "alterado",
                    "_anterior": {"complexidade": m_ant["complexidade"], "area": m_ant["area"]}})
    return {
        "scan_id_anterior": scan_anterior.get("scan_id", "anterior"),
        "scan_id_atual": scan_atual.get("scan_id", "atual"),
        "data_anterior": scan_anterior.get("data_execucao", ""),
        "data_atual": scan_atual.get("data_execucao", ""),
        "resumo": {
            "novos": len(novos), "resolvidos": len(resolvidos), "alterados": len(alterados),
            "total_anterior": len(ant), "total_atual": len(atu), "delta": len(atu) - len(ant),
        },
        "novos": novos, "resolvidos": resolvidos, "alterados": alterados,
    }


def _build_oportunidades_refatoracao(matriz: list[dict], ordem_migracao: list[dict]) -> list[dict]:
    from collections import defaultdict
    oportunidades: list[dict] = []
    regra_repos: dict[str, set] = defaultdict(set)
    for m in matriz:
        obs = m.get("observacoes", "")
        if "Regra:" in obs:
            regra_id = obs.split("Regra:")[1].split("|")[0].strip()
            regra_repos[regra_id].add(m["repositorio"])
    for regra, repos in regra_repos.items():
        if len(repos) >= 3:
            oportunidades.append({
                "tipo": "Utilitario compartilhado", "regra": regra,
                "repositorios": sorted(repos), "n_repos": len(repos),
                "descricao": f"Regra {regra} detectada em {len(repos)} repositorios.",
                "acao": "Criar lib compartilhada com utilitario CNPJ.",
            })
    arquivo_impactos: dict[tuple, list] = defaultdict(list)
    for m in matriz:
        arquivo_impactos[(m["repositorio"], m["componente"])].append(m)
    for (repo, arquivo), itens in arquivo_impactos.items():
        if len(itens) >= 4:
            areas = sorted({m["area"] for m in itens})
            oportunidades.append({
                "tipo": "God Object / Alta coesao", "regra": "-",
                "repositorios": [repo], "n_repos": 1,
                "descricao": f"{arquivo.split('/')[-1]} em {repo} tem {len(itens)} impactos.",
                "acao": f"Dividir {arquivo.split('/')[-1]} em classes menores (SRP).",
            })
    fe_repos = {m["repositorio"] for m in matriz if m["area"] == "Frontend"}
    if len(fe_repos) >= 2:
        oportunidades.append({
            "tipo": "Componente de Input compartilhado", "regra": "FE-001",
            "repositorios": sorted(fe_repos), "n_repos": len(fe_repos),
            "descricao": f"Mascaras de CNPJ no Frontend em {len(fe_repos)} repos.",
            "acao": "Publicar componente CnpjInput no design system.",
        })
    oportunidades.sort(key=lambda x: (-x["n_repos"], x["tipo"]))
    return oportunidades


def _build_checklist_rollback(matriz: list[dict], cfg: dict) -> dict:
    rollback_base = get_rollback_base(cfg)
    rollback_area = get_rollback_area(cfg)
    result = {}
    for area in sorted({m["area"] for m in matriz}):
        result[area] = rollback_base + rollback_area.get(area, [])
    return result


def _build_impacto_dados(matriz: list[dict], cfg: dict) -> dict:
    sql_queries = cfg.get("sql_queries") or {}
    areas = {m["area"] for m in matriz}
    return {
        area: {"descricao": "Queries sugeridas.", "queries": queries}
        for area, queries in sql_queries.items() if area in areas
    }


def _build_riscos(matriz: list[dict], cfg: dict) -> list[dict]:
    riscos_area = get_riscos_area(cfg)
    areas = {m["area"] for m in matriz}
    return [v for k, v in riscos_area.items() if k in areas]


def _build_pendencias(matriz: list[dict]) -> list[dict]:
    pendencias = []
    idx = 1
    def add(desc, resp, prazo="A definir"):
        nonlocal idx
        pendencias.append({"id": f"PND-{idx:03d}", "descricao": desc, "responsavel": resp, "prazo_estimado": prazo})
        idx += 1
    repos_lgpd = sorted({m["repositorio"] for m in matriz if m["area"] == "Seguranca/LGPD"})
    if repos_lgpd:
        add(f"CNPJs reais hardcoded (LGPD). Repos: {', '.join(repos_lgpd)}", "Time de Seguranca / DPO", "Imediato")
    alta = [m for m in matriz if m["complexidade"] == "Alta"]
    if alta:
        add(f"{len(alta)} componente(s) de alta complexidade.", "Time de Engenharia / Backend")
    for area, resp in [
        ("Configuracao", "Time de Engenharia / DevOps"),
        ("Infraestrutura/CI", "Time de DevOps"),
        ("Integracoes", "Time de Integracoes / Parcerias"),
        ("Processamento/Batch", "Time de Engenharia / Fiscal"),
        ("Documentacao", "Time de Engenharia / Tech Writer"),
    ]:
        repos = sorted({m["repositorio"] for m in matriz if m["area"] == area})
        if repos:
            add(f"[{area}] Revisar impactos em: {', '.join(repos)}", resp)
    return pendencias


def _load_status_anteriores(output_file: str) -> dict:
    import os, json
    if not os.path.exists(output_file):
        return {}
    try:
        d = json.load(open(output_file, encoding="utf-8"))
        return {
            f"{m['repositorio']}:{m['evidencia']['arquivo']}:{m['evidencia']['linha']}": {
                "status": m.get("status", "pendente"),
                "responsavel": m.get("responsavel"),
                "observacao": m.get("observacao"),
            }
            for m in d.get("matriz_impacto", [])
        }
    except Exception:
        return {}


def _build_impactos_por_repositorio(matriz: list[dict]) -> dict:
    result: dict[str, dict] = {}
    for m in matriz:
        repo = m["repositorio"]
        if repo not in result:
            result[repo] = {"total": 0, "Alta": 0, "M\u00e9dia": 0, "Baixa": 0, "areas": set()}
        result[repo]["total"] += 1
        result[repo][m["complexidade"]] += 1
        result[repo]["areas"].add(m["area"])
    return dict(sorted(
        {k: {**v, "areas": sorted(v["areas"])} for k, v in result.items()}.items(),
        key=lambda x: x[1]["total"], reverse=True,
    ))


def build_output(raw_impacts: list[dict], cfg: dict, repos_analisados: list[str], repo_stats: dict | None = None) -> dict:
    from core.engine import requires_dual_compat, dual_compat_motivo
    from datetime import datetime, timezone, timedelta
    tz_br = timezone(timedelta(hours=-3))
    status_anteriores = _load_status_anteriores(cfg.get("output_file", "impacto_cnpj.json"))
    matriz = []
    for idx, imp in enumerate(raw_impacts, start=1):
        rule, filepath, match = imp["_rule"], imp["filepath"], imp["match"]
        trecho = match["trecho_codigo"]
        dual = requires_dual_compat(rule["area"], trecho)
        chave = f"{imp['repositorio']}:{filepath}:{match['linha']}"
        status_anterior = status_anteriores.get(chave, {"status": "pendente", "responsavel": None, "observacao": None})
        matriz.append({
            "id": f"IMP-{idx:04d}",
            "area": rule["area"],
            "repositorio": imp["repositorio"],
            "componente": filepath,
            "descricao_impacto": rule["descricao_impacto"],
            "complexidade": rule["complexidade"],
            "prioridade": _calc_prioridade(rule["complexidade"], imp.get("arquivo_critico", False)),
            "status_migracao": match.get("status_migracao", "impacto"),
            "motivo_status": match.get("motivo_status"),
            "status": status_anterior["status"],
            "responsavel": status_anterior["responsavel"],
            "observacao": status_anterior["observacao"],
            "chamadores_estimados": imp.get("chamadores_estimados", 0),
            "arquivo_critico": imp.get("arquivo_critico", False),
            "requer_compatibilidade_dual": dual,
            "motivo_compatibilidade_dual": dual_compat_motivo(rule["area"], trecho) if dual else None,
            "evidencia": {"arquivo": filepath, "linha": match["linha"], "trecho_codigo": trecho},
            "observacoes": f"Regra: {rule.get('id', rule.get('area', '?'))} | Padrao: {match['pattern_matched']}",
        "fluxo": _inferir_tela(filepath, imp["repositorio"], get_tela_keywords(cfg)),
        })
    areas = {}
    for m in matriz:
        areas[m["area"]] = areas.get(m["area"], 0) + 1
    repos_com_impacto = {m["repositorio"] for m in matriz}
    repos_sem_impacto = sorted(set(repos_analisados) - repos_com_impacto)
    plan            = build_plan(matriz, cfg)
    ordem_migracao  = plan["ordem_migracao"]
    gargalos        = plan["gargalos"]
    spof            = plan["spof"]
    trilhas         = plan["trilhas"]
    now = datetime.now(tz_br)
    titulo = get_titulo(cfg)
    return {
        "titulo_analise": titulo,
        "spec_versao": "1.2",
        "versao_regras": cfg.get("versao_regras", "scanner-config.json"),
        "scan_id": now.strftime("%Y%m%d_%H%M%S"),
        "data_execucao": now.isoformat(),
        "data_limite_migracao": cfg.get("data_limite_migracao", None),
        "sistema_escopo": cfg["sistema_escopo"],
        "estatisticas": {
            "total_repositorios_analisados": len(repos_analisados),
            "total_repositorios_com_impacto": len(repos_com_impacto),
            "total_repositorios_sem_impacto": len(repos_sem_impacto),
            "total_impactos_encontrados": len(matriz),
            "impactos_por_area": areas,
            "impactos_por_complexidade": {
                "Alta":  sum(1 for m in matriz if m["complexidade"] == "Alta"),
                "Média": sum(1 for m in matriz if m["complexidade"] == "Média"),
                "Baixa": sum(1 for m in matriz if m["complexidade"] == "Baixa"),
            },
            "status_migracao": {
                "impacto":    sum(1 for m in matriz if m["status_migracao"] == "impacto"),
                "revisao":    sum(1 for m in matriz if m["status_migracao"] == "revisao"),
                "compativel": sum(1 for m in matriz if m["status_migracao"] == "compativel"),
            },
            "impactos_por_repositorio": _build_impactos_por_repositorio(matriz),
            "candidatos_por_repositorio": repo_stats or {},
            "chamadores_criticos_total": sum(m["chamadores_estimados"] for m in matriz if m["arquivo_critico"]),
            "requerem_compatibilidade_dual": sum(1 for m in matriz if m["requer_compatibilidade_dual"]),
            "arquivos_criticos": sum(1 for m in matriz if m["arquivo_critico"]),
            "progresso": {
                "pendente":    sum(1 for m in matriz if m["status"] == "pendente"),
                "em_progresso": sum(1 for m in matriz if m["status"] == "em_progresso"),
                "resolvido":   sum(1 for m in matriz if m["status"] == "resolvido"),
                "falso_positivo": sum(1 for m in matriz if m["status"] == "falso_positivo"),
            },
        },
        "cobertura": {
            "repositorios_sem_impacto": repos_sem_impacto,
            "repos_sem_impacto_com_aliases": {},
            "pontos_cegos": get_pontos_cegos(cfg),
        },
        "repositorios_analisados": repos_analisados,
        "matriz_impacto": matriz,
        "ordem_migracao": ordem_migracao,
        "arquivos_criticos": _build_arquivos_criticos(matriz),
        "checklist_rollback": _build_checklist_rollback(matriz, cfg),
        "impacto_dados": _build_impacto_dados(matriz, cfg),
        "riscos_mapeados": _build_riscos(matriz, cfg),
        "parceiros_externos": _build_parceiros_externos(matriz, cfg),
        "pendencias_identificadas": _build_pendencias(matriz),
        "telas_qa": _build_telas_qa(matriz, cfg),
        "trilhas": trilhas,
        "gargalos": gargalos,
        "spof": spof,
        "heatmap_risco": plan["heatmap_risco"],
        "criterios_aceite": _build_criterios_aceite(matriz, ordem_migracao, cfg),
        "esforco": plan["esforco"],
        "risk_score": plan["risk_score"],
        "sugestoes_movimentacao": plan["sugestoes_movimentacao"],
        "oportunidades_refatoracao": _build_oportunidades_refatoracao(matriz, ordem_migracao),
        "simulation": plan["simulation"],
        "migration_readiness": plan["migration_readiness"],
        "flows": build_flow_analysis(matriz, cfg),
    }

def _calc_prioridade(complexidade: str, critico: bool) -> str:
    if critico or complexidade == "Alta":
        return "P1"
    if complexidade == "Média":
        return "P2"
    return "P3"


# ---------------------------------------------------------------------------
# Mapeamento de telas para QA
# ---------------------------------------------------------------------------

def _inferir_tela(filepath: str, repo: str, tela_keywords: list) -> str | None:
    """Retorna o nome funcional da tela/fluxo inferido a partir do caminho do arquivo."""
    if not tela_keywords:
        return None
    path_lower = filepath.lower().replace("-", "").replace("_", "")
    repo_lower = repo.lower().replace("-", "")
    combined = path_lower + " " + repo_lower
    for keywords, nome in tela_keywords:
        if any(kw.lower().replace("-", "").replace("_", "") in combined for kw in keywords):
            return nome
    return None


def _build_telas_qa(matriz: list[dict], cfg: dict) -> list[dict]:
    tela_keywords = get_tela_keywords(cfg)
    _AREAS_VISIVEIS = {"Frontend", "Backend", "Processamento/Batch", "Integrações"}
    telas: dict[str, dict] = {}
    for m in matriz:
        if m["area"] not in _AREAS_VISIVEIS:
            continue
        tela = _inferir_tela(m["evidencia"]["arquivo"], m["repositorio"], tela_keywords)
        if not tela:
            continue
        if tela not in telas:
            telas[tela] = {
                "tela": tela,
                "repositorios": set(),
                "areas_impactadas": set(),
                "prioridade_maxima": "P3",
                "impactos": 0,
                "requer_compatibilidade_dual": False,
                "tipo_teste": set(),
                "evidencias": [],
            }
        t = telas[tela]
        t["repositorios"].add(m["repositorio"])
        t["areas_impactadas"].add(m["area"])
        t["impactos"] += 1
        if m["requer_compatibilidade_dual"]:
            t["requer_compatibilidade_dual"] = True
        if m["prioridade"] == "P1":
            t["prioridade_maxima"] = "P1"
        elif m["prioridade"] == "P2" and t["prioridade_maxima"] != "P1":
            t["prioridade_maxima"] = "P2"
        area = m["area"]
        if area == "Frontend":
            t["tipo_teste"].add("UI: campo aceita novo formato")
        if area == "Backend":
            t["tipo_teste"].add("Funcional: fluxo completo com novo formato")
        if area == "Processamento/Batch":
            t["tipo_teste"].add("Funcional: geração de documento/relatório com novo formato")
        if area == "Integrações":
            t["tipo_teste"].add("Integração: envio/recebimento com novo formato para parceiro")
        if m["requer_compatibilidade_dual"]:
            t["tipo_teste"].add("Regressão: formato antigo continua funcionando")
        if len(t["evidencias"]) < 2:
            t["evidencias"].append({
                "arquivo": m["evidencia"]["arquivo"],
                "linha": m["evidencia"]["linha"],
                "trecho": m["evidencia"]["trecho_codigo"][:80],
            })
    _PRIO_ORDER = {"P1": 0, "P2": 1, "P3": 2}
    result = []
    for t in telas.values():
        result.append({
            "tela": t["tela"],
            "prioridade": t["prioridade_maxima"],
            "repositorios": sorted(t["repositorios"]),
            "areas_impactadas": sorted(t["areas_impactadas"]),
            "total_impactos": t["impactos"],
            "requer_compatibilidade_dual": t["requer_compatibilidade_dual"],
            "testes_sugeridos": sorted(t["tipo_teste"]),
            "evidencias": t["evidencias"],
        })
    result.sort(key=lambda x: (_PRIO_ORDER.get(x["prioridade"], 9), -x["total_impactos"]))
    return result


# ---------------------------------------------------------------------------
# generate_markdown  (telas_qa inserido antes de Pendencias)
# ---------------------------------------------------------------------------

def generate_markdown(output: dict) -> str:
    lines = []
    stats = output["estatisticas"]
    titulo = output.get("titulo_analise", "Análise de Impacto")

    lines += [
        f"# 📋 {titulo}\n",
        f"**Sistema:** {output['sistema_escopo']}  ",
        f"**Data:** {output['data_execucao']}  ",
        f"**Scan ID:** `{output.get('scan_id', '—')}`  ",
        f"**Versão SPEC:** {output['spec_versao']}\n",
    ]

    # Resumo
    lines += [
        "## 📊 Resumo Executivo\n",
        "| Métrica | Valor |", "|---------|-------|",
        f"| Repositórios analisados | {stats['total_repositorios_analisados']} |",
        f"| Total de impactos | {stats['total_impactos_encontrados']} |",
        f"| Requerem compatibilidade dual | {stats.get('requerem_compatibilidade_dual', 0)} |",
    ]
    for area, count in sorted(stats["impactos_por_area"].items()):
        lines.append(f"| Impactos em {area} | {count} |")
    lines.append("")

    lines += ["### Distribuição por Complexidade\n", "| Complexidade | Quantidade |", "|--------------|------------|"]
    for compl, count in stats["impactos_por_complexidade"].items():
        emoji = {"Alta": "🔴", "Média": "🟡", "Baixa": "🟢"}.get(compl, "⚪")
        lines.append(f"| {emoji} {compl} | {count} |")
    lines.append("")

    # Fluxos de negócio
    flows = output.get("flows", [])
    if flows:
        lines += [
            "## 🔄 Maturidade por Fluxo de Negócio\n",
            "> Score = % de ocorrências compatíveis sobre o total detectado no fluxo. "
            "Fluxos com **Impactos = 0** estão prontos para homologação.\n",
            "| Fluxo | Score | Compatíveis | Revisão | Impactos | Status |",
            "|-------|-------|-------------|---------|----------|--------|"]
        for f in flows:
            emoji = "✅" if f["impacto"] == 0 and f["revisao"] == 0 else ("⚠️" if f["impacto"] == 0 else "❌")
            lines.append(
                f"| {emoji} **{f['name']}** | {f['score']}% "
                f"| {f['compativel']} | {f['revisao']} | {f['impacto']} "
                f"| {f['status']} |"
            )
        lines.append("")

        for f in flows:
            lines.append(f"### Fluxo: {f['name']}\n")
            lines.append(f"> Repos: {', '.join(f'`{r}`' for r in f['repos'])}\n")

            # Matriz repo × status
            lines += [
                "| Repositório | Compatíveis | Revisão | Impactos | Total |",
                "|-------------|-------------|---------|----------|-------|"]
            for rs in f["repos_summary"]:
                icon = "✅" if rs["impacto"] == 0 and rs["revisao"] == 0 else ("⚠️" if rs["impacto"] == 0 else "❌")
                lines.append(
                    f"| {icon} `{rs['repo']}` "
                    f"| {rs['compativel']} | {rs['revisao']} | {rs['impacto']} | {rs['total']} |"
                )
            lines.append("")

            # Matriz área × status
            if f["areas"]:
                lines += [
                    "| Área | Compatíveis | Revisão | Impactos |",
                    "|------|-------------|---------|----------|"]
                for area, counts in sorted(f["areas"].items()):
                    icon = "✅" if counts.get("impacto", 0) == 0 and counts.get("revisao", 0) == 0 else (
                        "⚠️" if counts.get("impacto", 0) == 0 else "❌")
                    lines.append(
                        f"| {icon} {area} "
                        f"| {counts.get('compativel', 0)} "
                        f"| {counts.get('revisao', 0)} "
                        f"| {counts.get('impacto', 0)} |"
                    )
                lines.append("")

    # Arquivos críticos — seção mais importante para o time de engenharia
    criticos = output.get("arquivos_criticos", [])
    if criticos:
        lines += [
            "## 🚨 Arquivos Críticos – Migrar Primeiro\n",
            "> Arquivos com maior número de chamadores estimados. "
            "Mudar estes componentes tem efeito cascata em toda a aplicação. "
            "**Devem ser os primeiros a receber testes de regressão e feature flags.**\n",
            "| # | Repositório | Arquivo | Área | Chamadores | Impactos | Dual | Linhas |",
            "|---|-------------|---------|------|------------|----------|------|--------|"]
        for i, arq in enumerate(criticos, start=1):
            dual = "✅" if arq["requer_compatibilidade_dual"] else "—"
            linhas = ", ".join(str(l) for l in sorted(set(arq["linhas_afetadas"]))[:5])
            if len(arq["linhas_afetadas"]) > 5:
                linhas += f" (+{len(arq['linhas_afetadas'])-5})"
            nome = arq["arquivo"].split("/")[-1]
            lines.append(
                f"| {i} | `{arq['repositorio']}` | `{nome}` "
                f"| {arq['area']} | **{arq['chamadores_estimados']}** "
                f"| {arq['impactos_no_arquivo']} | {dual} | {linhas} |"
            )
        lines.append("")

    # Matriz
    lines.append("## 🗂️ Matriz de Impacto\n")
    agrupado: dict[str, list] = {}
    for m in output["matriz_impacto"]:
        agrupado.setdefault(m["area"], []).append(m)

    for area, items in sorted(agrupado.items()):
        lines.append(f"### {area} ({len(items)} impacto(s))\n")
        lines += ["| ID | Repositório | Componente | Complexidade | Chamadores | Dual | Descrição |",
                  "|----|-------------|------------|--------------|------------|------|-----------|"]
        for m in items[:50]:
            dual = "✅" if m.get("requer_compatibilidade_dual") else "—"
            lines.append(
                f"| {m['id']} | {m['repositorio']} | `{m['componente']}` "
                f"| {m['complexidade']} | {m.get('chamadores_estimados', 0)} | {dual} | {m['descricao_impacto'][:80]} |"
            )
        if len(items) > 50:
            lines.append(f"| ... | +{len(items)-50} itens (ver JSON) | | | | | |")
        lines.append("")

    # Evidências
    lines += ["## 🔍 Evidências (amostra)\n", "```"]
    for m in output["matriz_impacto"][:20]:
        ev = m["evidencia"]
        lines += [f"[{m['id']}] {m['repositorio']}/{ev['arquivo']}:{ev['linha']}",
                  f"  → {ev['trecho_codigo'][:120]}", ""]
    lines += ["```\n"]

    # Ordem de migração por módulo
    lines += ["## 🗺️ Ordem de Migração por Módulo\n",
              "> Cada módulo (repositório) é migrado de forma independente. "
              "A sequência interna de áreas dentro de cada módulo segue a ordem de dependência técnica.\n"]
    for s in output.get("ordem_migracao", []):
        deps_str = ", ".join(f"`{d}`" for d in s.get("depende_de", []))
        lines.append(f"### Módulo {s['passo']}: `{s['modulo']}`\n")
        lines.append(f"**Total:** {s['total_impactos']} impactos | "
                     f"**Alta:** {s['impactos_alta_complexidade']} | "
                     f"**Dual:** {s['requerem_compatibilidade_dual']}"
                     + (f" | **Depende de:** {deps_str}" if deps_str else "") + "\n")
        lines += ["| Passo | Área | Impactos | Alta | Dual | Rationale |",
                  "|-------|------|----------|------|------|-----------|"]
        for i, a in enumerate(s["areas"], start=1):
            lines.append(
                f"| {i} | {a['area']} | {a['total_impactos']} "
                f"| {a['impactos_alta_complexidade']} | {a['requerem_compatibilidade_dual']} "
                f"| {a['rationale'][:80]} |"
            )
        lines.append("")

    # Mapa de calor de risco por sprint
    heatmap = output.get("heatmap_risco", [])
    if heatmap:
        _H_EMOJI = {"Crítico": "🔴", "Alto": "🟠", "Médio": "🟡", "Baixo": "🟢"}
        lines += [
            "## 🌡️ Mapa de Calor de Risco por Sprint\n",
            "> Score composto: impactos Alta (×2) + SPOF (+5) + Gargalo (+3×nível) + Fluxo partido (+4). "
            "Normalizado 0–100.\n",
            "| Sprint | Módulo | Nível | Score | Fatores |",
            "|--------|--------|-------|-------|---------|"]
        for h in heatmap:
            emoji = _H_EMOJI.get(h["nivel_risco"], "")
            fatores = ", ".join(h["fatores"]) or "—"
            lines.append(
                f"| {h['passo']} | `{h['modulo']}` "
                f"| {emoji} {h['nivel_risco']} | {h['score_normalizado']} "
                f"| {fatores} |"
            )
        lines.append("")

    # SPOFs
    spof = output.get("spof", [])
    if spof:
        lines += [
            "## ⚡ SPOFs — Pontos Únicos de Falha\n",
            "> Repos que são o **único** representante de um domínio crítico. "
            "Qualquer atraso neles bloqueia o domínio inteiro sem substituto.\n",
            "| Domínio | Repositório | Sprint | Impactos Alta | Alerta |",
            "|---------|------------|--------|---------------|--------|"]
        for s in spof:
            lines.append(
                f"| **{s['dominio']}** | `{s['repositorio']}` "
                f"| {s.get('passo_migracao', '—')} | {s['impactos_alta']} "
                f"| {s['alerta']} |"
            )
        lines.append("")

    # Gargalos arquiteturais
    gargalos = output.get("gargalos", [])
    if gargalos:
        _G_EMOJI = {"Crítico": "🔴", "Alto": "🟠", "Médio": "🟡"}
        lines += [
            "## 🔥 Gargalos Arquiteturais\n",
            "> Repos que participam de muitos fluxos. Qualquer atraso neles atrasa a migração inteira.\n",
            "| Nível | Repositório | Fluxos | % do Total | Sprint | Alerta |",
            "|-------|------------|--------|------------|--------|--------|"]
        for g in gargalos:
            emoji = _G_EMOJI.get(g["nivel"], "")
            lines.append(
                f"| {emoji} {g['nivel']} | `{g['repositorio']}` "
                f"| {g['n_fluxos']} | {g['pct_fluxos']}% "
                f"| {g.get('passo_migracao', '—')} | {g['alerta']} |"
            )
        lines.append("")

    # Trilhas paralelas
    trilhas_data = output.get("trilhas")
    if trilhas_data:
        n = trilhas_data["n_trilhas"]
        delta = trilhas_data["desequilibrio_pct"]
        lines += [
            f"## 🔀 Divisão em {n} Trilhas Paralelas\n",
            f"> Repos agrupados por similaridade de áreas impactadas e divididos em {n} trilhas com carga equilibrada.",
            f"> Desequilíbrio de carga: **{delta}%** (quanto menor, mais equilibrado).\n",
        ]

        # Grupos
        lines.append("### Grupos de Repos com Perfil Parecido\n")
        lines += ["| Grupo | Perfil de Áreas | Repos | Impactos Difíceis | Total |",
                  "|-------|----------------|-------|-------------------|-------|"]
        for g in trilhas_data["grupos"]:
            repos_str = ", ".join(f"`{r['modulo']}`" for r in g["repositorios"])
            lines.append(f"| {g['grupo']} | {g['perfil']} | {repos_str} | {g['total_alta']} | {g['total_impactos']} |")
        lines.append("")

        # Trilhas
        for t in trilhas_data["trilhas"]:
            lines.append(f"### Trilha {t['trilha']}  —  {t['carga_alta']} impactos difíceis | {t['total_impactos']} total\n")
            completos = t.get("fluxos_completos", [])
            if completos:
                lines.append("**Fluxos completos nesta trilha:** " + " · ".join(f"`{f}`" for f in completos) + "\n")
            lines += ["| Ordem | Repo | Difíceis | Total | Áreas | Fluxos |",
                      "|-------|------|----------|-------|-------|--------|"]
            for r in t["repositorios"]:
                fluxos_str = ", ".join(r.get("fluxos", [])) or "—"
                lines.append(f"| {r['passo']} | `{r['modulo']}` | {r['alta']} | {r['total']} | {r['perfil']} | {fluxos_str} |")
            lines.append("")

        # Fluxos partidos
        partidos = trilhas_data.get("fluxos_partidos", [])
        if partidos:
            lines.append("### ⚠️ Fluxos Partidos entre Trilhas — Coordenar Entrega\n")
            lines.append("> Estes fluxos têm repos em trilhas diferentes. As trilhas precisam sincronizar antes do go-live.\n")
            lines += ["| Gravidade | Fluxo | Trilhas | Repos | Repositórios |",
                      "|-----------|-------|---------|-------|-------------|"]
            _G_EMOJI = {"Crítico": "🔴", "Alto": "🟠", "Médio": "🟡", "Baixo": "🟢"}
            for fp in partidos:
                g = fp.get("gravidade", "—")
                trilhas_str = ", ".join(f"T{t}" for t in fp["trilhas"])
                repos_str = ", ".join(f"`{r}`" for r in fp["repositorios"])
                lines.append(f"| {_G_EMOJI.get(g, '')} {g} | **{fp['fluxo']}** | {trilhas_str} | {fp.get('n_repositorios', len(fp['repositorios']))} | {repos_str} |")
            lines.append("")

        # Grafo de dependências entre trilhas
        grafo = trilhas_data.get("grafo_dependencias", {})
        arestas = grafo.get("arestas", [])
        if arestas:
            lines.append("### 🔗 Dependências entre Trilhas\n")
            lines.append("> Trilha de origem deve ser concluída antes da trilha de destino.\n")
            lines += ["| De | Para | Motivo |",
                      "|----|------|--------|"]
            for a in arestas:
                motivos = "; ".join(a["motivos"][:3])
                if len(a["motivos"]) > 3:
                    motivos += f" (+{len(a['motivos'])-3})"
                lines.append(f"| Trilha {a['de']} | Trilha {a['para']} | {motivos} |")
            lines.append("")

        # Dependências cruzadas
        deps = trilhas_data.get("dependencias_cruzadas", [])
        if deps:
            lines.append("### ⚠️ Coordenar antes do merge\n")
            for dep in deps:
                repos_str = ", ".join(f"`{m}`" for m in dep["repositorios"])
                lines.append(f"- **{dep['area']}**: {repos_str} — definir quem faz a migration/versão de API primeiro.")
            lines.append("")

    # Migration Readiness Score
    readiness = output.get("migration_readiness")
    if readiness:
        _R_EMOJI = {"Pronto": "✅", "Atenção": "🟡", "Risco": "🟠", "Crítico": "🔴"}
        emoji = _R_EMOJI.get(readiness["nivel"], "")
        lines += [
            "## 🎯 Migration Readiness Score\n",
            f"> {emoji} **{readiness['nivel']}** — Score: **{readiness['score']}/100**\n",
            "| Dimensão | Status | Detalhe |",
            "|---------|--------|---------|"]
        for c in readiness["checks"]:
            lines.append(f"| {c['dimensao']} | {c['status']} | {c['detalhe']} |")
        lines.append("")

    # Simulação de estratégias
    sim = output.get("simulation")
    if sim and sim.get("recomendacao"):
        rec = sim["recomendacao"]
        lines += [
            "## 🧪 Simulação de Estratégias de Trilhas\n",
            f"> **Recomendação:** {rec['justificativa']}\n",
            "| Trilhas | Estratégia | Score | Fluxos Partidos | Desequilíbrio | Dias |",
            "|---------|-----------|-------|-----------------|--------------|------|"
        ]
        for r in sim["resultados"][:10]:
            rec_mark = " ⭐" if r["recomendada"] else ""
            lines.append(
                f"| {r['n_trilhas']} | {r['strategy']}{rec_mark} "
                f"| **{r['score']}** | {r['fluxos_partidos']} "
                f"| {r['desequilibrio_pct']}% | {r['dias_estimados']} |"
            )
        lines.append("")

    # Estimativa de esforço por módulo
    esforco = output.get("esforco", [])
    if esforco:
        dias_total_geral = sum(e["dias_estimados"] for e in esforco)
        sp_total = sum(e["story_points"] for e in esforco)
        lines += [
            "## ⏱️ Estimativa de Esforço por Módulo\n",
            f"> Total estimado: **{dias_total_geral:.1f} dias** | **{sp_total} story points**  ",
            "> Fórmula: Σ(dias por impacto × fator dual) + overhead fixo (2 dias). Story points em escala Fibonacci.\n",
            "| Sprint | Módulo | Dias | SP | Dual | Maior Área |",
            "|--------|--------|------|----|------|-----------|"]
        for e in esforco:
            maior = e["esforco_por_area"][0]["area"] if e["esforco_por_area"] else "—"
            dual  = "✅" if e["requer_dual"] else "—"
            lines.append(
                f"| {e['passo']} | `{e['modulo']}` "
                f"| {e['dias_estimados']} | **{e['story_points']}** "
                f"| {dual} | {maior} |"
            )
        lines.append("")

    # Critérios de aceite por módulo
    criterios = output.get("criterios_aceite", [])
    if criterios:
        lines += [
            "## ✅ Critérios de Aceite por Módulo\n",
            "> Condições que devem ser verdadeiras para considerar o módulo migrado e pronto para go-live.\n",
        ]
        for c in criterios:
            lines.append(f"### Módulo {c['passo']}: `{c['modulo']}`\n")
            for ca in c["criterios_por_area"]:
                lines.append(f"**{ca['area']}**\n")
                lines += [f"- [ ] {cr}" for cr in ca["criterios"]]
                lines.append("")
            lines.append("**Encerramento**\n")
            lines += [f"- [ ] {cr}" for cr in c["criterios_encerramento"]]
            lines.append("")

    # Checklist rollback
    lines.append("## 🔄 Checklist de Rollback\n")
    for area, perguntas in output.get("checklist_rollback", {}).items():
        lines.append(f"### {area}\n")
        lines += [f"- [ ] {p}" for p in perguntas]
        lines.append("")

    # Impacto em dados
    if output.get("impacto_dados"):
        lines.append("## 🗄️ Impacto em Dados – Queries de Estimativa\n")
        for area, info in output["impacto_dados"].items():
            lines += [f"### {area}\n", f"_{info['descricao']}_\n"]
            for q in info["queries"]:
                lines += ["```sql", q, "```\n"]
        lines.append("")

    # Riscos
    lines += ["## ⚠️ Riscos Mapeados\n",
              "| Risco | Impacto | Mitigação |", "|-------|---------|-----------|"]
    for r in output["riscos_mapeados"]:
        lines.append(f"| {r['risco']} | {r['impacto'][:80]} | {r['mitigacao'][:80]} |")
    lines.append("")

    # Parceiros externos
    parceiros = output.get("parceiros_externos", [])
    if parceiros:
        lines += [
            "## 🤝 Parceiros Externos — Alinhamento Necessário\n",
            "> Parceiros detectados nos impactos. "
            "**Cada um precisa confirmar suporte antes do go-live.**\n",
            "| Parceiro | Descrição | Repositórios | Status |",
            "|----------|-----------|-------------|--------|"]
        for p in parceiros:
            repos_str = ", ".join(f"`{r}`" for r in p["repositorios"])
            lines.append(f"| **{p['parceiro']}** | {p['descricao']} | {repos_str} | {p['status_alinhamento']} |")
        lines.append("")

    # Progresso
    prog = stats.get("progresso", {})
    if prog:
        total = stats["total_impactos_encontrados"]
        resolvidos = prog.get("resolvido", 0) + prog.get("falso_positivo", 0)
        pct = round(resolvidos / total * 100) if total else 0
        lines += [
            "## 📈 Progresso da Migração\n",
            f"> {resolvidos}/{total} impactos endereçados ({pct}%)\n",
            "| Status | Quantidade |", "|--------|------------|"]
        for status, count in prog.items():
            emoji = {"pendente": "⏳", "em_progresso": "🔄", "resolvido": "✅", "falso_positivo": "🚫"}.get(status, "")
            lines.append(f"| {emoji} {status} | {count} |")
        lines.append("")

    # Seções extras configuradas no config (genéricas, domínio-específicas)
    for secao in output.get("secoes_extras", []):
        lines.append(f"## {secao.get('titulo', 'Seção Extra')}\n")
        if secao.get("descricao"):
            lines.append(f"> {secao['descricao']}\n")
        for bloco in secao.get("blocos", []):
            if bloco.get("subtitulo"):
                lines.append(f"### {bloco['subtitulo']}\n")
            if bloco.get("nota"):
                lines.append(f"> {bloco['nota']}\n")
            if bloco.get("tabela"):
                headers = bloco["tabela"].get("headers", [])
                rows = bloco["tabela"].get("rows", [])
                if headers:
                    lines.append("| " + " | ".join(headers) + " |")
                    lines.append("|" + "---|" * len(headers))
                for row in rows:
                    lines.append("| " + " | ".join(str(c) for c in row) + " |")
            lines.append("")

    # Telas para QA
    telas_qa = output.get("telas_qa", [])
    if telas_qa:
        lines += [
            "## Telas para QA\n",
            "> Telas e fluxos inferidos a partir dos impactos de codigo. "
            "Testar com CNPJ alfanumerico (ex: `12.ABC.345/01DE-35`) "
            "e verificar que CNPJ numerico antigo continua funcionando.\n",
            "| Prioridade | Tela / Fluxo | Repositorios | Testes Sugeridos | Dual? |",
            "|------------|-------------|-------------|-----------------|-------|"]
        for t in telas_qa:
            repos_str = ", ".join(f"`{r}`" for r in t["repositorios"])
            testes_str = " / ".join(t["testes_sugeridos"])
            dual = "Sim" if t["requer_compatibilidade_dual"] else "Nao"
            lines.append(
                f"| **{t['prioridade']}** | {t['tela']} | {repos_str} "
                f"| {testes_str[:120]} | {dual} |"
            )
        lines.append("")

    # Pendencias
    lines += ["## 📌 Pendências\n",
              "| ID | Descrição | Responsável | Prazo |", "|----|-----------|-------------|-------|"]
    for p in output["pendencias_identificadas"]:
        lines.append(f"| {p['id']} | {p['descricao'][:100]} | {p['responsavel']} | {p['prazo_estimado']} |")
    lines.append("")

    # Cobertura / pontos cegos
    cobertura = output.get("cobertura", {})
    sem_impacto = cobertura.get("repositorios_sem_impacto", [])
    pontos_cegos = cobertura.get("pontos_cegos", [])
    if pontos_cegos:
        lines.append("## ⚠️ Limitações de Cobertura\n")
        lines.append("> Esta varredura é baseada em análise estática por regex. Os pontos abaixo representam riscos de falso negativo.\n")
        for pc in pontos_cegos:
            lines += [f"**{pc['id']}** — {pc['descricao']}", f"_Recomendação:_ {pc['recomendacao']}", ""]
    aliases_suspeitos = cobertura.get("repos_sem_impacto_com_aliases", {})
    if aliases_suspeitos:
        lines.append("### ⚠️ Repos sem impacto mas com aliases suspeitos\n")
        lines.append("> Estes repos não usam a palavra 'cnpj' mas contêm campos que podem processar CNPJ indiretamente. **Requerem revisão manual.**\n")
        lines += ["| Repositório | Aliases encontrados |", "|-------------|---------------------|"]
        for repo, aliases in aliases_suspeitos.items():
            lines.append(f"| `{repo}` | {', '.join(f'`{a}`' for a in aliases)} |")
        lines.append("")
    if sem_impacto:
        lines.append(f"### Repositórios sem impacto detectado ({len(sem_impacto)})\n")
        lines.append("> Podem ser genuinamente não afetados ou usar aliases de campo sem a palavra 'cnpj'.\n")
        lines += [f"- `{r}`" for r in sem_impacto]
        lines.append("")

    # Repositórios
    lines.append("## 📦 Repositórios Analisados\n")
    lines += [f"- `{r}`" for r in output["repositorios_analisados"]]
    lines += ["", "---\n", f"*Gerado automaticamente pelo Impact Scanner*"]

    return "\n".join(lines)
