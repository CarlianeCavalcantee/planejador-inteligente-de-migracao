"""
Cria work items no Azure DevOps a partir do impacto_cnpj.json.

Hierarquia:
  Épico (existente, fornecido via ADO_EPIC_ID)
    Feature  — 1 por fluxo de negócio (ex: PIX, Conta Digital)
      PBI    — 1 por (fluxo × repositório), ex: [PIX] pix-api
        Task — 1 por categoria técnica (DTOs, Entidades, SQL, etc.) com todos os impactos na descrição
        Task — tasks fixas de encerramento (Code Review, Testes, Deploy, Homologação, Scanner)

Uso:
  python azuredevops_export.py           # dry-run (padrão)
  python azuredevops_export.py --csv     # exporta ado_workitems.csv
  python azuredevops_export.py --create  # cria via API REST

Variáveis de ambiente para --create:
  ADO_ORG      = https://dev.azure.com/<org>
  ADO_PROJECT  = <projeto>
  ADO_PAT      = <personal-access-token>
  ADO_EPIC_ID  = <id numérico do Épico existente>
"""

import csv
import json
import os
import sys
from collections import defaultdict
from pathlib import Path

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

_PRIO_ADO = {"P1": 1, "P2": 2, "P3": 3}

_AREA_RATIONALE = {
    "Segurança/LGPD":      "Remover dados reais do codigo antes de qualquer outra mudanca.",
    "Banco de Dados":      "Migrar schema primeiro — todas as camadas dependem do tipo da coluna.",
    "API/Contrato":        "Versionar contratos antes de alterar implementacao.",
    "Infraestrutura/CI":   "Atualizar pipelines para que builds usem o novo formato.",
    "Configuração":        "Externalizar CNPJs fixos antes de subir nova versao.",
    "Integrações":         "Comunicar parceiros externos antes de alterar payloads.",
    "Processamento/Batch": "Atualizar layouts de arquivo e validacoes de ETL apos schema de BD.",
    "Backend":             "Refatorar validadores e logica de negocio apos BD e contratos.",
    "Testes/Qualidade":    "Atualizar massa de dados e fixtures para cobrir o novo formato.",
    "Documentação":        "Atualizar docs e exemplos apos implementacao concluida.",
    "Frontend":            "Atualizar mascaras e validacoes de UI por ultimo.",
}

# Tasks fixas adicionadas ao final de cada PBI
_CLOSURE_TASKS = [
    {
        "titulo": "Code Review — Revisão técnica e aprovação Tech Lead",
        "checklist": ["☐ Revisão técnica", "☐ Aprovação Tech Lead"],
        "tags": "code-review",
    },
    {
        "titulo": "Testes — Unitários, Integração e Regressão",
        "checklist": ["☐ Testes unitários", "☐ Testes de integração", "☐ Testes de regressão"],
        "tags": "testes",
    },
    {
        "titulo": "Deploy — DEV / QA / HML",
        "checklist": ["☐ Deploy DEV", "☐ Deploy QA", "☐ Deploy HML"],
        "tags": "deploy",
    },
    {
        "titulo": "Homologação — Validar migração do repositório",
        "checklist": ["☐ Homologar migração do repositório"],
        "tags": "homologacao",
    },
    {
        "titulo": "Validação Scanner — Executar scanner e confirmar ausência de ocorrências",
        "checklist": ["☐ Executar scanner novamente", "☐ Validar ausência de ocorrências"],
        "tags": "scanner-validation",
    },
]

_FLUXO_FALLBACK = "Sem Fluxo Mapeado"

