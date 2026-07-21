"""
Blind Spots Scanner — complementa o impacto_cnpj.json com findings dos pontos cegos.

Cobre os 6 PCs identificados no dashboard:
  PC-001  Aliases de campo sem a palavra 'cnpj' (taxId, documento, cpfCnpj, etc.)
  PC-002  Repos que atingiram o limite de 1000 resultados da Search API
  PC-003  Arquivos > 500KB ignorados pelo scanner principal
  PC-004  Lógica relevante em comentários TODO/FIXME
  PC-005  Repos com zero impactos que podem processar CNPJ via aliases
  PC-006  Templates de documentos PJ (contrato social, procuração, etc.)

Os findings são convertidos para o formato da matriz_impacto e INJETADOS no JSON
existente — aparecem no dashboard, ordem de migração, checklist de rollback, etc.

Uso:
    python tools/blind_spots.py [--repos-dir DIR] [--json impacto_cnpj.json]
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime

# ---------------------------------------------------------------------------
# Configuração
# ---------------------------------------------------------------------------

REPOS_DIR = os.path.join(os.path.dirname(__file__), "..", "repos")
DEFAULT_JSON = os.path.join(os.path.dirname(__file__), "..", "docs", "output", "impacto_cnpj.json")

MAX_FILE_SIZE = 500_000  # bytes — mesmo limite do scanner principal

IGNORE_DIRS = {
    "node_modules", ".git", "dist", "build", "target", ".mvn",
    "bin", "obj", "vendor", "__pycache__", ".gradle", "out",
}

# PC-001 / PC-005: aliases de campo suspeitos
_ALIAS_RE = re.compile(
    r"(?i)\b(cpf_?cnpj|nr_?doc(?:umento)?|num_?doc(?:umento)?|tax_?id|federal_?id"
    r"|doc_?number|company_?id|corporate_?id|registration_?number"
    r"|documento_?federal|legal_?entity|legal_?person|pessoa_?juridica"
    r"|cnpj_?empresa|empresa_?cnpj|cnpj_?da_?empresa)\b"
)

# PC-001: VARCHAR/CHAR(14-20) em tabelas com coluna cnpj (análise estrutural SQL)
_SQL_TABLE = re.compile(r"(?i)(CREATE|ALTER)\s+TABLE\s+(\S+)")
_SQL_ALIAS_COL = re.compile(r"(?i)^\s*(\w+)\s+(VARCHAR2?|CHAR|NVARCHAR2?)\s*\(\s*(1[0-9]|20)\s*\)")
_SQL_CNPJ_COL = re.compile(r"(?i)\bcnpj\b")

# PC-004: comentários com TODO/FIXME mencionando CNPJ
_COMMENT_CNPJ_RE = re.compile(
    r"(?i)(//|/\*|\*|#|<!--).{0,120}(todo|fixme|hack|xxx|note).{0,80}cnpj"
)
_COMMENT_CNPJ_RE2 = re.compile(
    r"(?i)(//|/\*|\*|#|<!--).{0,80}cnpj.{0,80}(todo|fixme|hack|xxx|note)"
)

# PC-006: templates de documentos PJ
_TEMPLATE_RE = re.compile(
    r"(?i)(contratoSocial|contrato_social|procuracao|procuração"
    r"|inscricaoEstadual|inscricao_estadual|inscricão_estadual"
    r"|NIRE|fichaCAD|ficha_cad|quadroSocietario|quadro_societario"
    r"|aberturaConta|abertura_conta|comprovanteAbertura|comprovante_abertura"
    r"|documentoPJ|documento_pj|fichaCliente|ficha_cliente)"
)
_TEMPLATE_EXTS = {".html", ".jrxml", ".ftl", ".vm", ".docx", ".pdf", ".xhtml", ".jsp"}

# Extensões relevantes para PC-001/PC-004/PC-005
_CODE_EXTS = {
    ".java", ".kt", ".scala", ".py", ".js", ".ts", ".tsx", ".jsx",
    ".cs", ".go", ".rb", ".php", ".rs", ".sql", ".xml", ".yml", ".yaml",
    ".json", ".properties", ".env", ".conf", ".cfg",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _walk(repo_path: str):
    """os.walk com poda de diretórios ignorados."""
    for dirpath, dirnames, filenames in os.walk(repo_path):
        dirnames[:] = [d for d in dirnames if d not in IGNORE_DIRS and not d.startswith(".")]
        yield dirpath, filenames


def _rel(abs_path: str, repo_path: str) -> str:
    return os.path.relpath(abs_path, repo_path).replace("\\", "/")


def _read(abs_path: str) -> str | None:
    try:
        with open(abs_path, encoding="utf-8", errors="replace") as f:
            return f.read()
    except OSError:
        return None


def _size(abs_path: str) -> int:
    try:
        return os.path.getsize(abs_path)
    except OSError:
        return 0


# ---------------------------------------------------------------------------
# PC-001: aliases de campo em código-fonte
# ---------------------------------------------------------------------------

def scan_pc001_aliases(repo: str, repo_path: str) -> list[dict]:
    findings = []
    for dirpath, filenames in _walk(repo_path):
        for fn in filenames:
            ext = os.path.splitext(fn)[1].lower()
            if ext not in _CODE_EXTS:
                continue
            abs_path = os.path.join(dirpath, fn)
            if _size(abs_path) > MAX_FILE_SIZE:
                continue
            content = _read(abs_path)
            if not content:
                continue
            for lineno, line in enumerate(content.splitlines(), 1):
                if _ALIAS_RE.search(line):
                    findings.append({
                        "pc": "PC-001",
                        "repo": repo,
                        "filepath": _rel(abs_path, repo_path),
                        "linha": lineno,
                        "trecho": line.strip()[:200],
                    })
    return findings


# ---------------------------------------------------------------------------
# PC-001 (SQL estrutural): VARCHAR(14-20) em tabelas com coluna cnpj
# ---------------------------------------------------------------------------

def scan_pc001_sql_structural(repo: str, repo_path: str) -> list[dict]:
    findings = []
    for dirpath, filenames in _walk(repo_path):
        for fn in filenames:
            if not fn.lower().endswith(".sql"):
                continue
            abs_path = os.path.join(dirpath, fn)
            if _size(abs_path) > MAX_FILE_SIZE:
                continue
            content = _read(abs_path)
            if not content:
                continue
            lines = content.splitlines()
            i = 0
            while i < len(lines):
                if not _SQL_TABLE.search(lines[i]):
                    i += 1
                    continue
                block_start = i
                block = []
                while i < len(lines):
                    block.append((i + 1, lines[i]))
                    if ";" in lines[i] and i > block_start:
                        break
                    i += 1
                i += 1
                block_text = "\n".join(l for _, l in block)
                if not _SQL_CNPJ_COL.search(block_text):
                    continue
                for lineno, bline in block:
                    m = _SQL_ALIAS_COL.match(bline)
                    if m and not _SQL_CNPJ_COL.search(m.group(1)):
                        findings.append({
                            "pc": "PC-001",
                            "repo": repo,
                            "filepath": _rel(abs_path, repo_path),
                            "linha": lineno,
                            "trecho": bline.strip()[:200],
                            "detalhe": f"coluna '{m.group(1)}' {m.group(2)}({m.group(3)}) em tabela com coluna cnpj",
                        })
    return findings


# ---------------------------------------------------------------------------
# PC-003: arquivos > 500KB ignorados
# ---------------------------------------------------------------------------

def scan_pc003_large_files(repo: str, repo_path: str) -> list[dict]:
    findings = []
    for dirpath, filenames in _walk(repo_path):
        for fn in filenames:
            ext = os.path.splitext(fn)[1].lower()
            if ext not in _CODE_EXTS:
                continue
            abs_path = os.path.join(dirpath, fn)
            sz = _size(abs_path)
            if sz <= MAX_FILE_SIZE:
                continue
            # Só reporta se o nome do arquivo sugere contexto de CNPJ/migração
            fn_lower = fn.lower()
            if any(k in fn_lower for k in ("cnpj", "migra", "schema", "flyway", "liquibase", "carga", "seed")):
                findings.append({
                    "pc": "PC-003",
                    "repo": repo,
                    "filepath": _rel(abs_path, repo_path),
                    "tamanho_kb": round(sz / 1024, 1),
                })
    return findings


# ---------------------------------------------------------------------------
# PC-004: TODO/FIXME em comentários mencionando CNPJ
# ---------------------------------------------------------------------------

def scan_pc004_comments(repo: str, repo_path: str) -> list[dict]:
    findings = []
    for dirpath, filenames in _walk(repo_path):
        for fn in filenames:
            ext = os.path.splitext(fn)[1].lower()
            if ext not in _CODE_EXTS:
                continue
            abs_path = os.path.join(dirpath, fn)
            if _size(abs_path) > MAX_FILE_SIZE:
                continue
            content = _read(abs_path)
            if not content:
                continue
            for lineno, line in enumerate(content.splitlines(), 1):
                if _COMMENT_CNPJ_RE.search(line) or _COMMENT_CNPJ_RE2.search(line):
                    findings.append({
                        "pc": "PC-004",
                        "repo": repo,
                        "filepath": _rel(abs_path, repo_path),
                        "linha": lineno,
                        "trecho": line.strip()[:200],
                    })
    return findings


# ---------------------------------------------------------------------------
# PC-006: templates de documentos PJ
# ---------------------------------------------------------------------------

def scan_pc006_templates(repo: str, repo_path: str) -> list[dict]:
    findings = []
    for dirpath, filenames in _walk(repo_path):
        for fn in filenames:
            ext = os.path.splitext(fn)[1].lower()
            abs_path = os.path.join(dirpath, fn)
            filepath = _rel(abs_path, repo_path)

            # Detecta pelo nome do arquivo
            if _TEMPLATE_RE.search(fn):
                findings.append({
                    "pc": "PC-006",
                    "repo": repo,
                    "filepath": filepath,
                    "detalhe": "nome do arquivo sugere template de documento PJ",
                })
                continue

            # Detecta pelo conteúdo (apenas extensões de template)
            if ext not in _TEMPLATE_EXTS:
                continue
            sz = _size(abs_path)
            if sz > MAX_FILE_SIZE:
                continue
            content = _read(abs_path)
            if content and _TEMPLATE_RE.search(content):
                # Encontra a primeira linha com match para contexto
                for lineno, line in enumerate(content.splitlines(), 1):
                    if _TEMPLATE_RE.search(line):
                        findings.append({
                            "pc": "PC-006",
                            "repo": repo,
                            "filepath": filepath,
                            "linha": lineno,
                            "trecho": line.strip()[:200],
                        })
                        break
    return findings


# ---------------------------------------------------------------------------
# PC-002 / PC-005: repos que atingiram limite da Search API ou têm zero impactos
# Detectados a partir do JSON de saída do scanner principal
# ---------------------------------------------------------------------------

def load_scan_json(json_path: str) -> dict:
    if not os.path.exists(json_path):
        print(f"[ERRO] JSON não encontrado: {json_path}", file=sys.stderr)
        sys.exit(1)
    with open(json_path, encoding="utf-8") as f:
        return json.load(f)


def get_repos_at_search_limit(scan_data: dict) -> list[str]:
    """Repos que atingiram 1000 resultados na Search API."""
    stats = scan_data.get("estatisticas", {}).get("candidatos_por_repositorio", {})
    return [r for r, s in stats.items() if s.get("candidatos", 0) >= 1000]


def get_repos_zero_impact(scan_data: dict, repos_dir: str) -> list[str]:
    """Repos com zero impactos que existem localmente."""
    impacted = {m["repositorio"] for m in scan_data.get("matriz_impacto", [])}
    if not os.path.isdir(repos_dir):
        return []
    all_local = {d for d in os.listdir(repos_dir) if os.path.isdir(os.path.join(repos_dir, d))}
    return sorted(all_local - impacted)


# ---------------------------------------------------------------------------
# Conversão para formato matriz_impacto
# ---------------------------------------------------------------------------

# Mapeamento PC → (área, complexidade, descrição)
_PC_META = {
    "PC-001-alias": (
        "Backend", "Média",
        "Campo com alias de CNPJ (taxId, documento, cpfCnpj, etc.) detectado por varredura local. "
        "Pode armazenar CNPJ sem usar a palavra 'cnpj' no nome — invisível para a Search API do GitHub.",
    ),
    "PC-001-sql": (
        "Banco de Dados", "Alta",
        "Coluna com alias de CNPJ (VARCHAR 14-20) em tabela que já possui coluna 'cnpj'. "
        "Detectado por análise estrutural SQL local — fora do escopo da Search API.",
    ),
    "PC-003": (
        "Banco de Dados", "Alta",
        "Arquivo SQL > 500KB ignorado pelo scanner principal. Pode conter scripts de carga ou migration "
        "com CNPJ em formato numérico. Requer revisão manual.",
    ),
    "PC-004": (
        "Backend", "Baixa",
        "Comentário TODO/FIXME menciona CNPJ. Pode indicar lógica pendente de migração ou "
        "decisão de design que ainda não foi implementada.",
    ),
    "PC-006": (
        "Pessoa Jurídica/PJ", "Alta",
        "Template de documento PJ (contrato social, procuração, ficha cadastral, abertura de conta) "
        "detectado por varredura local. Pode conter CNPJ em formato numérico hardcoded.",
    ),
}


def _to_impacto(finding: dict, next_id: int) -> dict:
    """Converte um finding do blind_spots para o formato da matriz_impacto."""
    pc_key = finding["_pc_key"]
    area, complexidade, descricao = _PC_META[pc_key]
    prioridade = "P1" if complexidade == "Alta" else ("P2" if complexidade == "Média" else "P3")
    return {
        "id": f"BS-{next_id:04d}",
        "area": area,
        "repositorio": finding["repo"],
        "componente": finding["filepath"],
        "descricao_impacto": descricao,
        "complexidade": complexidade,
        "prioridade": prioridade,
        "status": "pendente",
        "responsavel": None,
        "observacao": finding.get("detalhe", ""),
        "chamadores_estimados": 0,
        "arquivo_critico": False,
        "requer_compatibilidade_dual": area in ("API/Contrato", "Integrações"),
        "motivo_compatibilidade_dual": None,
        "evidencia": {
            "arquivo": finding["filepath"],
            "linha": finding.get("linha", 0),
            "trecho_codigo": finding.get("trecho", finding.get("detalhe", ""))[:200],
        },
        "observacoes": f"Ponto cego {finding['pc']} | varredura local blind_spots.py",
        "_blind_spot": True,
    }


# ---------------------------------------------------------------------------
# Orquestrador
# ---------------------------------------------------------------------------

def run(repos_dir: str, json_path: str, repos_filter: list[str] | None = None) -> dict:
    """Varre repos locais, converte findings e injeta no JSON existente. Retorna o JSON atualizado."""
    scan_data = load_scan_json(json_path)
    repos_limit = set(get_repos_at_search_limit(scan_data))
    repos_zero = set(get_repos_zero_impact(scan_data, repos_dir))

    if not os.path.isdir(repos_dir):
        print(f"[ERRO] Diretório de repos não encontrado: {repos_dir}", file=sys.stderr)
        sys.exit(1)

    all_repos = sorted(
        d for d in os.listdir(repos_dir)
        if os.path.isdir(os.path.join(repos_dir, d)) and not d.startswith(".")
    )
    if repos_filter:
        all_repos = [r for r in all_repos if r in repos_filter]

    # Coleta findings brutos
    raw: list[dict] = []
    pc002_repos: list[str] = []
    pc005_repos: list[str] = []

    total = len(all_repos)
    for idx, repo in enumerate(all_repos, 1):
        print(f"  [{idx:3d}/{total}] {repo}", end="\r", flush=True)
        repo_path = os.path.join(repos_dir, repo)

        for f in scan_pc001_aliases(repo, repo_path):
            raw.append({**f, "_pc_key": "PC-001-alias"})
        for f in scan_pc001_sql_structural(repo, repo_path):
            raw.append({**f, "_pc_key": "PC-001-sql"})
        for f in scan_pc003_large_files(repo, repo_path):
            raw.append({**f, "_pc_key": "PC-003"})
        for f in scan_pc004_comments(repo, repo_path):
            raw.append({**f, "_pc_key": "PC-004"})
        for f in scan_pc006_templates(repo, repo_path):
            raw.append({**f, "_pc_key": "PC-006"})

        if repo in repos_limit:
            pc002_repos.append(repo)
        if repo in repos_zero and any(f["repo"] == repo for f in raw):
            pc005_repos.append(repo)

    print()  # newline após o \r

    # Deduplica por (repo, filepath, linha) — não adiciona o que já está na matriz
    existing_keys = {
        (m["repositorio"], m["evidencia"]["arquivo"], m["evidencia"]["linha"])
        for m in scan_data.get("matriz_impacto", [])
    }
    deduped = [
        f for f in raw
        if (f["repo"], f["filepath"], f.get("linha", 0)) not in existing_keys
    ]

    # Converte para formato matriz_impacto
    next_id = len(scan_data.get("matriz_impacto", [])) + 1
    novos_impactos = [_to_impacto(f, next_id + i) for i, f in enumerate(deduped)]

    # Injeta no JSON
    scan_data["matriz_impacto"].extend(novos_impactos)

    # Atualiza estatísticas
    stats = scan_data["estatisticas"]
    stats["total_impactos_encontrados"] = len(scan_data["matriz_impacto"])
    for imp in novos_impactos:
        area = imp["area"]
        stats["impactos_por_area"][area] = stats["impactos_por_area"].get(area, 0) + 1
        compl = imp["complexidade"]
        stats["impactos_por_complexidade"][compl] = stats["impactos_por_complexidade"].get(compl, 0) + 1
        repo = imp["repositorio"]
        por_repo = stats.setdefault("impactos_por_repositorio", {})
        if repo not in por_repo:
            por_repo[repo] = {"total": 0, "Alta": 0, "Média": 0, "Baixa": 0, "areas": []}
        por_repo[repo]["total"] += 1
        por_repo[repo][compl] += 1
        if area not in por_repo[repo]["areas"]:
            por_repo[repo]["areas"].append(area)

    # Atualiza PC-002 e PC-005 nos pontos_cegos do JSON
    cobertura = scan_data.setdefault("cobertura", {})
    if pc002_repos:
        cobertura["repos_search_limit"] = sorted(set(cobertura.get("repos_search_limit", []) + pc002_repos))
    if pc005_repos:
        cobertura["repos_zero_com_aliases"] = sorted(set(cobertura.get("repos_zero_com_aliases", []) + pc005_repos))

    scan_data["blind_spots_aplicados"] = {
        "gerado_em": datetime.now().isoformat(),
        "repos_varridos": len(all_repos),
        "novos_impactos": len(novos_impactos),
        "pc002_repos": pc002_repos,
        "pc005_repos": pc005_repos,
        "por_pc": {
            pc: sum(1 for f in deduped if f["pc"] == pc)
            for pc in ("PC-001", "PC-003", "PC-004", "PC-006")
        },
    }

    return scan_data


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    p = argparse.ArgumentParser(description="Blind Spots Scanner — injeta pontos cegos no impacto_cnpj.json")
    p.add_argument("--repos-dir", default=REPOS_DIR, help="Diretório com repos clonados (padrão: repos/)")
    p.add_argument("--json", default=DEFAULT_JSON, metavar="FILE", help="JSON do scanner principal (leitura e escrita)")
    p.add_argument("-r", "--repos", nargs="+", help="Filtrar repos específicos")
    args = p.parse_args()

    json_path = os.path.abspath(args.json)
    print(f"\nBlind Spots Scanner")
    print(f"Repos: {os.path.abspath(args.repos_dir)}")
    print(f"JSON: {json_path}\n")

    result = run(
        repos_dir=os.path.abspath(args.repos_dir),
        json_path=json_path,
        repos_filter=args.repos,
    )

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    bs = result["blind_spots_aplicados"]
    print(f"Novos impactos injetados: {bs['novos_impactos']}")
    for pc, count in sorted(bs["por_pc"].items()):
        if count:
            print(f"  {pc}: {count}")
    if bs["pc002_repos"]:
        print(f"  PC-002 (search limit): {bs['pc002_repos']}")
    if bs["pc005_repos"]:
        print(f"  PC-005 (zero impacto + aliases): {len(bs['pc005_repos'])} repos")
    print(f"\nTotal impactos no JSON: {result['estatisticas']['total_impactos_encontrados']}")
    print(f"Salvo em: {json_path}")


if __name__ == "__main__":
    main()
