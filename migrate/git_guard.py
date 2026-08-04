"""
git_guard: verifica o estado do repositorio git antes de escrever em disco.

Regras:
  - Path fora de repo git -> avisa mas permite continuar.
  - Working tree suja     -> pergunta ao usuario (ou aborta em modo CI).
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


class GitDirtyError(RuntimeError):
    """Levantado quando a working tree esta suja e o usuario recusa continuar."""


def _run(cmd: list[str], cwd: str) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)


def _find_git_root(path: str) -> str | None:
    result = _run(["git", "rev-parse", "--show-toplevel"], cwd=str(Path(path).resolve()))
    return result.stdout.strip() if result.returncode == 0 else None


def _dirty_files(git_root: str) -> list[str]:
    result = _run(["git", "status", "--porcelain"], cwd=git_root)
    if result.returncode != 0:
        return []
    return [line[3:] for line in result.stdout.splitlines() if line.strip()]


def check(path: str, ci: bool = False) -> None:
    """
    Verifica o estado git do path antes de qualquer escrita.

    ci=True  -> aborta automaticamente se sujo (sem prompt).
    ci=False -> pergunta ao usuario.

    Levanta GitDirtyError se o usuario recusar ou ci=True e sujo.
    """
    git_root = _find_git_root(path)

    if git_root is None:
        print(f"[git] Aviso: '{path}' nao esta dentro de um repositorio git.")
        print("[git] Continuando sem verificacao de working tree.\n")
        return

    dirty = _dirty_files(git_root)
    if not dirty:
        print(f"[git] Working tree limpa. ({git_root})")
        return

    print(f"\n[git] Working tree SUJA em: {git_root}")
    print(f"[git] {len(dirty)} arquivo(s) com alteracoes nao commitadas:")
    for f in dirty[:10]:
        print(f"        {f}")
    if len(dirty) > 10:
        print(f"        ... e mais {len(dirty) - 10} arquivo(s)")
    print()

    if ci or not sys.stdin.isatty():
        raise GitDirtyError(
            "Abortando: working tree suja. "
            "Commite ou descarte as alteracoes antes de rodar o migrador."
        )

    answer = input("[git] Deseja continuar mesmo assim? [s/N] ").strip().lower()
    if answer not in ("s", "sim", "y", "yes"):
        raise GitDirtyError("Operacao cancelada pelo usuario.")
    print()