# Mapeamento arquivo → categoria de task (ordem importa: primeiro match vence)
_CATEGORIA_RULES: list[tuple[str, str]] = [
    # padrões de nome de arquivo (lowercase)
    ("dto",          "Ajustar DTOs"),
    ("request",      "Ajustar DTOs"),
    ("response",     "Ajustar DTOs"),
    ("entity",       "Ajustar Entidades"),
    ("entidade",     "Ajustar Entidades"),
    ("model",        "Ajustar Entidades"),
    ("domain",       "Ajustar Entidades"),
    ("repository",   "Ajustar Repositórios"),
    ("dao",          "Ajustar Repositórios"),
    ("service",      "Ajustar Services"),
    ("usecase",      "Ajustar Services"),
    ("use_case",     "Ajustar Services"),
    ("controller",   "Ajustar Controllers/APIs"),
    ("resource",     "Ajustar Controllers/APIs"),
    ("handler",      "Ajustar Controllers/APIs"),
    (".sql",         "Ajustar SQL"),
    ("migration",    "Ajustar SQL"),
    ("flyway",       "Ajustar SQL"),
    ("liquibase",    "Ajustar SQL"),
    ("changelog",    "Ajustar SQL"),
    ("test",         "Atualizar Testes"),
    ("spec",         "Atualizar Testes"),
    ("mock",         "Atualizar Testes"),
    ("fixture",      "Atualizar Testes"),
    ("seed",         "Atualizar Testes"),
    (".tsx",         "Ajustar Frontend"),
    (".jsx",         "Ajustar Frontend"),
    ("component",    "Ajustar Frontend"),
    ("mask",         "Ajustar Frontend"),
    ("validator",    "Ajustar Validadores"),
    ("validation",   "Ajustar Validadores"),
    ("formatter",    "Ajustar Validadores"),
    (".yml",         "Ajustar Configuração/CI"),
    (".yaml",        "Ajustar Configuração/CI"),
    (".properties",  "Ajustar Configuração/CI"),
    ("dockerfile",   "Ajustar Configuração/CI"),
    ("jenkinsfile",  "Ajustar Configuração/CI"),
]

_CATEGORIA_AREA: dict[str, str] = {
    "Banco de Dados":      "Ajustar SQL",
    "API/Contrato":        "Ajustar Controllers/APIs",
    "Frontend":            "Ajustar Frontend",
    "Testes/Qualidade":    "Atualizar Testes",
    "Infraestrutura/CI":   "Ajustar Configuração/CI",
    "Configuração":        "Ajustar Configuração/CI",
    "Segurança/LGPD":      "Ajustar Segurança/LGPD",
    "Integrações":         "Ajustar Integrações",
    "Processamento/Batch": "Ajustar Batch/ETL",
    "Documentação":        "Atualizar Documentação",
}


def _categoria(imp: dict) -> str:
    arquivo_lower = imp["evidencia"]["arquivo"].lower()
    for pattern, cat in _CATEGORIA_RULES:
        if pattern in arquivo_lower:
            return cat
    return _CATEGORIA_AREA.get(imp["area"], "Ajustar Backend")


def _prio(imp: dict) -> int:
    return _PRIO_ADO.get(imp.get("prioridade", "P3"), 3)


def _tags_categoria(impactos: list[dict]) -> str:
    areas = {i["area"].lower().replace("/", "-") for i in impactos}
    tags  = ["cnpj-alfanumerico"] + sorted(areas)
    if any(i.get("requer_compatibilidade_dual") for i in impactos):
        tags.append("dual-compat")
    if any(i.get("arquivo_critico") for i in impactos):
        tags.append("arquivo-critico")
    return "; ".join(tags)


def _desc_categoria(impactos: list[dict], fluxo: str) -> str:
    arquivos = sorted({i["evidencia"]["arquivo"].split("/")[-1] for i in impactos})
    ids      = [i["id"] for i in impactos]
    linhas   = sorted({str(i["evidencia"]["linha"]) for i in impactos})
    dual     = [i["id"] for i in impactos if i.get("requer_compatibilidade_dual")]
    criticos = [i["evidencia"]["arquivo"].split("/")[-1] for i in impactos if i.get("arquivo_critico")]

    arq_html = "".join(f"<li>{a}</li>" for a in arquivos)
    ids_html = "".join(f"<li>{i}</li>" for i in ids)
    lin_html = ", ".join(linhas)

    extra = ""
    if criticos:
        extra += f"<br><b>⚠ Arquivos críticos:</b> {', '.join(sorted(set(criticos)))}"
    if dual:
        extra += f"<br><b>⚠ Requer compatibilidade dual:</b> {', '.join(dual)}"

    return (
        f"<b>Fluxo:</b> {fluxo}<br>"
        f"<b>Total de impactos:</b> {len(impactos)}<br>"
        f"<b>Complexidade predominante:</b> {max(set(i['complexidade'] for i in impactos), key=lambda c: ['Baixa','Média','Alta'].index(c) if c in ['Baixa','Média','Alta'] else 0)}<br>"
        f"{extra}<br>"
        f"<b>Arquivos afetados:</b><ul>{arq_html}</ul>"
        f"<b>Impactos:</b><ul>{ids_html}</ul>"
        f"<b>Linhas:</b> {lin_html}"
    )


