"""
clone_repos.py — clona ou atualiza todos os repos da org BScash localmente.

Uso:
    python clone_repos.py                        # clona todos os repos da org
    python clone_repos.py -r repo1 repo2         # repos específicos
    python clone_repos.py --update               # git pull nos já clonados
    python clone_repos.py -d caminho/alternativo # diretório de destino
"""

import argparse
import asyncio
import logging
import os
import subprocess
import sys

from dotenv import load_dotenv

load_dotenv()

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")

DEFAULT_REPOS_DIR = "repos"


def _run(cmd: list[str], cwd: str | None = None) -> tuple[int, str]:
    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    return result.returncode, (result.stdout + result.stderr).strip()


def clone_or_update(repo: str, org: str, token: str, repos_dir: str, update: bool, branch: str | None = None) -> bool:
    dest = os.path.join(repos_dir, repo)
    url = f"https://{token}@github.com/{org}/{repo}.git"

    if os.path.isdir(os.path.join(dest, ".git")):
        if not update:
            log.info("%-40s já clonado (use --update para atualizar)", repo)
            return True
        log.info("%-40s atualizando...", repo)
        code, out = _run(["git", "pull", "--depth=1", "--rebase"], cwd=dest)
    else:
        log.info("%-40s clonando...", repo)
        os.makedirs(repos_dir, exist_ok=True)
        cmd = ["git", "clone", "--depth=1", "--single-branch"]
        if branch:
            cmd += ["--branch", branch]
        cmd += [url, dest]
        code, out = _run(cmd)

    if code != 0:
        log.error("%-40s ERRO: %s", repo, out[:200])
        return False
    return True


async def _clone_all(repos: list[str], org: str, token: str, repos_dir: str, update: bool, concurrency: int, branch: str | None = None) -> None:
    sem = asyncio.Semaphore(concurrency)
    loop = asyncio.get_event_loop()

    async def _task(repo: str) -> None:
        async with sem:
            await loop.run_in_executor(None, clone_or_update, repo, org, token, repos_dir, update, branch)

    await asyncio.gather(*[_task(r) for r in repos])


def main() -> None:
    p = argparse.ArgumentParser(description="Clona/atualiza repos da org para scan local")
    p.add_argument("-c", "--config", default="scanner-config.json")
    p.add_argument("-o", "--org", help="Organização GitHub (sobrescreve config)")
    p.add_argument("-r", "--repos", nargs="+", help="Repos específicos")
    p.add_argument("-d", "--dir", default=DEFAULT_REPOS_DIR, help=f"Diretório de destino (padrão: {DEFAULT_REPOS_DIR})")
    p.add_argument("--update", action="store_true", help="Faz git pull nos repos já clonados")
    p.add_argument("--branch", metavar="BRANCH", help="Branch específica a clonar (padrão: branch default do repo)")
    p.add_argument("--concurrency", type=int, default=8, help="Clones em paralelo (padrão: 8)")
    args = p.parse_args()

    token = os.getenv("GITHUB_TOKEN")
    if not token:
        log.error("GITHUB_TOKEN não definido.")
        sys.exit(1)

    import json
    with open(args.config, encoding="utf-8") as f:
        cfg = json.load(f)

    org = args.org or cfg["github_org"]

    if args.repos:
        repos = args.repos
    elif cfg.get("repositorios"):
        repos = cfg["repositorios"]
    else:
        # Lista via API
        import asyncio as _asyncio
        from core.github_client import list_org_repos, init_token_pool
        init_token_pool()
        repos = _asyncio.run(list_org_repos(org))
        log.info("%d repos encontrados na org '%s'", len(repos), org)

    log.info("Clonando %d repos em '%s' (concorrência: %d)...", len(repos), args.dir, args.concurrency)
    asyncio.run(_clone_all(repos, org, token, args.dir, args.update, args.concurrency, branch=args.branch))

    # Resumo
    clonados = sum(1 for r in repos if os.path.isdir(os.path.join(args.dir, r, ".git")))
    log.info("Concluído: %d/%d repos disponíveis em '%s'", clonados, len(repos), args.dir)


if __name__ == "__main__":
    main()
