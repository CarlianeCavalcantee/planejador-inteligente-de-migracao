"""
Cliente GitHub API — async com semáforo, retry em rate limit e cache de conteúdo.
"""

import asyncio
import base64
import logging
import os
import re as _re

import aiohttp
from tqdm import tqdm

import core.cache as cache_mod

log = logging.getLogger(__name__)

GITHUB_API = "https://api.github.com"
MAX_FILE_SIZE = 500_000
MAX_CONCURRENT = 10  # requisições paralelas por repo


def _headers() -> dict:
    token = os.getenv("GITHUB_TOKEN")
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github.v3+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


# ---------------------------------------------------------------------------
# Pool de tokens — cada token tem cota independente na Search API
# ---------------------------------------------------------------------------

class _TokenPool:
    """
    Pool de tokens com exclusividade: cada repo reserva um token
    pelo tempo do scan, garantindo autenticação dedicada.
    Search API usa semáforo global separado (rate-limit por IP/org).
    """

    def __init__(self, tokens: list[str]) -> None:
        self._tokens = tokens
        self._queue: asyncio.Queue | None = None

    def _ensure_queue(self) -> asyncio.Queue:
        if self._queue is None:
            self._queue = asyncio.Queue()
            for t in self._tokens:
                self._queue.put_nowait(t)
        return self._queue

    async def acquire(self) -> tuple[str, None]:
        """Bloqueia até um token ficar livre. Retorna (token, None)."""
        token = await self._ensure_queue().get()
        return token, None

    def release(self, token: str) -> None:
        self._ensure_queue().put_nowait(token)

    @property
    def size(self) -> int:
        return len(self._tokens)


_TOKEN_POOL: _TokenPool | None = None


def init_token_pool(extra_tokens: list[str] | None = None) -> _TokenPool:
    """Inicializa o pool com GITHUB_TOKEN + tokens extras do ambiente."""
    global _TOKEN_POOL
    primary = os.getenv("GITHUB_TOKEN", "")
    tokens = [primary] if primary else []
    # Tokens extras: GITHUB_TOKEN_2, GITHUB_TOKEN_3, ...
    for i in range(2, 10):
        t = os.getenv(f"GITHUB_TOKEN_{i}")
        if t:
            tokens.append(t)
    if extra_tokens:
        tokens.extend(t for t in extra_tokens if t not in tokens)
    if not tokens:
        raise RuntimeError("Nenhum GITHUB_TOKEN definido.")
    _TOKEN_POOL = _TokenPool(tokens)
    log.info("Token pool: %d token(s) disponível(is)", _TOKEN_POOL.size)
    return _TOKEN_POOL


def _get_pool() -> _TokenPool:
    global _TOKEN_POOL
    if _TOKEN_POOL is None:
        _TOKEN_POOL = init_token_pool()
    return _TOKEN_POOL


def _headers_for(token: str) -> dict:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github.v3+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }



async def _get(
    session: aiohttp.ClientSession,
    url: str,
    params: dict = None,
    _token_ref: list[str] | None = None,
) -> dict | None:
    """
    GET async com retry em rate limit (403/429).
    Se _token_ref=[token] for passado e o token estiver com cota esgotada,
    aguarda o reset em vez de tentar trocar (troca de token em sessão ativa
    causa corrida entre corrotinas que compartilham a mesma sessão).
    """
    import time
    for attempt in range(4):
        headers = {"Authorization": f"Bearer {_token_ref[0]}"} if _token_ref else {}
        async with session.get(url, params=params, headers=headers, timeout=aiohttp.ClientTimeout(total=30)) as resp:
            if resp.status == 200:
                return await resp.json()
            if resp.status in (403, 429):
                remaining = resp.headers.get("x-ratelimit-remaining")
                reset = resp.headers.get("x-ratelimit-reset")
                retry_after = resp.headers.get("Retry-After")
                if reset:
                    wait = max(1, int(reset) - int(time.time()) + 2)
                elif retry_after:
                    wait = int(retry_after)
                else:
                    wait = min(60 * (2 ** attempt), 300)
                log.warning("rate-limit: aguardando %ds (url=%s)", wait, url)
                await asyncio.sleep(wait)
            elif resp.status == 404:
                return None
            else:
                log.warning("GET %s → %d", url, resp.status)
                return None
    return None


