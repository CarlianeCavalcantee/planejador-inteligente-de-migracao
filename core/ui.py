"""
TUI do CNPJ Impact Scanner — Textual.
Expõe ScannerUI (app) e ScannerBridge (thread-safe callbacks para o async worker).

Arquitetura:
- Modo API:   scan roda como worker async dentro do Textual (I/O bound, não trava)
- Modo local: scan roda em processo filho (subprocess); UI monitora o checkpoint
"""

import asyncio
import json
import logging
import os
import subprocess
import sys
from collections import Counter
from datetime import datetime
from typing import Callable

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.reactive import reactive
from textual.widgets import DataTable, Footer, Header, Label, Log, Static

# ---------------------------------------------------------------------------
# Cores por status de repo
# ---------------------------------------------------------------------------
_ICON = {"pending": "⏳", "running": "🔄", "ok": "✅", "error": "❌"}
_COMPLEXITY_COLOR = {"Alta": "red", "Média": "yellow", "Baixa": "green"}


# ---------------------------------------------------------------------------
# Painel de estatísticas
# ---------------------------------------------------------------------------

class StatsPanel(Static):
    total_repos: reactive[int] = reactive(0)
    done_repos: reactive[int] = reactive(0)
    total_impacts: reactive[int] = reactive(0)
    alta: reactive[int] = reactive(0)
    media: reactive[int] = reactive(0)
    baixa: reactive[int] = reactive(0)
    elapsed: reactive[str] = reactive("00:00")

    def render(self) -> str:
        pct = int(self.done_repos / self.total_repos * 100) if self.total_repos else 0
        return (
            f"[bold cyan]CNPJ Impact Scanner[/]\n\n"
            f"Repos   [bold]{self.done_repos}/{self.total_repos}[/] ({pct}%)\n"
            f"Impactos [bold]{self.total_impacts}[/]\n\n"
            f"[red]Alta  {self.alta:>5}[/]\n"
            f"[yellow]Média {self.media:>5}[/]\n"
            f"[green]Baixa {self.baixa:>5}[/]\n\n"
            f"⏱  {self.elapsed}"
        )


# ---------------------------------------------------------------------------
# App principal
# ---------------------------------------------------------------------------