# ---------------------------------------------------------------------------
# Monta hierarquia: Feature (fluxo) > PBI ([Fluxo] repo) > Task
# ---------------------------------------------------------------------------

def build_hierarchy(data: dict) -> list[dict]:
    """
    Retorna lista de Features (fluxos de negócio), cada uma com PBIs
    ([Fluxo] repo), cada PBI com Tasks por categoria técnica (DTOs, Entidades,
    SQL, etc.) + tasks fixas de encerramento.
    """
    modulo_step = {s["modulo"]: s["passo"] for s in data.get("ordem_migracao", [])}
    modulo_deps = {s["modulo"]: s.get("depende_de", []) for s in data.get("ordem_migracao", [])}
    repo_stats   = data["estatisticas"]["impactos_por_repositorio"]

    # Agrupa impactos por (fluxo, repo, area)
    grupos: dict[tuple, list] = defaultdict(list)
    for imp in data["matriz_impacto"]:
        fluxo = imp.get("fluxo") or _FLUXO_FALLBACK
        grupos[(fluxo, imp["repositorio"], imp["area"])].append(imp)

    # Monta PBIs por (fluxo, repo)
    pbis_por_fluxo_repo: dict[tuple, dict] = {}

    for (fluxo, repo, area), impactos in grupos.items():
        key = (fluxo, repo)
        if key not in pbis_por_fluxo_repo:
            step = modulo_step.get(repo, 0)
            deps = modulo_deps.get(repo, [])
            pbis_por_fluxo_repo[key] = {
                "titulo":         f"[{fluxo}] {repo}",
                "fluxo":          fluxo,
                "repositorio":    repo,
                "sprint":         f"Sprint {step} - Modulo" if step else "Sprint 0",
                "prioridade_ado": 3,
                "tags":           f"cnpj-alfanumerico; {fluxo.lower().replace(' ', '-')}",
                "depende_de":     deps,
                "areas":          [],
                "tasks":          [],
                "total_impactos": 0,
            }

        pbi = pbis_por_fluxo_repo[key]
        alta     = sum(1 for i in impactos if i["complexidade"] == "Alta")
        dual     = sum(1 for i in impactos if i.get("requer_compatibilidade_dual"))
        prio_max = min(_prio(i) for i in impactos)
        pbi["prioridade_ado"] = min(pbi["prioridade_ado"], prio_max)
        pbi["total_impactos"] += len(impactos)
        pbi["areas"].append({
            "area": area, "total": len(impactos), "alta": alta, "dual": dual,
            "rationale": _AREA_RATIONALE.get(area, ""),
        })

        # Agrupa impactos desta área por categoria de task
        por_categoria: dict[str, list] = defaultdict(list)
        for imp in impactos:
            por_categoria[_categoria(imp)].append(imp)

        step = modulo_step.get(repo, 0)
        sprint_val = f"Sprint {step} - Modulo" if step else "Sprint 0"

        for cat, cat_imps in sorted(por_categoria.items()):
            prio_max = min(_prio(i) for i in cat_imps)
            pbi["tasks"].append({
                "tipo":           "impacto",
                "id_scanner":     ", ".join(i["id"] for i in cat_imps),
                "titulo":         f"{cat} ({len(cat_imps)} impactos)",
                "descricao":      _desc_categoria(cat_imps, fluxo),
                "area":           area,
                "fluxo":          fluxo,
                "repositorio":    repo,
                "arquivo":        "",
                "linha":          "",
                "complexidade":   cat_imps[0]["complexidade"],
                "prioridade_ado": prio_max,
                "sprint":         sprint_val,
                "tags":           _tags_categoria(cat_imps),
            })

    # Adiciona tasks fixas de encerramento a cada PBI
    for pbi in pbis_por_fluxo_repo.values():
        step = modulo_step.get(pbi["repositorio"], 0)
        sprint_val = f"Sprint {step} - Modulo" if step else "Sprint 0"
        for ct in _CLOSURE_TASKS:
            desc = "<br>".join(ct["checklist"])
            pbi["tasks"].append({
                "tipo":           "encerramento",
                "id_scanner":     "",
                "titulo":         ct["titulo"],
                "descricao":      desc,
                "area":           "",
                "fluxo":          pbi["fluxo"],
                "repositorio":    pbi["repositorio"],
                "arquivo":        "",
                "linha":          "",
                "complexidade":   "",
                "prioridade_ado": 2,
                "sprint":         sprint_val,
                "tags":           f"cnpj-alfanumerico; {ct['tags']}",
            })

    # Monta descrição de cada PBI
    for pbi in pbis_por_fluxo_repo.values():
        repo  = pbi["repositorio"]
        stats = repo_stats.get(repo, {})
        deps_str = ", ".join(pbi["depende_de"]) if pbi["depende_de"] else "Nenhuma"
        areas_html = "".join(
            f"<li>{a['area']}: {a['total']} impactos ({a['alta']} Alta, {a['dual']} Dual) — {a['rationale']}</li>"
            for a in pbi["areas"]
        )
        n_impactos = sum(t["tipo"] == "impacto" for t in pbi["tasks"])
        pbi["descricao"] = (
            f"<b>Fluxo:</b> {pbi['fluxo']}<br>"
            f"<b>Repositório:</b> {repo}<br>"
            f"<b>Total de impactos:</b> {n_impactos}<br>"
            f"<b>Alta complexidade:</b> {stats.get('Alta', 0)}<br>"
            f"<b>Depende de:</b> {deps_str}<br><br>"
            f"<b>Áreas afetadas neste fluxo:</b><ul>{areas_html}</ul>"
            f"<b>Critério de aceite:</b><ul>"
            f"<li>Todos os {n_impactos} impactos resolvidos ou marcados como falso positivo</li>"
            f"<li>Testes cobrindo CNPJ alfanumérico nos componentes afetados</li>"
            f"<li>Scanner reexecutado sem ocorrências neste repositório</li>"
            f"</ul>"
        )

    # Agrupa PBIs por fluxo e monta Features
    pbis_por_fluxo: dict[str, list] = defaultdict(list)
    for (fluxo, _repo), pbi in pbis_por_fluxo_repo.items():
        pbis_por_fluxo[fluxo].append(pbi)

    # Ordena PBIs dentro de cada Feature pelo passo de migração
    for fluxo in pbis_por_fluxo:
        pbis_por_fluxo[fluxo].sort(key=lambda p: modulo_step.get(p["repositorio"], 999))

    # Monta Features ordenadas por prioridade mínima dos PBIs
    features = []
    for fluxo in sorted(pbis_por_fluxo.keys()):
        pbis = pbis_por_fluxo[fluxo]
        prio_feature = min(p["prioridade_ado"] for p in pbis)
        n_repos      = len(pbis)
        n_tasks      = sum(len(p["tasks"]) for p in pbis)
        n_impactos   = sum(p["total_impactos"] for p in pbis)
        repos_list   = ", ".join(f"<li>{p['repositorio']}</li>" for p in pbis)

        feature_desc = (
            f"<b>Fluxo de negócio:</b> {fluxo}<br>"
            f"<b>Repositórios impactados:</b> {n_repos}<br>"
            f"<b>Total de impactos:</b> {n_impactos}<br>"
            f"<b>PBIs:</b><ul>{repos_list}</ul>"
        )

        features.append({
            "titulo":         f"[CNPJ-Alfanum] {fluxo}",
            "fluxo":          fluxo,
            "prioridade_ado": prio_feature,
            "tags":           f"cnpj-alfanumerico; {fluxo.lower().replace(' ', '-')}",
            "descricao":      feature_desc,
            "pbis":           pbis,
        })

    features.sort(key=lambda f: f["prioridade_ado"])
    return features


