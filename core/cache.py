"""
Cache de conteúdo de arquivos indexado por (repo, filepath, sha).
Evita re-download de arquivos que não mudaram entre execuções.

Cada entrada armazena o conteúdo e o timestamp de criação.
Entradas com mais de TTL_DAYS dias são removidas automaticamente no load.
"""

import json
import logging
import os
import time

log = logging.getLogger(__name__)

CACHE_FILE = ".scanner_cache.json"
TTL_DAYS = 7
_TTL_SECONDS = TTL_DAYS * 86_400


def _now() -> float:
    return time.time()


def load_cache() -> dict:
    if not os.path.exists(CACHE_FILE):
        return {}
    try:
        with open(CACHE_FILE, encoding="utf-8") as f:
            raw: dict = json.load(f)
    except (json.JSONDecodeError, OSError):
        log.warning("Cache corrompido — iniciando vazio.")
        return {}

    cutoff = _now() - _TTL_SECONDS
    expired = [k for k, v in raw.items() if isinstance(v, dict) and v.get("ts", _now()) < cutoff]
    if expired:
        for k in expired:
            del raw[k]
        log.info("Cache: %d entrada(s) expirada(s) removida(s).", len(expired))

    return raw


def save_cache(cache: dict) -> None:
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False)


def cache_key(repo: str, filepath: str, sha: str) -> str:
    return f"{repo}:{filepath}:{sha}"


def get(cache: dict, repo: str, filepath: str, sha: str) -> str | None:
    entry = cache.get(cache_key(repo, filepath, sha))
    if entry is None:
        return None
    # Suporta entradas legadas (string pura) e novas (dict com ts)
    if isinstance(entry, str):
        return entry
    return entry.get("content")


def put(cache: dict, repo: str, filepath: str, sha: str, content: str) -> None:
    cache[cache_key(repo, filepath, sha)] = {"content": content, "ts": _now()}