class ScannerUI(App):
    CSS = """
    Screen {
        layout: grid;
        grid-size: 2 2;
        grid-rows: 1fr 1fr;
        grid-columns: 32 1fr;
    }
    #left-top {
        height: 100%;
        border: solid $primary;
        padding: 0 1;
    }
    #stats {
        height: auto;
        border: solid $accent;
        padding: 1;
        margin-bottom: 1;
    }
    #repo-list {
        height: 1fr;
        overflow-y: auto;
    }
    #impacts {
        height: 100%;
        border: solid $success;
        row-span: 2;
    }
    #log-panel {
        height: 100%;
        border: solid $warning;
    }
    DataTable {
        height: 1fr;
    }
    """

    BINDINGS = [Binding("q", "quit", "Sair")]

    def __init__(self, repos: list[str], org: str, scan_fn: Callable | None,
                 child_cmd: list[str] | None = None,
                 checkpoint_file: str | None = None,
                 **kwargs):
        super().__init__(**kwargs)
        self._all_repos = repos
        self._org = org
        self._scan_fn = scan_fn
        self._child_cmd = child_cmd
        self._checkpoint_file = checkpoint_file
        self._child_proc: subprocess.Popen | None = None
        self._repo_status: dict[str, str] = {r: "pending" for r in repos}
        self._repo_detail: dict[str, str] = {}
        self._scan_start = datetime.now()
        self._done = 0
        self._complexity_counter: Counter = Counter()

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Vertical(id="left-top"):
            yield StatsPanel(id="stats")
            yield Log(id="repo-list", highlight=True, max_lines=300)
        with Vertical(id="impacts"):
            yield Label("[bold]Impactos detectados[/]", markup=True)
            tbl = DataTable(id="impact-table", zebra_stripes=True, cursor_type="row")
            tbl.add_columns("Repo", "Área", "Complexidade", "Arquivo", "Linha")
            yield tbl
        with Vertical(id="log-panel"):
            yield Label("[bold]Log[/]", markup=True)
            yield Log(id="log-output", highlight=True, max_lines=500)
        yield Footer()

    def on_mount(self) -> None:
        stats = self.query_one("#stats", StatsPanel)
        stats.total_repos = len(self._all_repos)
        stats.done_repos = 0
        repo_log = self.query_one("#repo-list", Log)
        for r in self._all_repos:
            repo_log.write_line(f"{_ICON['pending']} {r}")
        self.set_interval(1, self._tick_elapsed)
        if self._child_cmd:
            # Modo local: lança processo filho e monitora checkpoint
            self._child_proc = subprocess.Popen(
                self._child_cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            self._seen_repos: set[str] = set()
            self._seen_impacts: set[str] = set()
            self.set_interval(1, self._poll_checkpoint)
        elif self._scan_fn is not None:
            self.set_timer(0.3, lambda: self.run_worker(self._scan_fn(), exclusive=True))

    def _tick_elapsed(self) -> None:
        delta = datetime.now() - self._scan_start
        m, s = divmod(int(delta.total_seconds()), 60)
        self.query_one("#stats", StatsPanel).elapsed = f"{m:02d}:{s:02d}"

    # ------------------------------------------------------------------
    # Modo monitor — lê checkpoint escrito pelo processo filho
    # ------------------------------------------------------------------

    async def _poll_checkpoint(self) -> None:
        if not hasattr(self, "_checkpoint_file") or self._child_proc is None:
            return
        # Verifica se o processo filho terminou
        if self._child_proc.poll() is not None:
            self._child_proc = None  # guarda: impede re-entrada
            self._load_checkpoint_final()
            return
        try:
            with open(self._checkpoint_file, encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError):
            return

        done_repos = data.get("done", [])
        impacts = data.get("impacts", [])

        # Novos repos concluídos
        repo_stats = data.get("repo_stats", {})
        for repo in done_repos:
            if repo not in self._seen_repos:
                self._seen_repos.add(repo)
                repo_impacts = [i for i in impacts if i.get("repositorio") == repo]
                stats = repo_stats.get(repo, {})
                candidatos = stats.get("candidatos", 0)
                self.repo_done(repo, candidatos, len(repo_impacts))

        # Repos ainda em andamento (na fila mas não concluídos)
        running = data.get("running", [])
        for repo in running:
            if repo not in self._seen_repos:
                self._repo_status[repo] = "running"
        self._refresh_repo_list()

        # Novos impactos
        new_impacts = []
        for imp in impacts:
            key = f"{imp.get('repositorio')}:{imp.get('filepath')}:{imp.get('match', {}).get('linha')}"
            if key not in self._seen_impacts:
                self._seen_impacts.add(key)
                new_impacts.append({
                    "_rule": {
                        "area": imp.get("area", ""),
                        "complexidade": imp.get("complexidade", ""),
                    },
                    "repositorio": imp.get("repositorio", ""),
                    "filepath": imp.get("filepath", ""),
                    "match": imp.get("match", {}),
                    "requer_compatibilidade_dual": imp.get("requer_compatibilidade_dual", False),
                    "prioridade": imp.get("prioridade", "P3"),
                })
        if new_impacts:
            self.add_impacts(new_impacts)

    def _load_checkpoint_final(self) -> None:
        """Processo filho terminou — sincroniza estado final e lê total do JSON de saída."""
        # Tenta ler o JSON de saída gerado pelo _finish (mais confiável que o checkpoint)
        out_json = "docs/output/impacto_cnpj.json"
        total = 0
        try:
            with open(out_json, encoding="utf-8") as f:
                data = json.load(f)
            total = data.get("estatisticas", {}).get("total_impactos_encontrados", 0)
            # Sincroniza repos que o poll pode ter perdido
            imp_list = data.get("matriz_impacto", [])
            repo_stats_raw: dict = {}
            for imp in imp_list:
                r = imp.get("repositorio", "")
                repo_stats_raw.setdefault(r, {"candidatos": 0, "impactos": 0})
                repo_stats_raw[r]["impactos"] += 1
            for repo in data.get("repositorios_analisados", []):
                if repo not in self._seen_repos:
                    self._seen_repos.add(repo)
                    n_imp = repo_stats_raw.get(repo, {}).get("impactos", 0)
                    self.repo_done(repo, 0, n_imp)
        except (OSError, json.JSONDecodeError):
            # Fallback: lê checkpoint se o JSON ainda não foi gerado
            try:
                with open(self._checkpoint_file, encoding="utf-8") as f:
                    ck = json.load(f)
                repo_stats = ck.get("repo_stats", {})
                for repo in ck.get("done", []):
                    if repo not in self._seen_repos:
                        self._seen_repos.add(repo)
                        n_imp = len([i for i in ck["impacts"] if i.get("repositorio") == repo])
                        self.repo_done(repo, repo_stats.get(repo, {}).get("candidatos", 0), n_imp)
                total = len(ck.get("impacts", []))
            except (OSError, json.JSONDecodeError):
                pass
        self.scan_complete(total, out_json)

    # ------------------------------------------------------------------
    # Thread-safe updaters (called from asyncio worker via call_from_thread)
    # ------------------------------------------------------------------

    def repo_started(self, repo: str, slot: int) -> None:
        self._repo_status[repo] = "running"
        self._repo_detail[repo] = f"slot {slot}"
        self._refresh_repo_list()
        self.query_one("#log-output", Log).write_line(
            f"[cyan]→ slot {slot} > {repo}[/]"
        )

    def repo_done(self, repo: str, candidates: int, impacts: int, error: str | None = None) -> None:
        self._repo_status[repo] = "error" if error else "ok"
        detail = error or f"{candidates} cand → {impacts} imp"
        self._repo_detail[repo] = detail
        self._done += 1
        self._refresh_repo_list()
        log_widget = self.query_one("#log-output", Log)
        if error:
            log_widget.write_line(f"[red]✗ {repo}: {error}[/]")
        else:
            log_widget.write_line(f"[green]✓ {repo}: {detail}[/]")
        stats = self.query_one("#stats", StatsPanel)
        stats.done_repos = self._done

    def repo_search_progress(self, repo: str, batch: int, total: int, term: str) -> None:
        self._repo_detail[repo] = f"search {batch}/{total} ({term})"
        self._refresh_repo_list()

    def repo_local_progress(self, repo: str, candidates: int) -> None:
        self._repo_detail[repo] = f"lendo... {candidates} arq"
        self._refresh_repo_list()

    def add_impacts(self, impacts: list[dict]) -> None:
        if not impacts:
            return
        tbl = self.query_one("#impact-table", DataTable)
        stats = self.query_one("#stats", StatsPanel)
        for imp in impacts:
            area = imp.get("_rule", {}).get("area", "")
            cx = imp.get("_rule", {}).get("complexidade", "")
            fp = imp.get("filepath", "")
            filename = fp.split("/")[-1] if fp else ""
            linha = str(imp.get("match", {}).get("linha", ""))
            repo = imp.get("repositorio", "")
            color = _COMPLEXITY_COLOR.get(cx, "white")
            tbl.add_row(repo, area, f"[{color}]{cx}[/]", filename, linha)
            self._complexity_counter[cx] += 1
        total = sum(self._complexity_counter.values())
        stats.total_impacts = total
        stats.alta = self._complexity_counter["Alta"]
        stats.media = self._complexity_counter["Média"]
        stats.baixa = self._complexity_counter["Baixa"]

    def log_message(self, msg: str, level: str = "INFO") -> None:
        color = {"WARNING": "yellow", "ERROR": "red", "DEBUG": "dim"}.get(level, "white")
        ts = datetime.now().strftime("%H:%M:%S")
        self.query_one("#log-output", Log).write_line(
            f"[dim]{ts}[/] [{color}]{msg}[/]"
        )

    def scan_complete(self, total: int, out_json: str) -> None:
        self.query_one("#log-output", Log).write_line(
            f"[bold green]✅ Concluído — {total} impactos → {out_json}[/]"
        )

    def _refresh_repo_list(self) -> None:
        repo_log = self.query_one("#repo-list", Log)
        repo_log.clear()
        for r in self._all_repos:
            status = self._repo_status.get(r, "pending")
            detail = self._repo_detail.get(r, "")
            icon = _ICON[status]
            color = {"ok": "green", "error": "red", "running": "cyan", "pending": "dim"}[status]
            suffix = f" [dim]{detail}[/]" if detail else ""
            repo_log.write_line(f"[{color}]{icon} {r}[/]{suffix}")


# ---------------------------------------------------------------------------
# Bridge — chamado do worker async, despacha para a UI via call_from_thread
# ---------------------------------------------------------------------------

class ScannerBridge:
    """Proxy entre o worker async e o ScannerUI.
    Métodos chamados de corrotinas async usam a UI diretamente.
    Métodos chamados de threads (run_in_executor) usam call_from_thread.
    """

    def __init__(self, app: "ScannerUI") -> None:
        self._app = app

    def _is_same_thread(self) -> bool:
        import threading
        return threading.current_thread() is threading.main_thread()

    def _call(self, fn, *args) -> None:
        if self._is_same_thread():
            fn(*args)
        else:
            self._app.call_from_thread(fn, *args)

    def repo_started(self, repo: str, slot: int) -> None:
        self._call(self._app.repo_started, repo, slot)

    def repo_done(self, repo: str, candidates: int, impacts: int, error: str | None = None) -> None:
        self._call(self._app.repo_done, repo, candidates, impacts, error)

    def repo_search_progress(self, repo: str, batch: int, total: int, term: str) -> None:
        self._call(self._app.repo_search_progress, repo, batch, total, term)

    def repo_local_progress(self, repo: str, candidates: int) -> None:
        self._call(self._app.repo_local_progress, repo, candidates)

    def add_impacts(self, impacts: list[dict]) -> None:
        self._call(self._app.add_impacts, impacts)

    def log_message(self, msg: str, level: str = "INFO") -> None:
        self._call(self._app.log_message, msg, level)

    def scan_complete(self, total: int, out_json: str) -> None:
        self._call(self._app.scan_complete, total, out_json)


# ---------------------------------------------------------------------------
# Handler de logging que redireciona para a bridge
# ---------------------------------------------------------------------------

class BridgeLogHandler(logging.Handler):
    def __init__(self, bridge: ScannerBridge) -> None:
        super().__init__()
        self._bridge = bridge

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self._bridge.log_message(self.format(record), record.levelname)
        except Exception:
            pass