# ---------------------------------------------------------------------------
# Dry-run
# ---------------------------------------------------------------------------

def dry_run(features: list[dict]) -> None:
    total_pbis  = sum(len(f["pbis"]) for f in features)
    total_tasks = sum(len(p["tasks"]) for f in features for p in f["pbis"])

    print("=" * 70)
    print(f"  Features (fluxos)  : {len(features)}")
    print(f"  PBIs ([Fluxo] repo): {total_pbis}")
    print(f"  Tasks              : {total_tasks}")
    print("=" * 70)
    print()

    for feat in features:
        t = sum(len(p["tasks"]) for p in feat["pbis"])
        print(f"[Feature] {feat['titulo']}  ({len(feat['pbis'])} PBIs | {t} tasks | P{feat['prioridade_ado']})")
        for pbi in feat["pbis"]:
            n_cat = sum(1 for t in pbi["tasks"] if t["tipo"] == "impacto")
            print(f"  [PBI] {pbi['titulo']}  [{n_cat} categorias + {len(_CLOSURE_TASKS)} fixas | {pbi['sprint']}]")
            if pbi["depende_de"]:
                print(f"        depende de: {', '.join(pbi['depende_de'])}")
            for task in pbi["tasks"]:
                marker = "  " if task["tipo"] == "impacto" else "  *"
                print(f"    [Task]{marker} {task['titulo']}")
        print()

    print("Use --csv para exportar ou --create para criar via API REST")


