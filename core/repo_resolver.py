"""
Resolucao de repositorio local e troca de branch.

Permite informar apenas o nome do projeto (ex: api-cobrancaterceiro) e localizar
o clone em qualquer raiz conhecida: 'repos/' do proprio scanner, raizes vindas do
config/env (`local_repos_dirs` / LOCAL_REPOS_DIRS) e o diretorio que contem o
scanner (workspace com os projetos clonados lado a lado).
"""

from __future__ import annotations

import difflib
import os
import re
import subprocess

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_ROOT_SEPARATOR = re.compile(r"[;,]")


class RepoNotFound(Exception):
    """Repo nao encontrado em nenhuma das raizes pesquisadas."""

    def __init__(self, name: str, roots: list[str], suggestions: list[str]):
        self.name = name
        self.roots = roots
        self.suggestions = suggestions
        linhas = [f"Repositorio '{name}' nao encontrado localmente.", "Procurei em:"]
        linhas += [f"  - {r}" for r in roots] or ["  (nenhuma raiz existente)"]
        if suggestions:
            linhas.append(f"Voce quis dizer: {', '.join(suggestions)}?")
        linhas.append(
            "Informe o caminho completo em -r, adicione a raiz com --repos-root DIR "
            "ou configure 'local_repos_dirs' no scanner-config.yaml."
        )
        super().__init__("\n".join(linhas))


def _env_roots() -> list[str]:
    raw = os.getenv("LOCAL_REPOS_DIRS") or os.getenv("LOCAL_REPOS_DIR") or ""
    return [p.strip() for p in _ROOT_SEPARATOR.split(raw) if p.strip()]


def _abs(path: str) -> str:
    if os.path.isabs(path):
        return os.path.normpath(path)
    if os.path.isdir(path):
        return os.path.normpath(os.path.abspath(path))
    return os.path.normpath(os.path.join(PROJECT_ROOT, path))


def search_roots(cfg: dict, extra: list[str] | None = None) -> list[str]:
    """Raizes onde procurar clones, em ordem de prioridade, sem duplicatas."""
    candidates = list(extra or [])
    candidates += _env_roots()
    candidates += list(cfg.get("local_repos_dirs") or [])
    candidates.append(cfg.get("repos_dir") or "repos")
    candidates.append(os.path.dirname(PROJECT_ROOT))

    roots: list[str] = []
    seen: set[str] = set()
    for raw in candidates:
        root = _abs(raw)
        key = root.lower()
        if key in seen or not os.path.isdir(root):
            continue
        seen.add(key)
        roots.append(root)
    return roots


def _subdirs(root: str) -> list[str]:
    try:
        return [d for d in os.listdir(root) if os.path.isdir(os.path.join(root, d))]
    except OSError:
        return []


def resolve_repo_path(name_or_path: str, cfg: dict, extra_roots: list[str] | None = None) -> str:
    """
    Retorna o caminho absoluto do repo. Aceita caminho (absoluto/relativo) ou
    apenas o nome do projeto. Levanta RepoNotFound se nao existir em disco.
    """
    if os.path.isdir(name_or_path):
        return os.path.normpath(os.path.abspath(name_or_path))

    name = os.path.basename(os.path.normpath(name_or_path))
    roots = search_roots(cfg, extra_roots)

    for root in roots:
        direct = os.path.join(root, name)
        if os.path.isdir(direct):
            return os.path.normpath(direct)
        for d in _subdirs(root):
            if d.lower() == name.lower():
                return os.path.normpath(os.path.join(root, d))

    known = {d for root in roots for d in _subdirs(root)}
    suggestions = difflib.get_close_matches(name, sorted(known), n=3, cutoff=0.6)
    raise RepoNotFound(name, roots, suggestions)


# ---------------------------------------------------------------------------
# Git
# ---------------------------------------------------------------------------

def _git(repo_path: str, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", repo_path, *args],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )


def is_git_repo(repo_path: str) -> bool:
    return _git(repo_path, "rev-parse", "--git-dir").returncode == 0


def current_branch(repo_path: str) -> str | None:
    r = _git(repo_path, "rev-parse", "--abbrev-ref", "HEAD")
    if r.returncode != 0:
        return None
    branch = r.stdout.strip()
    return branch or None


def has_uncommitted_changes(repo_path: str) -> bool:
    r = _git(repo_path, "status", "--porcelain", "--untracked-files=no")
    return r.returncode == 0 and bool(r.stdout.strip())


def _ref_exists(repo_path: str, ref: str) -> bool:
    return _git(repo_path, "rev-parse", "--verify", "--quiet", ref).returncode == 0


def _local_branches(repo_path: str) -> list[str]:
    r = _git(repo_path, "for-each-ref", "--format=%(refname:short)", "refs/heads")
    return r.stdout.split() if r.returncode == 0 else []


def checkout_branch(repo_path: str, branch: str) -> tuple[bool, str]:
    """
    Garante que o repo esta na branch informada.

    Nunca descarta trabalho: se houver alteracoes nao commitadas e a branch atual
    for outra, aborta pedindo commit/stash. Cria branch de rastreio quando ela so
    existe em origin.
    """
    if not is_git_repo(repo_path):
        return False, f"'{repo_path}' nao e um repositorio git — nao da para trocar de branch."

    atual = current_branch(repo_path)
    if atual == branch:
        return True, f"Branch: {branch} (ja estava ativa)"

    if has_uncommitted_changes(repo_path):
        return False, (
            f"Alteracoes nao commitadas em '{repo_path}' (branch atual: {atual}).\n"
            f"Faca commit/stash antes de trocar para '{branch}', ou rode sem --branch "
            f"para validar a branch atual."
        )

    if not _ref_exists(repo_path, f"refs/heads/{branch}"):
        if not _ref_exists(repo_path, f"refs/remotes/origin/{branch}"):
            _git(repo_path, "fetch", "--quiet", "origin", branch)
        if _ref_exists(repo_path, f"refs/remotes/origin/{branch}"):
            r = _git(repo_path, "checkout", "-b", branch, "--track", f"origin/{branch}")
            if r.returncode == 0:
                return True, f"Branch: {branch} (criada a partir de origin/{branch})"
            return False, f"Falha ao criar branch '{branch}': {r.stderr.strip()}"

        locais = _local_branches(repo_path)
        proximas = difflib.get_close_matches(branch, locais, n=3, cutoff=0.5)
        msg = f"Branch '{branch}' nao existe em '{repo_path}' (nem local, nem em origin)."
        if proximas:
            msg += f"\nBranches parecidas: {', '.join(proximas)}"
        return False, msg

    r = _git(repo_path, "checkout", branch)
    if r.returncode != 0:
        return False, f"Falha ao fazer checkout de '{branch}': {r.stderr.strip()}"
    return True, f"Branch: {branch}"