async def list_org_repos(org: str) -> list[str]:
    token, _ = await _get_pool().acquire()
    async with aiohttp.ClientSession(headers=_headers_for(token)) as session:
        repos, page = [], 1
        while True:
            data = await _get(session, f"{GITHUB_API}/orgs/{org}/repos",
                              {"per_page": 100, "page": page, "type": "all"})
            if not data:
                break
            repos.extend(r["name"] for r in data if not r.get("archived"))
            if len(data) < 100:
                break
            page += 1
        return sorted(repos)


async def get_repo_tree(session: aiohttp.ClientSession, org: str, repo: str) -> list[dict]:
    meta = await _get(session, f"{GITHUB_API}/repos/{org}/{repo}")
    if not meta:
        return []
    branch = meta.get("default_branch", "main")
    tree = await _get(session, f"{GITHUB_API}/repos/{org}/{repo}/git/trees/{branch}?recursive=1")
    if not tree:
        return []
    return [item for item in tree.get("tree", []) if item["type"] == "blob"]


# ---------------------------------------------------------------------------
# Listas de termos
# ---------------------------------------------------------------------------

# Search API do GitHub é case-insensitive — manter apenas formas canônicas únicas.
# Variações de case (CNPJ/Cnpj, TAX_ID/taxId) são redundantes e só aumentam batches.
_EXTRA_TERMS = [
    "cnpj",
    "cpfCnpj", "cpf_cnpj",
    "documento",
    "pessoaJuridica", "pessoa_juridica",
    "legalEntity", "legal_entity",
    "taxId", "tax_id",
    "federalId", "federal_id",
    "cnpjRegex", "formatCNPJ",
    "empresa",
    "cnpj_empresa", "cnpjEmpresa",
    "cnpjDaEmpresa", "cnpj_da_empresa",
    "companyId", "company_id",
    "corporateId", "corporate_id",
    "registrationNumber", "registration_number",
]

_CNPJ_ALIASES = [
    "cpfCnpj", "cpf_cnpj",
    "documento",
    "nrDocumento", "nr_documento",
    "numDocumento", "num_documento",
    "documentoFederal", "documento_federal",
    "taxId", "tax_id",
    "federalId", "federal_id",
    "docNumber", "doc_number",
    "nrDoc", "nr_doc",
    "numDoc", "num_doc",
    "corporateId", "corporate_id",
    "companyId", "company_id",
    "registrationNumber", "registration_number",
    "cnpjRegex", "cnpjPattern", "formatCNPJ", "formatCpfCnpj", "maskCNPJ",
    "empresa",
    "cnpjEmpresa", "cnpj_empresa",
    "cnpjDaEmpresa", "cnpj_da_empresa",
    "pessoaJuridica", "pessoa_juridica",
    "legalEntity", "legal_entity",
    "legalPerson", "legal_person",
]

# Termos usados para confirmar conteúdo no fallback via tree (case-insensitive na comparação)
_SEARCH_TERMS = [
    "cnpj", "cpfCnpj", "cpf_cnpj",
    "taxId", "tax_id", "federalId", "federal_id",
    "cnpjRegex", "formatCNPJ",
    "cnpjEmpresa", "cnpj_empresa", "cnpjDaEmpresa",
    "companyId", "company_id",
    "corporateId", "corporate_id",
    "registrationNumber", "registration_number",
    "pessoaJuridica", "pessoa_juridica",
    "legalEntity", "legal_entity",
]

