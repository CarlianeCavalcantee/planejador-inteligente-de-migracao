"""
Client local — lê repositórios clonados em disco em vez da GitHub API.
Interface idêntica ao github_client para scan_repo_data e list_org_repos.
"""

import logging
import os

from core.github_client import _match_rules, _should_ignore, _content_has_anchor, _SEARCH_TERMS

log = logging.getLogger(__name__)

MAX_FILE_SIZE = 500_000


def list_local_repos(repos_dir: str) -> list[str]:
    """Lista subdiretórios de repos_dir que parecem repos git clonados."""
    if not os.path.isdir(repos_dir):
        raise FileNotFoundError(f"Diretório de repos não encontrado: {repos_dir}")
    return sorted(
        d for d in os.listdir(repos_dir)
        if os.path.isdir(os.path.join(repos_dir, d))
        and not d.startswith(".")
    )


def scan_repo_local(
    repo: str,
    repos_dir: str,
    ignore_paths: list[str],
    rules: list[dict],
    include_large: bool = False,
    bridge=None,
) -> tuple[list[tuple], dict[str, str]]:
    """
    Varre um repo clonado localmente.
    Retorna (candidates, content_map) no mesmo formato que scan_repo_data do github_client.
    """
    repo_path = os.path.join(repos_dir, repo)
    if not os.path.isdir(repo_path):
        log.warning("%s: diretório não encontrado em %s", repo, repos_dir)
        return [], {}

    all_exts = {ext for rule in rules for ext in rule["extensoes"]}
    all_named = {name for rule in rules for name in rule.get("nomes_arquivo", [])}
    _st_lower = [t.lower() for t in _SEARCH_TERMS]

    candidates: list[tuple] = []
    content_map: dict[str, str] = {}

    for dirpath, dirnames, filenames in os.walk(repo_path):
        # Poda diretórios ignorados in-place para não descer neles
        dirnames[:] = [
            d for d in dirnames
            if not _should_ignore(d, ignore_paths) and not d.startswith(".")
        ]

        for filename in filenames:
            abs_path = os.path.join(dirpath, filename)
            # filepath relativo ao repo (usa / como separador)
            filepath = os.path.relpath(abs_path, repo_path).replace("\\", "/")

            if _should_ignore(filepath, ignore_paths):
                continue

            # Filtra por extensão ou nome de arquivo
            has_ext = any(filepath.endswith(ext) for ext in all_exts)
            has_name = filename in all_named
            if not has_ext and not has_name:
                continue

            # Tamanho
            try:
                size = os.path.getsize(abs_path)
            except OSError:
                continue
            if size > MAX_FILE_SIZE and not include_large:
                log.debug("skip large file: %s (%.0fKB)", filepath, size / 1024)
                continue

            # Lê conteúdo
            try:
                with open(abs_path, encoding="utf-8", errors="replace") as fh:
                    content = fh.read()
            except OSError:
                continue

            # Filtro âncora: descarta arquivos sem nenhum termo de CNPJ
            cl = content.lower()
            if not any(t in cl for t in _st_lower) and not _content_has_anchor(content):
                continue

            matched = _match_rules(rules, filename, filepath)
            if not matched:
                continue

            candidates.append((filepath, "", matched))  # sha vazio — não usado no modo local
            content_map[filepath] = content

            if bridge and len(candidates) % 10 == 0:
                bridge.repo_local_progress(repo, len(candidates))

    log.info("%s: %d candidato(s) encontrado(s) localmente", repo, len(candidates))
    return candidates, content_map
