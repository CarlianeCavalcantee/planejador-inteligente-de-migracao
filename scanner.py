"""
CNPJ Impact Scanner — entry point.
Orquestra: config → cache → github_client (async) → engine → output.
"""

import argparse
import asyncio
import json
import logging
import logging.config
import os
import sys
from datetime import datetime, timezone, timedelta

# Garante UTF-8 no stdout/stderr no Windows (cp1252 nao suporta setas/checkmarks)
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
if sys.stderr.encoding and sys.stderr.encoding.lower() != "utf-8":
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]

from dotenv import load_dotenv

import core.cache as cache_mod
from core.config import load_config, area_priority, get_checkpoint_file, get_titulo
from core.engine import process_repo
from core.flow import repos_for_flow
from core.github_client import list_org_repos, scan_repo_data, audit_alias_coverage, init_token_pool
from core.local_client import list_local_repos, scan_repo_local
from core.output import build_output, generate_markdown

load_dotenv()

# Resolvido após load_config — ver main()


def _setup_logging(level: str = "INFO", bridge=None) -> None:
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s", datefmt="%H:%M:%S")
    if bridge is not None:
        from core.ui import BridgeLogHandler
        handler = BridgeLogHandler(bridge)
    else:
        handler = logging.StreamHandler()
    handler.setFormatter(fmt)
    logging.root.setLevel(getattr(logging, level.upper(), logging.INFO))
    logging.root.handlers = [handler]


log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Checkpoint (resume)
# ---------------------------------------------------------------------------