# ---------------------------------------------------------------------------
# CSV
# ---------------------------------------------------------------------------

def export_csv(features: list[dict], path: str = "ado_workitems.csv") -> None:
    fields = [
        "nivel", "tipo_wi", "titulo", "fluxo", "repositorio", "area",
        "sprint", "prioridade", "tags", "total_impactos", "pai_titulo",
        "id_scanner", "arquivo", "linha", "complexidade", "depende_de",
    ]
    rows = []

    for feat in features:
        rows.append({
            "nivel": "1-Feature", "tipo_wi": "Feature",
            "titulo": feat["titulo"], "fluxo": feat["fluxo"],
            "repositorio": "", "area": "", "sprint": "",
            "prioridade": feat["prioridade_ado"], "tags": feat["tags"],
            "total_impactos": sum(p["total_impactos"] for p in feat["pbis"]),
            "pai_titulo": "", "id_scanner": "", "arquivo": "",
            "linha": "", "complexidade": "", "depende_de": "",
        })
        for pbi in feat["pbis"]:
            rows.append({
                "nivel": "2-PBI", "tipo_wi": "Product Backlog Item",
                "titulo": pbi["titulo"], "fluxo": pbi["fluxo"],
                "repositorio": pbi["repositorio"], "area": "",
                "sprint": pbi["sprint"], "prioridade": pbi["prioridade_ado"],
                "tags": pbi["tags"], "total_impactos": pbi["total_impactos"],
                "pai_titulo": feat["titulo"], "id_scanner": "", "arquivo": "",
                "linha": "", "complexidade": "",
                "depende_de": "; ".join(f"[{pbi['fluxo']}] {d}" for d in pbi["depende_de"]),
            })
            for task in pbi["tasks"]:
                rows.append({
                    "nivel": "3-Task", "tipo_wi": "Task",
                    "titulo": task["titulo"], "fluxo": task["fluxo"],
                    "repositorio": task["repositorio"], "area": task["area"],
                    "sprint": task["sprint"], "prioridade": task["prioridade_ado"],
                    "tags": task["tags"], "total_impactos": "",
                    "pai_titulo": pbi["titulo"],
                    "id_scanner": task["id_scanner"],
                    "arquivo": task["arquivo"], "linha": task["linha"],
                    "complexidade": task["complexidade"], "depende_de": "",
                })

    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)

    total_pbis  = sum(len(f["pbis"]) for f in features)
    total_tasks = sum(len(p["tasks"]) for f in features for p in f["pbis"])
    print(f"[ok] {path}  ({len(features)} Features | {total_pbis} PBIs | {total_tasks} Tasks)")