# Termos âncora: presença obrigatória no conteúdo para confirmar contexto de CNPJ.
# Arquivos trazidos por termos genéricos são descartados se não tiverem nenhum âncora.
_ANCHOR_TERMS = [
    "cnpj", "CNPJ", "cpfCnpj", "cpf_cnpj", "CPF_CNPJ",
    "taxId", "TAX_ID", "tax_id", "federalId", "FEDERAL_ID",
    "CNPJ_REGEX", "cnpjRegex", "formatCNPJ", "maskCNPJ",
    "cnpjEmpresa", "empresaCnpj", "cnpj_empresa", "empresa_cnpj",
    "cnpjDaEmpresa", "cnpj_da_empresa",
    "pessoaJuridica", "pessoa_juridica", "legalEntity", "legalPerson",
]
_ANCHOR_RES = [_re.compile(_re.escape(t), _re.IGNORECASE) for t in _ANCHOR_TERMS] + [
    _re.compile(r"\d{14}"),
    _re.compile(r"\d{2}\.\d{3}\.\d{3}"),
]


def _content_has_anchor(content: str) -> bool:
    """Verifica se o conteúdo tem pelo menos um termo âncora de CNPJ."""
    return any(pat.search(content) for pat in _ANCHOR_RES)


# Rate limiter global para Search API — GitHub limita ~10 req/min por org.
# Com múltiplos repos em paralelo, o intervalo precisa ser conservador o suficiente
# para nunca receber items=[] silencioso por throttle.
# 8s garante ~7.5 req/min — abaixo do limite mesmo com burst.
_SEARCH_LOCK: asyncio.Lock | None = None
_SEARCH_LAST_T: float = 0.0
_SEARCH_INTERVAL = 8.0  # segundos entre queries


def _get_search_lock() -> asyncio.Lock:
    global _SEARCH_LOCK
    if _SEARCH_LOCK is None:
        _SEARCH_LOCK = asyncio.Lock()
    return _SEARCH_LOCK


async def _search_throttle() -> None:
    """
    Aguarda o intervalo mínimo desde a última query.
    O lock é adquirido ANTES do sleep e liberado DEPOIS que o chamador
    registra _SEARCH_LAST_T — garantindo que nenhuma outra corrotina
    entre até o intervalo completo ter passado.
    Retorna com o lock ainda adquirido; o chamador deve chamar _search_done().
    """
    global _SEARCH_LAST_T
    import time
    lock = _get_search_lock()
    await lock.acquire()
    now = time.monotonic()
    wait = _SEARCH_INTERVAL - (now - _SEARCH_LAST_T)
    if wait > 0:
        await asyncio.sleep(wait)
    _SEARCH_LAST_T = time.monotonic()
    lock.release()


def _get_search_sem() -> asyncio.Lock:
    return _get_search_lock()


# ---------------------------------------------------------------------------
# Busca em batch (OR)
# ---------------------------------------------------------------------------

def _make_batches(terms: list[str], max_chars: int = 180) -> list[list[str]]:
    """
    Agrupa termos em batches cujo join com OR não ultrapasse max_chars.
    Mantém a query dentro do limite seguro da Search API do GitHub.
    """
    batches: list[list[str]] = []
    current: list[str] = []
    current_len = 0
    for t in terms:
        needed = len(t) + (4 if current else 0)  # 4 = len(" OR ")
        if current and current_len + needed > max_chars:
            batches.append(current)
            current = [t]
            current_len = len(t)
        else:
            current.append(t)
            current_len += needed
    if current:
        batches.append(current)
    return batches


# União deduplicada de _EXTRA_TERMS + _CNPJ_ALIASES, calculada uma vez.
_ALL_TERMS: list[str] = []


def _get_all_terms() -> list[str]:
    global _ALL_TERMS
    if not _ALL_TERMS:
        seen: set[str] = set()
        for t in _EXTRA_TERMS + _CNPJ_ALIASES:
            if t not in seen:
                seen.add(t)
                _ALL_TERMS.append(t)
    return _ALL_TERMS


