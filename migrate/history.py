"""
history.py — histórico de execuções do migrador.

Persiste cada execução em um arquivo JSONL (uma entrada JSON por linha).
Permite comparar progresso entre runs: quantos patches foram aplicados,
quantos itens de revisão restam, taxa de automação ao longo do tempo.

Arquivo padrão: migrate_history.jsonl (ao lado do relatório de saída).
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone, timedelta
from pathlib import Path

_DEFAULT_FILE = "migrate_history.jsonl"
_TZ_BR = timezone(timedelta(hours=-3))


@dataclass
class HistoryEntry:
    run_id:          str        # timestamp YYYYMMDD_HHMMSS
    timestamp:       str        # ISO 8601 BRT
    command:         str        # scan | fix | fix --dry-run
    path:            str        # diretório analisado
    projects:        int
    files_scanned:   int
    auto_patches:    int
    review_items:    int
    total:           int
    automation_rate: float
    scan_json:       str | None  # --from-scan usado, se houver
    dry_run:         bool


def _now_id() -> tuple[str, str]:
    now = datetime.now(_TZ_BR)
    return now.strftime("%Y%m%d_%H%M%S"), now.isoformat()


def record(
    summary: dict,
    command: str,
    path: str,
    dry_run: bool = False,
    scan_json: str | None = None,
    history_file: str = _DEFAULT_FILE,
) -> HistoryEntry:
    """Cria e persiste uma entrada de histórico. Retorna a entrada criada."""
    run_id, ts = _now_id()
    entry = HistoryEntry(
        run_id=run_id,
        timestamp=ts,
        command=command,
        path=path,
        projects=summary.get("projects", 0),
        files_scanned=summary.get("files_scanned", 0),
        auto_patches=summary.get("auto_patches", 0),
        review_items=summary.get("review_items", 0),
        total=summary.get("total", 0),
        automation_rate=summary.get("automation_rate", 0.0),
        scan_json=scan_json,
        dry_run=dry_run,
    )
    _append(entry, history_file)
    return entry


def load(history_file: str = _DEFAULT_FILE) -> list[HistoryEntry]:
    """Carrega todas as entradas do arquivo JSONL."""
    p = Path(history_file)
    if not p.exists():
        return []
    entries = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entries.append(HistoryEntry(**json.loads(line)))
        except (json.JSONDecodeError, TypeError):
            continue
    return entries


def _append(entry: HistoryEntry, history_file: str) -> None:
    with open(history_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(asdict(entry), ensure_ascii=False) + "\n")


def print_history(entries: list[HistoryEntry], last: int = 20) -> None:
    """Exibe as últimas N entradas em formato tabular."""
    shown = entries[-last:]
    if not shown:
        print("Nenhuma execucao registrada.")
        return

    w = 72
    print(f"\n{'='*w}")
    print(f"  {'Run ID':<18} {'Cmd':<18} {'Auto':>5} {'Rev':>5} {'Taxa':>6}  Path")
    print(f"  {'-'*17} {'-'*17} {'-'*5} {'-'*5} {'-'*6}  {'-'*20}")
    for e in shown:
        dry = " (dry)" if e.dry_run else ""
        cmd = f"{e.command}{dry}"[:17]
        print(f"  {e.run_id:<18} {cmd:<18} {e.auto_patches:>5} {e.review_items:>5} {e.automation_rate:>5.1f}%  {e.path}")

    # Tendência: compara primeira e última entrada real (não dry-run)
    real = [e for e in entries if not e.dry_run and e.command == "fix"]
    if len(real) >= 2:
        first, last_e = real[0], real[-1]
        delta_auto = last_e.auto_patches - first.auto_patches
        delta_rev  = last_e.review_items - first.review_items
        print(f"\n  Tendencia (fix real): auto {_sign(delta_auto)}  revisao {_sign(delta_rev)}")

    print(f"{'='*w}\n")


def _sign(n: int) -> str:
    return f"+{n}" if n > 0 else str(n)