# ---------------------------------------------------------------------------
# API REST
# ---------------------------------------------------------------------------

def _ado_headers(pat: str) -> dict:
    import base64
    token = base64.b64encode(f":{pat}".encode()).decode()
    return {"Authorization": f"Basic {token}", "Content-Type": "application/json-patch+json"}


def _create_wi(session, org: str, project: str, wi_type: str,
               titulo: str, descricao: str, prio: int, tags: str,
               sprint: str, parent_id: int | None = None) -> int | None:
    url  = f"{org}/{project}/_apis/wit/workitems/${wi_type}?api-version=7.1"
    body = [
        {"op": "add", "path": "/fields/System.Title",                   "value": titulo},
        {"op": "add", "path": "/fields/System.Description",             "value": descricao},
        {"op": "add", "path": "/fields/Microsoft.VSTS.Common.Priority", "value": prio},
    ]

    if parent_id:
        body.append({
            "op": "add", "path": "/relations/-",
            "value": {
                "rel": "System.LinkTypes.Hierarchy-Reverse",
                "url": f"{org}/_apis/wit/workItems/{parent_id}",
            }
        })
    resp = session.post(url, json=body, timeout=20)
    if resp.status_code in (200, 201):
        return resp.json().get("id")
    print(f"      ERR {resp.status_code}: {resp.text[:500]}")
    return None


def _add_dependency_link(session, org: str, from_id: int, to_id: int) -> bool:
    """Cria link 'Predecessor' de from_id → to_id (from depende de to)."""
    url  = f"{org}/_apis/wit/workitems/{from_id}?api-version=7.1"
    body = [{
        "op": "add", "path": "/relations/-",
        "value": {
            "rel": "System.LinkTypes.Dependency-Forward",
            "url": f"{org}/_apis/wit/workItems/{to_id}",
            "attributes": {"comment": "Dependência inferida pelo CNPJ Impact Scanner"},
        }
    }]
    resp = session.patch(url, json=body, timeout=20)
    return resp.status_code in (200, 201)