def _load_checkpoint() -> dict:
    if os.path.exists(CHECKPOINT_FILE):
        try:
            with open(CHECKPOINT_FILE, encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    return {"done": [], "impacts": []}


def _save_checkpoint(done: list[str], impacts: list[dict], running: list[str] | None = None, repo_stats: dict | None = None) -> None:
    serializable = []
    for imp in impacts:
        rule = imp.get("_rule", {})
        entry = {k: v for k, v in imp.items() if k != "_rule"}
        entry.setdefault("area", rule.get("area", ""))
        entry.setdefault("complexidade", rule.get("complexidade", ""))
        serializable.append(entry)
    os.makedirs(os.path.dirname(CHECKPOINT_FILE), exist_ok=True)
    with open(CHECKPOINT_FILE, "w", encoding="utf-8") as f:
        json.dump({
            "done": done,
            "impacts": serializable,
            "running": running or [],
            "repo_stats": repo_stats or {},
        }, f, ensure_ascii=False)


def _clear_checkpoint() -> None:
    if os.path.exists(CHECKPOINT_FILE):
        os.remove(CHECKPOINT_FILE)


# ---------------------------------------------------------------------------
# Orquestrador async
# ---------------------------------------------------------------------------

async def _scan_all(org: str, repos: list[str], cfg: dict, disk_cache: dict,
                    done: list[str], prior_impacts: list[dict],
                    repo_stats: dict, include_large: bool = False,
                    scan_aliases: bool = False,
                    concurrency: int = 4,
                    local_dir: str | None = None,
                    branch: str | None = None,
                    bridge=None) -> list[dict]:
    priority = area_priority(cfg)
    all_impacts = list(prior_impacts)
    done_set = set(done)
    pending = [r for r in repos if r not in done_set]
    lock = asyncio.Lock()

    repo_queue: asyncio.Queue = asyncio.Queue()
    for r in pending:
        repo_queue.put_nowait(r)

    async def _worker(slot_idx: int) -> None:
        if slot_idx > 0 and not local_dir:
            await asyncio.sleep(slot_idx * 2)  # escalonamento só no modo API
        while True:
            try:
                repo = repo_queue.get_nowait()
            except asyncio.QueueEmpty:
                break

            if bridge:
                bridge.repo_started(repo, slot_idx + 1)
            else:
                print(f"  -> slot {slot_idx + 1} > {repo}")

            try:
                if local_dir:
                    loop = asyncio.get_event_loop()
                    candidates, content_map = await loop.run_in_executor(
                        None, scan_repo_local,
                        repo, local_dir, cfg["ignore_paths"], cfg["regras"],
                        include_large, bridge,
                    )
                    await asyncio.sleep(0)  # cede o event loop para a UI renderizar
                else:
                    candidates, content_map = await scan_repo_data(
                        org, repo,
                        cfg["ignore_paths"],
                        cfg["regras"],
                        disk_cache,
                        include_large=include_large,
                        scan_aliases=scan_aliases,
                        branch=branch,
                        bridge=bridge,
                    )
                impacts = process_repo(repo, candidates, content_map, priority, cfg)
                stats = {
                    "candidatos": len(candidates),
                    "impactos": len(impacts),
                    "taxa_conversao": round(len(impacts) / len(candidates), 2) if candidates else 0.0,
                }
                if bridge:
                    bridge.repo_done(repo, len(candidates), len(impacts))
                    bridge.add_impacts(impacts)
                else:
                    print(f"  OK {repo}: {len(candidates)} candidatos -> {len(impacts)} impactos")
            except Exception as e:
                impacts = []
                stats = {"candidatos": 0, "impactos": 0, "erro": str(e)}
                if bridge:
                    bridge.repo_done(repo, 0, 0, error=str(e))
                else:
                    print(f"  ERRO {repo}: {e}")
                log.exception("Erro ao processar repo '%s'", repo)

            async with lock:
                all_impacts.extend(impacts)
                repo_stats[repo] = stats
                done.append(repo)
                running_now = [r for r in pending if r not in set(done)]
                _save_checkpoint(done, all_impacts, running_now, repo_stats)

    await asyncio.gather(*[_worker(i) for i in range(concurrency)])
    return all_impacts


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args():
    p = argparse.ArgumentParser(description="Impact Scanner")
    p.add_argument("-c", "--config", default="scanner-config.yaml")
    p.add_argument("-o", "--org", help="Organização GitHub (sobrescreve config)")
    p.add_argument("-r", "--repos", nargs="+", help="Repositórios específicos")
    p.add_argument("--repos-file", metavar="FILE", help="Arquivo com lista de repos a escanear (um por linha)")
    p.add_argument("--exclude-repos-file", metavar="FILE", help="Arquivo com lista de repos a excluir (um por linha)")
    p.add_argument("-b", "--batch-size", type=int, help="Tamanho do lote (ignorado — async processa tudo)")
    p.add_argument("--json-only", action="store_true")
    p.add_argument("--md-only", action="store_true")
    p.add_argument("--resume", action="store_true", help="Retoma execução anterior do checkpoint")
    p.add_argument("--clear-cache", action="store_true", help="Limpa cache de conteúdo e checkpoint antes de rodar")
    p.add_argument("--audit-aliases", action="store_true", help="Audita aliases de CNPJ em repos sem impacto (lento — usa Search API)")
    p.add_argument("--scan-aliases", action="store_true", help="Inclui busca por aliases de campo (taxId, documento, cpfCnpj...) em TODOS os repos durante o scan principal")
    p.add_argument("--concurrency", type=int, default=2,
                   help="Repos processados em paralelo (default: 2 para API, recomendado 8+ para --local)")
    p.add_argument("--include-large-files", action="store_true", help="Baixa arquivos > 500KB via Blob API (mais lento)")
    p.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"], help="Nível de log (padrão: INFO)")
    p.add_argument("--no-ui", action="store_true", help="Desativa a TUI e usa saída de texto simples")
    p.add_argument("--local", metavar="DIR", help="Usa repos clonados localmente em DIR em vez da GitHub API")
    p.add_argument("--branch", metavar="BRANCH", help="Branch a escanear (padrão: branch default do repo; ignorado com --local)")
    p.add_argument("--flow", metavar="FLOW_ID", help="Escaneia apenas os repos do fluxo definido em flows: no config")
    return p.parse_args()


# ---------------------------------------------------------------------------
# Nomes de saída
# ---------------------------------------------------------------------------

def _resolve_output_names(args, cfg: dict) -> tuple[str, str, str]:
    """
    Retorna (json_path, md_path, docx_path).
    - Scan global (sem -r): usa os nomes do config (impacto_cnpj.*)
    - Scan de repo(s) específico(s): deriva o nome do(s) repo(s)
      Ex: -r backoffice          → scan_backoffice.*
          -r ms-pix ms-boleto    → scan_ms-pix_ms-boleto.*
          -r repo1 repo2 repo3 + mais → scan_repo1_repo2_+2.*
    """
    if not args.repos:
        base_json  = cfg.get("output_file",     "impacto_cnpj.json")
        base_md    = cfg.get("output_markdown", "impacto_cnpj.md")
        base_docx  = os.path.splitext(base_json)[0] + ".docx"
        return base_json, base_md, base_docx

    repos = args.repos
    if len(repos) <= 2:
        slug = "_".join(repos)
    else:
        slug = "_".join(repos[:2]) + f"_+{len(repos)-2}"

    # Sanitizar para nome de arquivo seguro
    slug = slug.replace("/", "-").replace("\\", "-")
    prefix = f"docs/scans/scan_{slug}"
    return f"{prefix}.json", f"{prefix}.md", f"{prefix}.docx"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Subcomando: validate-flow
# ---------------------------------------------------------------------------

def _cmd_migrate(argv: list[str]) -> None:
    from migrate.cli import main as migrate_main
    sys.argv = ["cnpj-migrate"] + argv
    migrate_main()


def _cmd_validate_flow(argv: list[str]) -> None:
    import argparse as _ap

    p = _ap.ArgumentParser(
        prog="scanner.py validate-flow",
        description="Valida se um fluxo/repo esta pronto para CNPJ alfanumerico.",
    )
    p.add_argument("-c", "--config", default="scanner-config.yaml")
    p.add_argument("-r", "--repo", metavar="REPO",
                   help="Nome do repo (clona da org) ou path local (ex: repos/api-adesao)")
    p.add_argument("--branch", metavar="BRANCH",
                   help="Branch a clonar/checar antes de escanear (so com -r)")
    p.add_argument("--flow", metavar="FLOW_ID",
                   help="Filtra arquivos do fluxo no modo -r; seleciona repos no modo fluxo completo")
    p.add_argument("--local", metavar="DIR",
                   help="Dir com repos clonados para re-scan do fluxo completo")
    p.add_argument("--scan-json", metavar="FILE",
                   help="JSON de scan alternativo (modo fluxo sem --local)")
    args = p.parse_args(argv)

    cfg = load_config(args.config)

    # ── Modo repo: -r fornecido ─────────────────────────────────────────────
    if args.repo:
        from core.flow_validator import validate_repo, print_validation_result
        from core.local_client import scan_repo_local

        repo_path = args.repo
        repos_dir = "repos"

        # Resolve o path: se não existe como diretório, tenta repos/<nome>
        if not os.path.isdir(repo_path):
            candidate = os.path.join(repos_dir, repo_path)
            if os.path.isdir(candidate):
                # já clonado em repos/ — usa direto, só faz checkout se --branch
                repo_path = candidate
                if args.branch:
                    import subprocess
                    r = subprocess.run(["git", "-C", repo_path, "checkout", args.branch],
                                       capture_output=True, text=True)
                    if r.returncode != 0:
                        print(f"Falha ao fazer checkout de '{args.branch}': {r.stderr.strip()}")
                        sys.exit(1)
                    print(f"Branch: {args.branch}")
            else:
                # não existe localmente — clona da org
                token = os.getenv("GITHUB_TOKEN")
                if not token:
                    print("GITHUB_TOKEN nao definido — necessario para clonar o repo.")
                    sys.exit(1)
                org = cfg["github_org"]
                repo_name = repo_path
                repo_path = os.path.join(repos_dir, repo_name)
                from scripts.clone_repos import clone_or_update
                print(f"Clonando {org}/{repo_name}" + (f" @ {args.branch}" if args.branch else "") + "...")
                ok = clone_or_update(repo_name, org, token, repos_dir,
                                     update=False, branch=args.branch)
                if not ok:
                    print(f"Falha ao clonar {repo_name}.")
                    sys.exit(1)
        elif args.branch:
            # path explícito existente + --branch
            import subprocess
            r = subprocess.run(["git", "-C", repo_path, "checkout", args.branch],
                               capture_output=True, text=True)
            if r.returncode != 0:
                print(f"Falha ao fazer checkout de '{args.branch}': {r.stderr.strip()}")
                sys.exit(1)
            print(f"Branch: {args.branch}")

        result = validate_repo(repo_path, cfg, flow_id=args.flow)

        local_dir = os.path.dirname(os.path.normpath(repo_path)) or "."
        repo_name = os.path.basename(os.path.normpath(repo_path))
        try:
            cands, _ = scan_repo_local(repo_name, local_dir, cfg["ignore_paths"], cfg["regras"])
            files_scanned = len({fp for fp, _, _ in cands})
        except Exception:
            files_scanned = 0

        print_validation_result(result, files_scanned=files_scanned)
        sys.exit(0 if result.status == "APROVADO" else 1)

    # ── Modo fluxo completo: --flow obrigatorio ─────────────────────────────
    if not args.flow:
        print("Informe -r <repo> para validar um repositorio, ou --flow <id> para validar um fluxo completo.")
        sys.exit(1)

    from core.flow_validator import validate_flow_from_json, validate_flow_local, print_validation_result

    if args.local:
        result = validate_flow_local(args.flow, args.local, cfg)
    else:
        scan_file = args.scan_json or cfg.get("output_file", "impacto_cnpj.json")
        if not os.path.exists(scan_file):
            print(f"Arquivo de scan nao encontrado: {scan_file}")
            sys.exit(1)
        print(f"Usando scan: {scan_file}")
        with open(scan_file, encoding="utf-8") as f:
            scan_json = json.load(f)
        result = validate_flow_from_json(args.flow, scan_json, cfg)

    if result is None:
        flows = list((cfg.get("flows") or {}).keys())
        print(f"Fluxo '{args.flow}' nao encontrado no config.")
        if flows:
            print(f"Fluxos disponiveis: {', '.join(flows)}")
        sys.exit(1)

    print_validation_result(result)
    sys.exit(0 if result.status == "APROVADO" else 1)


def main():
    # Subcomando validate-flow interceptado antes do argparse normal
    if len(sys.argv) >= 3 and sys.argv[1] == "validate-flow":
        _cmd_validate_flow(sys.argv[2:])
        return

    args = parse_args()

    cfg = load_config(args.config)
    org = args.org or cfg["github_org"]
    global CHECKPOINT_FILE
    CHECKPOINT_FILE = get_checkpoint_file(cfg)

    if args.local:
        pool = None
        effective_concurrency = args.concurrency if args.concurrency != 2 else 8
    else:
        if not os.getenv("GITHUB_TOKEN"):
            logging.basicConfig()
            logging.error("GITHUB_TOKEN não definido.")
            sys.exit(1)
        pool = init_token_pool()
        effective_concurrency = min(args.concurrency, pool.size)

    if args.clear_cache:
        _clear_checkpoint()
        if os.path.exists(cache_mod.CACHE_FILE):
            os.remove(cache_mod.CACHE_FILE)

    if args.repos_file:
        try:
            with open(args.repos_file, encoding="utf-8") as f:
                repos = [line.strip() for line in f if line.strip() and not line.startswith("#")]
            log.info("%d repos carregados de %s", len(repos), args.repos_file)
        except OSError as e:
            log.error("Não foi possível ler %s: %s", args.repos_file, e)
            sys.exit(1)
    elif args.flow:
        repos = repos_for_flow(args.flow, cfg)
        if not repos:
            log.error("Fluxo '%s' não encontrado ou sem repos no config.", args.flow)
            sys.exit(1)
        log.info("Fluxo '%s': %d repos — %s", args.flow, len(repos), repos)
    elif args.repos:
        repos = args.repos
    elif cfg.get("repositorios"):
        repos = cfg["repositorios"]
    elif args.local:
        _setup_logging(args.log_level)
        repos = list_local_repos(args.local)
        log.info("%d repos encontrados em '%s'", len(repos), args.local)
    else:
        # listing precisa de logging básico antes da UI subir
        _setup_logging(args.log_level)
        log.info("Listando repositórios de '%s'...", org)
        repos = asyncio.run(list_org_repos(org))

    if args.exclude_repos_file:
        try:
            with open(args.exclude_repos_file, encoding="utf-8") as f:
                excluded = {line.strip() for line in f if line.strip() and not line.startswith("#")}
            repos = [r for r in repos if r not in excluded]
            log.info("Excluídos %d repos via %s", len(excluded), args.exclude_repos_file)
        except OSError as e:
            log.error("Não foi possível ler %s: %s", args.exclude_repos_file, e)
            sys.exit(1)

    if not repos:
        log.error("Nenhum repositório encontrado.")
        sys.exit(1)

    checkpoint = _load_checkpoint() if args.resume else {"done": [], "impacts": []}
    done: list[str] = checkpoint["done"]
    prior_impacts: list[dict] = checkpoint["impacts"]
    disk_cache = cache_mod.load_cache()
    out_json, out_md, _out_docx = _resolve_output_names(args, cfg)
    repo_stats: dict = {}

    # ------------------------------------------------------------------
    # Modo UI (Textual)
    # ------------------------------------------------------------------
    if not args.no_ui:
        try:
            from core.ui import ScannerUI, ScannerBridge

            if args.local:
                # Modo local: scan em processo filho, UI monitora checkpoint
                cmd = [
                    sys.executable, __file__,
                    "--local", args.local,
                    "--no-ui",
                    "--concurrency", str(effective_concurrency),
                    "--log-level", args.log_level,
                ]
                if args.include_large_files:
                    cmd.append("--include-large-files")
                if args.repos:
                    cmd += ["-r"] + args.repos

                ui_app = ScannerUI(
                    repos=repos, org=org, scan_fn=None,
                    child_cmd=cmd, checkpoint_file=CHECKPOINT_FILE,
                )
                _setup_logging(args.log_level)
                ui_app.run()
                return
            else:
                # Modo API: scan como worker async dentro do Textual
                async def _scan_fn():
                    raw = await _scan_all(
                        org, repos, cfg, disk_cache, done, prior_impacts, repo_stats,
                        include_large=args.include_large_files,
                        scan_aliases=args.scan_aliases,
                        concurrency=effective_concurrency,
                        local_dir=None,
                        branch=args.branch,
                        bridge=_ui_bridge,
                    )
                    cache_mod.save_cache(disk_cache)
                    _clear_checkpoint()
                    output = build_output(raw, cfg, repos, repo_stats)
                    _finish(args, output, out_json, out_md, _ui_bridge)

                ui_app = ScannerUI(repos=repos, org=org, scan_fn=_scan_fn)
                _ui_bridge = ScannerBridge(ui_app)
                _setup_logging(args.log_level, bridge=_ui_bridge)
                ui_app.run()
                return
        except ImportError:
            pass

    # ------------------------------------------------------------------
    # Modo texto simples (--no-ui ou textual não instalado)
    # ------------------------------------------------------------------
    _setup_logging(args.log_level)
    print(f"\n{'#'*60}")
    titulo = get_titulo(cfg) if 'cfg' in dir() else "Impact Scanner"
    print(f"# {titulo}")
    print(f"# Org: {org} | Repos: {len(repos)} | Regras: {len(cfg['regras'])}")
    print(f"# Modo: {'local' if args.local else f'GitHub API ({pool.size} token(s))'} | Concorrência: {effective_concurrency} repos simultâneos")
    print(f"{'#'*60}\n")

    async def _run_plain():
        raw = await _scan_all(
            org, repos, cfg, disk_cache, done, prior_impacts, repo_stats,
            include_large=args.include_large_files,
            scan_aliases=args.scan_aliases,
            concurrency=effective_concurrency,
            local_dir=args.local,
            branch=args.branch,
            bridge=None,
        )
        cache_mod.save_cache(disk_cache)
        _clear_checkpoint()
        output = build_output(raw, cfg, repos, repo_stats)
        _finish(args, output, out_json, out_md, bridge=None)

    asyncio.run(_run_plain())


def _finish(args, output: dict, out_json: str, out_md: str, bridge) -> None:
    # Auditoria de aliases em repos sem impacto (opcional)
    repos_sem_impacto = output["cobertura"]["repositorios_sem_impacto"]
    if args.audit_aliases and repos_sem_impacto:
        log.info("Auditando aliases em %d repos sem impacto...", len(repos_sem_impacto))
    elif repos_sem_impacto:
        output["cobertura"]["repos_sem_impacto_com_aliases"] = {}

    if not args.md_only:
        with open(out_json, "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
        log.info("JSON: %s (%d impactos)", out_json, output["estatisticas"]["total_impactos_encontrados"])

    if not args.json_only:
        with open(out_md, "w", encoding="utf-8") as f:
            f.write(generate_markdown(output))
        log.info("Markdown: %s", out_md)

    total = output["estatisticas"]["total_impactos_encontrados"]
    if bridge:
        bridge.scan_complete(total, out_json)
    else:
        print(f"\n{'='*60}")
        print(f"OK CONCLUIDO -- {total} impactos")
        for area, count in sorted(output["estatisticas"]["impactos_por_area"].items()):
            print(f"   . {area}: {count}")
        print(f"Saídas: {out_json} | {out_md}")
        print(f"{'='*60}")


if __name__ == "__main__":
    main()