async def _search_batch(
    session: aiohttp.ClientSession,
    org: str,
    repo: str,
    terms: list[str],
    search_sem: asyncio.Semaphore,
    batch_idx: int = 0,
    total_batches: int = 1,
    bridge=None,
) -> set[str]:
    q = " OR ".join(terms) + f" repo:{org}/{repo}"
    paths, page = set(), 1
    if bridge:
        bridge.repo_search_progress(repo, batch_idx + 1, total_batches, terms[0])
    else:
        tqdm.write(f"  [search] {repo}: batch {batch_idx+1}/{total_batches} ({terms[0]}...)")
    while True:
        await _search_throttle()
        data = await _get(
            session,
            f"{GITHUB_API}/search/code",
            {"q": q, "per_page": 100, "page": page},
        )
        if not data:
            break
        items = data.get("items", [])
        total = data.get("total_count", 0)
        # items vazio com total > 0 indica throttling silencioso — retry
        if not items and total > 0:
            log.warning("%s: Search API retornou items=[] mas total_count=%d (throttle silencioso) — aguardando 15s", repo, total)
            await asyncio.sleep(15)
            continue
        if not items:
            break
        for item in items:
            paths.add(item["path"])
        if total > 1000 and len(paths) >= 1000:
            log.warning("%s: Search API limitou a 1000/%d para batch %s — complementando via tree",
                        repo, total, terms[:3])
            break
        if len(data["items"]) < 100:
            break
        page += 1
    return paths


async def search_cnpj_files(
    session: aiohttp.ClientSession,
    org: str,
    repo: str,
    search_sem: asyncio.Semaphore,
    bridge=None,
) -> set[str]:
    paths: set[str] = set()
    batches = _make_batches(_get_all_terms())
    log.info("%s: %d termos → %d batches de search", repo, len(_get_all_terms()), len(batches))
    for i, batch in enumerate(batches):
        extra = await _search_batch(session, org, repo, batch, search_sem, i, len(batches), bridge=bridge)
        new = extra - paths
        if new:
            log.info("%s: +%d arquivo(s) via batch %s", repo, len(new), batch[:2])
        paths |= extra
        if len(paths) >= 1000:
            log.info("%s: Search API saturada — parando busca", repo)
            break
    return paths


async def search_alias_files(
    session: aiohttp.ClientSession,
    org: str,
    repo: str,
    aliases: list[str],
    search_sem: asyncio.Semaphore,
) -> set[str]:
    """Busca aliases via batches de OR. Usado com --scan-aliases."""
    found: set[str] = set()
    alias_batches = _make_batches(aliases)
    for i, batch in enumerate(alias_batches):
        found |= await _search_batch(session, org, repo, batch, search_sem, i, len(alias_batches))
    return found


async def _check_alias(
    session: aiohttp.ClientSession,
    org: str,
    repo: str,
    alias: str,
) -> tuple[str, str | None]:
    """Retorna (alias, alias) se encontrado, (alias, None) caso contrário."""
    await _search_throttle()
    data = await _get(
        session,
        f"{GITHUB_API}/search/code",
        {"q": f"{alias} repo:{org}/{repo}", "per_page": 1},
    )
    if data and data.get("total_count", 0) > 0:
        return alias, alias
    return alias, None


async def audit_alias_coverage(
    org: str,
    repos_sem_impacto: list[str],
    disk_cache: dict,
) -> dict[str, list[str]]:
    """
    Para repos com zero impactos, busca aliases de campo que podem conter CNPJ
    sem usar a palavra 'cnpj'. Retorna {repo: [aliases_encontrados]}.
    """
    cache_key = "alias_audit:{}"
    pending = [r for r in repos_sem_impacto if cache_key.format(r) not in disk_cache]

    if pending:
        async with aiohttp.ClientSession(headers=_headers()) as session:
            tasks = {
                (repo, alias): _check_alias(session, org, repo, alias)
                for repo in pending
                for alias in _CNPJ_ALIASES
            }
            results = await asyncio.gather(*tasks.values())

        fetched: dict[str, list[str]] = {}
        for (repo, _), (_, found) in zip(tasks.keys(), results):
            if found:
                fetched.setdefault(repo, []).append(found)

        for repo in pending:
            disk_cache[cache_key.format(repo)] = fetched.get(repo, [])

    resultado: dict[str, list[str]] = {}
    for repo in repos_sem_impacto:
        aliases = disk_cache.get(cache_key.format(repo), [])
        if aliases:
            resultado[repo] = aliases
    return resultado


# ---------------------------------------------------------------------------
# Download de arquivos
# ---------------------------------------------------------------------------