def create_work_items(features: list[dict]) -> None:
    if not HAS_REQUESTS:
        print("[erro] pip install requests")
        sys.exit(1)

    org     = os.environ.get("ADO_ORG", "").rstrip("/")
    project = os.environ.get("ADO_PROJECT", "")
    pat     = os.environ.get("ADO_PAT", "")
    epic_id = os.environ.get("ADO_EPIC_ID")

    if not all([org, project, pat]):
        print("[erro] Defina ADO_ORG, ADO_PROJECT e ADO_PAT")
        sys.exit(1)

    session = requests.Session()
    session.headers.update(_ado_headers(pat))

    feat_ok = feat_fail = pbi_ok = pbi_fail = task_ok = task_fail = dep_ok = dep_fail = 0

    # repo → pbi_id (por fluxo) para criar links de dependência
    pbi_ids: dict[tuple, int] = {}  # (fluxo, repo) → ado_id

    for feat in features:
        feat_id = _create_wi(
            session, org, project, "Feature",
            titulo    = feat["titulo"],
            descricao = feat["descricao"],
            prio      = feat["prioridade_ado"],
            tags      = feat["tags"],
            sprint    = "",
            parent_id = int(epic_id) if epic_id else None,
        )
        if not feat_id:
            print(f"  FAIL Feature: {feat['titulo']}")
            feat_fail += 1
            continue
        print(f"  Feature #{feat_id}  {feat['titulo']}")
        feat_ok += 1

        for pbi in feat["pbis"]:
            pbi_id = _create_wi(
                session, org, project, "Product Backlog Item",
                titulo    = pbi["titulo"],
                descricao = pbi["descricao"],
                prio      = pbi["prioridade_ado"],
                tags      = pbi["tags"],
                sprint    = pbi["sprint"],
                parent_id = feat_id,
            )
            if not pbi_id:
                print(f"    FAIL PBI: {pbi['titulo']}")
                pbi_fail += 1
                continue
            print(f"    PBI #{pbi_id}  {pbi['titulo']}  [{len(pbi['tasks'])} tasks]")
            pbi_ok += 1
            pbi_ids[(pbi["fluxo"], pbi["repositorio"])] = pbi_id

            for task in pbi["tasks"]:
                tid = _create_wi(
                    session, org, project, "Task",
                    titulo    = task["titulo"],
                    descricao = task["descricao"],
                    prio      = task["prioridade_ado"],
                    tags      = task["tags"],
                    sprint    = task["sprint"],
                    parent_id = pbi_id,
                )
                if tid:
                    task_ok += 1
                else:
                    task_fail += 1

    # Cria links de dependência entre PBIs (mesmo fluxo, repo depende de outro)
    print("\n[info] Criando links de dependência entre PBIs...")
    for feat in features:
        for pbi in feat["pbis"]:
            from_id = pbi_ids.get((pbi["fluxo"], pbi["repositorio"]))
            if not from_id:
                continue
            for dep_repo in pbi.get("depende_de", []):
                to_id = pbi_ids.get((pbi["fluxo"], dep_repo))
                if not to_id:
                    continue
                if _add_dependency_link(session, org, from_id, to_id):
                    print(f"    DEP  [{pbi['fluxo']}] {pbi['repositorio']} -> {dep_repo}")
                    dep_ok += 1
                else:
                    dep_fail += 1

    print(f"\n[ok] Features: {feat_ok} | PBIs: {pbi_ok} | Tasks: {task_ok} | Deps: {dep_ok}")
    if feat_fail or pbi_fail or task_fail or dep_fail:
        print(f"[warn] Falhas — Features: {feat_fail} | PBIs: {pbi_fail} | Tasks: {task_fail} | Deps: {dep_fail}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

_DEFAULT_JSON = Path(__file__).parent.parent / "docs" / "output" / "impacto_cnpj.json"


def main():
    src = Path(sys.argv[1]) if len(sys.argv) > 1 and not sys.argv[1].startswith("--") else _DEFAULT_JSON
    if not src.exists():
        src = Path("impacto_cnpj.json")
    if not src.exists():
        print(f"[erro] {src} nao encontrado.")
        sys.exit(1)
    mode_arg = next((a for a in sys.argv[1:] if a.startswith("--")), None)
    sys.argv = [sys.argv[0]] + ([mode_arg] if mode_arg else [])

    data     = json.loads(src.read_text(encoding="utf-8"))
    features = build_hierarchy(data)

    total_pbis  = sum(len(f["pbis"]) for f in features)
    total_tasks = sum(len(p["tasks"]) for f in features for p in f["pbis"])
    print(f"[info] {len(features)} Features (fluxos) | {total_pbis} PBIs ([Fluxo] repo) | {total_tasks} Tasks\n")

    mode = sys.argv[1] if len(sys.argv) > 1 else "--dry"

    if mode == "--csv":
        export_csv(features)
    elif mode == "--create":
        create_work_items(features)
    elif mode == "--test":
        print("[test] Criando apenas a primeira feature...\n")
        create_work_items(features[:1])
    elif mode == "--create-skip":
        skip = {"[CNPJ-Alfanum] Abertura de Conta / Onboarding PJ"}
        filtered = [f for f in features if f["titulo"] not in skip]
        print(f"[info] Pulando {len(features) - len(filtered)} feature(s) ja existentes...\n")
        create_work_items(filtered)
    else:
        dry_run(features)


if __name__ == "__main__":
    main()