async def _fetch_large_file(
    session: aiohttp.ClientSession,
    sem: asyncio.Semaphore,
    org: str,
    repo: str,
    filepath: str,
    sha: str,
    disk_cache: dict,
) -> tuple[str, str | None]:
    """Baixa arquivo grande via Blob API (sem limite de tamanho da Contents API)."""
    cached = cache_mod.get(disk_cache, repo, filepath, sha)
    if cached is not None:
        return filepath, cached

    async with sem:
        await asyncio.sleep(0.1)
        data = await _get(session, f"{GITHUB_API}/repos/{org}/{repo}/git/blobs/{sha}")

    if not data or data.get("encoding") != "base64":
        return filepath, None
    try:
        content = base64.b64decode(data["content"]).decode("utf-8", errors="replace")
        cache_mod.put(disk_cache, repo, filepath, sha, content)
        return filepath, content
    except Exception:
        return filepath, None


async def _fetch_file(
    session: aiohttp.ClientSession,
    sem: asyncio.Semaphore,
    org: str,
    repo: str,
    filepath: str,
    sha: str,
    disk_cache: dict,
    include_large: bool = False,
    token_ref: list[str] | None = None,
) -> tuple[str, str | None]:
    """Baixa um arquivo respeitando o semáforo e usando cache de disco."""
    cached = cache_mod.get(disk_cache, repo, filepath, sha)
    if cached is not None:
        return filepath, cached

    async with sem:
        await asyncio.sleep(0.1)
        data = await _get(session, f"{GITHUB_API}/repos/{org}/{repo}/contents/{filepath}", _token_ref=token_ref)

    if not data or data.get("encoding") != "base64":
        return filepath, None
    if data.get("size", 0) > MAX_FILE_SIZE:
        if include_large:
            log.info("large file: %s (%.0fKB) — baixando via Blob API", filepath, data['size'] / 1024)
            return await _fetch_large_file(session, sem, org, repo, filepath, sha, disk_cache)
        log.debug("skip large file: %s (%.0fKB > %dKB)", filepath, data['size'] / 1024, MAX_FILE_SIZE // 1024)
        return filepath, None
    try:
        content = base64.b64decode(data["content"]).decode("utf-8", errors="replace")
        cache_mod.put(disk_cache, repo, filepath, sha, content)
        return filepath, content
    except Exception:
        return filepath, None


async def fetch_files(
    org: str,
    repo: str,
    candidates: list[tuple[str, str, list]],
    disk_cache: dict,
    include_large: bool = False,
    token: str | None = None,
    max_concurrent: int = MAX_CONCURRENT,
    token_ref: list[str] | None = None,
) -> dict[str, str]:
    """Baixa todos os arquivos candidatos em paralelo usando o token do repo."""
    if token is None:
        token, _ = await _get_pool().acquire()
    if token_ref is None:
        token_ref = [token]
    sem = asyncio.Semaphore(max_concurrent)
    # Sessão sem Authorization fixa — cada request injeta o token via header override em _get()
    async with aiohttp.ClientSession() as session:
        tasks = [
            _fetch_file(session, sem, org, repo, fp, sha, disk_cache, include_large, token_ref)
            for fp, sha, _ in candidates
        ]
        results = await asyncio.gather(*tasks)
    return {fp: content for fp, content in results if content is not None}


# ---------------------------------------------------------------------------
# Filtros de path
# ---------------------------------------------------------------------------

def _should_ignore(filepath: str, ignore_paths: list[str]) -> bool:
    """
    Verifica por segmento de path para evitar falsos positivos como
    'build' em 'src/builder/CnpjBuilder.java'.
    Suporta glob simples: '*.min.js' compara o sufixo do basename.
    """
    parts = set(filepath.replace("\\", "/").split("/"))
    for ig in ignore_paths:
        if ig.startswith("*"):
            if filepath.endswith(ig[1:]):
                return True
        elif ig in parts:
            return True
    return False


# ---------------------------------------------------------------------------
# Scan principal
# ---------------------------------------------------------------------------

async def scan_repo_data(
    org: str,
    repo: str,
    ignore_paths: list[str],
    rules: list[dict],
    disk_cache: dict,
    include_large: bool = False,
    scan_aliases: bool = False,
    bridge=None,
) -> tuple[list[tuple], dict[str, str]]:
    """
    Faz tree + search em batch + filtra candidatos.
    Adquire um token do pool para autenticação; Search usa semáforo global
    para serializar queries entre todos os workers (rate-limit por IP/org).
    """
    token, _token_sem = await _get_pool().acquire()
    token_ref = [token]  # mutável para permitir troca dentro de _get()
    headers = _headers_for(token)
    search_sem = _get_search_sem()  # semáforo global compartilhado
    try:
        async with aiohttp.ClientSession(headers=headers) as session:
            # Busca tree primeiro — evita gastar slots de Search em repos vazios
            tree = await get_repo_tree(session, org, repo)
            if not tree:
                return [], {}

            # Verifica se há arquivos com extensões relevantes antes de buscar
            all_exts = {ext for rule in rules for ext in rule["extensoes"]}
            all_named = {name for rule in rules for name in rule.get("nomes_arquivo", [])}
            has_relevant = any(
                not _should_ignore(item["path"], ignore_paths) and (
                    any(item["path"].endswith(ext) for ext in all_exts)
                    or os.path.basename(item["path"]) in all_named
                )
                for item in tree
            )
            if not has_relevant:
                log.info("%s: nenhum arquivo com extensão relevante na tree — pulando Search API", repo)
                return [], {}

            cnpj_paths = await search_cnpj_files(session, org, repo, search_sem, bridge=bridge)

            # Se Search retornou zero resultados mas a tree tem arquivos relevantes,
            # é provável throttle total (total_count=0 silencioso) — fallback via tree
            if not cnpj_paths:
                log.warning("%s: Search retornou 0 arquivos — ativando fallback completo via tree", repo)
                all_exts_fb = {ext for rule in rules for ext in rule["extensoes"]}
                fb_candidates = [
                    (item["path"], item.get("sha", ""), [])
                    for item in tree
                    if not _should_ignore(item["path"], ignore_paths)
                    and any(item["path"].endswith(ext) for ext in all_exts_fb)
                ]
                if fb_candidates:
                    # Cap de 300 arquivos para não esgotar a cota da Contents API
                    if len(fb_candidates) > 300:
                        log.warning("%s: fallback limitado a 300/%d arquivos", repo, len(fb_candidates))
                        fb_candidates = fb_candidates[:300]
                    log.info("%s: baixando %d arquivo(s) via tree fallback", repo, len(fb_candidates))
                    fb_content = await fetch_files(org, repo, fb_candidates, disk_cache, include_large, token=token_ref[0], max_concurrent=5, token_ref=token_ref)
                    _st_lower = [t.lower() for t in _SEARCH_TERMS]
                    for fp, content in fb_content.items():
                        cl = content.lower()
                        if any(t in cl for t in _st_lower):
                            cnpj_paths.add(fp)
                    log.info("%s: %d arquivo(s) confirmados via tree fallback", repo, len(cnpj_paths))

            if scan_aliases:
                alias_paths = await search_alias_files(session, org, repo, _CNPJ_ALIASES, search_sem)
                new_alias_paths = alias_paths - cnpj_paths
                if new_alias_paths:
                    log.info("%s: +%d arquivo(s) via aliases de campo", repo, len(new_alias_paths))
                cnpj_paths |= alias_paths
    finally:
        _get_pool().release(token_ref[0])

    if not tree:
        return [], {}

    sha_map = {item["path"]: item.get("sha", "") for item in tree}
    search_truncated = len(cnpj_paths) >= 1000

    if search_truncated:
        all_exts = {ext for rule in rules for ext in rule["extensoes"]}
        tree_extras = [
            item["path"] for item in tree
            if item["path"] not in cnpj_paths
            and not _should_ignore(item["path"], ignore_paths)
            and any(item["path"].endswith(ext) for ext in all_exts)
        ]
        log.info("%s: Search API limitou a 1000 resultados — baixando %d arquivo(s) adicionais da tree",
                 repo, len(tree_extras))
        extra_candidates = [(p, sha_map.get(p, ""), []) for p in tree_extras]
        extra_content_map = await fetch_files(org, repo, extra_candidates, disk_cache, include_large)
        confirmed = {
            p for p, content in extra_content_map.items()
            if any(t.lower() in content.lower() for t in _SEARCH_TERMS)
        }
        if confirmed:
            log.info("%s: %d arquivo(s) confirmados com 'cnpj' no conteúdo via tree", repo, len(confirmed))
        cnpj_paths |= confirmed

    # search_paths = arquivos confirmados pela Search API (isentos do filtro âncora)
    search_paths = set(cnpj_paths)

    candidates = []
    for filepath in cnpj_paths:
        if _should_ignore(filepath, ignore_paths):
            continue
        filename = os.path.basename(filepath)
        matched = _match_rules(rules, filename, filepath)
        if matched:
            sha = sha_map.get(filepath, "")
            candidates.append((filepath, sha, matched))

    # Arquivos com nomes_arquivo incluídos diretamente da tree
    all_named_files: set[str] = set()
    for rule in rules:
        all_named_files.update(rule.get("nomes_arquivo", []))

    # named_paths = isentos do filtro âncora (incluídos por nome explícito)
    named_paths: set[str] = set()
    candidate_paths = {fp for fp, _, _ in candidates}
    for item in tree:
        filepath = item["path"]
        if filepath in candidate_paths or _should_ignore(filepath, ignore_paths):
            continue
        filename = os.path.basename(filepath)
        if filename not in all_named_files:
            continue
        matched = _match_rules(rules, filename, filepath)
        if matched:
            sha = sha_map.get(filepath, "")
            candidates.append((filepath, sha, matched))
            named_paths.add(filepath)
            log.info("%s: adicionado via nomes_arquivo: %s", repo, filepath)

    if not candidates:
        if tree:
            log.warning("%s: 0 candidatos encontrados (tree tem %d arquivos) — possível throttle da Search API", repo, len(tree))
        return [], {}

    content_map = await fetch_files(org, repo, candidates, disk_cache, include_large, token=token_ref[0], token_ref=token_ref)

    # Filtro âncora: aplica APENAS a arquivos trazidos via tree fallback (não confirmados pela Search API).
    # Arquivos da search já foram validados pelo GitHub; arquivos via nomes_arquivo são isentos por design.
    filtered: list[tuple] = []
    for fp, sha, matched in candidates:
        content = content_map.get(fp)
        if content and fp not in search_paths and fp not in named_paths and not _content_has_anchor(content):
            log.debug("%s: descartado (sem âncora CNPJ): %s", repo, fp)
            content_map.pop(fp, None)
        else:
            filtered.append((fp, sha, matched))

    if not filtered:
        return [], {}

    return filtered, content_map


def _match_rules(rules: list[dict], filename: str, filepath: str) -> list[dict]:
    r"""
    Casa regras por extensão testando as mais longas primeiro
    (ex: .spec.ts antes de .ts) para evitar classificação errada.
    Também detecta migrations Flyway (V\d+__*.sql) e Liquibase (changelog*.xml).
    """
    import re
    _FLYWAY = re.compile(r'^V\d+__.*\.sql$', re.IGNORECASE)
    _LIQUIBASE = re.compile(r'(changelog|changeset|db\.migration).*\.xml$', re.IGNORECASE)

    matched = []
    for rule in rules:
        exts = sorted(rule["extensoes"], key=len, reverse=True)
        for ext in exts:
            if filepath.endswith(ext):
                matched.append(rule)
                break
        else:
            if filename in rule.get("nomes_arquivo", []):
                matched.append(rule)
            elif rule.get("id", "").startswith("API") and any(
                k in filename.lower() for k in ("swagger", "openapi", "api-spec")
            ):
                matched.append(rule)
            elif rule.get("id") == "MIGRATION-001" and (
                _FLYWAY.match(filename) or _LIQUIBASE.search(filename)
            ):
                matched.append(rule)
    return matched
