"""
CLI do migrador CNPJ alfanumerico.

Uso:
  python -m migrate scan   <caminho>
  python -m migrate fix    <caminho> [--dry-run]
  python -m migrate report <caminho> [--out arquivo.md]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from migrate.transformer import ScanStats, TransformResult, _load_rules, transform_directory
from migrate.git_guard import GitDirtyError, check as git_check
from migrate.validator import ValidateResult, validate_directory
from migrate.report_html import generate_html
from migrate import history as _history
from migrate.scanner_bridge import repos_from_scan, repos_from_flow, flow_names, summary_from_scan

_RULE_META: dict[str, dict] = {}


def _load_rule_meta() -> None:
    global _RULE_META
    if not _RULE_META:
        _RULE_META = {
            r["id"]: {"description": r.get("description", ""), "priority": r.get("priority", 50)}
            for r in _load_rules()
        }


# ─── helpers ─────────────────────────────────────────────────────────────────

def _summary(stats: ScanStats) -> dict:
    results = stats.results
    total_auto   = sum(r.auto_count   for r in results)
    total_review = sum(r.review_count for r in results)
    total        = total_auto + total_review

    by_rule_auto:   dict[str, int] = {}
    by_rule_review: dict[str, int] = {}
    for r in results:
        for p in r.patches:
            by_rule_auto[p.rule_id] = by_rule_auto.get(p.rule_id, 0) + 1
        for p in r.review_items:
            by_rule_review[p.rule_id] = by_rule_review.get(p.rule_id, 0) + 1

    all_rule_ids = sorted(
        set(by_rule_auto) | set(by_rule_review),
        key=lambda rid: _RULE_META.get(rid, {}).get("priority", 50),
        reverse=True,
    )
    by_rule = {
        rid: {"auto": by_rule_auto.get(rid, 0), "review": by_rule_review.get(rid, 0)}
        for rid in all_rule_ids
    }

    return {
        "projects":        stats.projects,
        "files_scanned":   stats.files_scanned,
        "files_with_hits": len(results),
        "files_changed":   sum(1 for r in results if r.changed),
        "files_review":    sum(1 for r in results if r.review_items),
        "auto_patches":    total_auto,
        "review_items":    total_review,
        "total":           total,
        "automation_rate": round(total_auto / total * 100, 1) if total else 0.0,
        "by_rule":         by_rule,
    }


def _print_summary(stats: ScanStats, mode: str) -> None:
    _load_rule_meta()
    s = _summary(stats)
    w = 52
    print(f"\n{'='*w}")
    print(f"  Modo             : {mode}")
    print(f"  Projetos         : {s['projects']}")
    print(f"  Arquivos         : {s['files_scanned']}")
    print(f"  Ocorrencias      : {s['total']}")
    print(f"  Auto corrigidos  : {s['auto_patches']}")
    print(f"  Pendentes        : {s['review_items']}")
    print(f"  Taxa de automacao: {s['automation_rate']}%")
    if s["by_rule"]:
        print(f"\n  {'Regra':<12} {'P':>3}  {'Auto':>6}  {'Revisao':>7}  Descricao")
        print(f"  {'-'*11} {'-'*3}  {'-'*6}  {'-'*7}  {'-'*28}")
        for rid, counts in s["by_rule"].items():
            meta = _RULE_META.get(rid, {})
            prio = meta.get("priority", 50)
            desc = meta.get("description", "")[:28]
            auto_mark = f"[+{counts['auto']}]"  if counts["auto"]   else "     "
            rev_mark  = f"[!{counts['review']}]" if counts["review"] else "      "
            print(f"  {rid:<12} {prio:>3}  {auto_mark:>6}  {rev_mark:>7}  {desc}")
    print(f"{'='*w}\n")


def _generate_report(stats: ScanStats, out_path: str) -> None:
    _load_rule_meta()
    s = _summary(stats)
    lines = ["# Relatorio de Migracao CNPJ Alfanumerico\n"]
    lines += [
        "| Metrica | Valor |",
        "|---------|-------|",
        f"| Projetos analisados | {s['projects']} |",
        f"| Arquivos | {s['files_scanned']} |",
        f"| Ocorrencias | {s['total']} |",
        f"| Auto corrigidos | {s['auto_patches']} |",
        f"| Pendentes | {s['review_items']} |",
        f"| Taxa de automacao | {s['automation_rate']}% |",
        "",
        "## Ocorrencias por regra\n",
        "| Regra | P | Auto | Revisao | Descricao |",
        "|-------|---|------|---------|-----------|",
    ]
    for rid, counts in s["by_rule"].items():
        meta = _RULE_META.get(rid, {})
        prio = meta.get("priority", 50)
        desc = meta.get("description", "")
        auto_v = f"+{counts['auto']}"   if counts["auto"]   else "-"
        rev_v  = f"!{counts['review']}" if counts["review"] else "-"
        lines.append(f"| `{rid}` | {prio} | {auto_v} | {rev_v} | {desc} |")
    lines.append("")

    for r in sorted(stats.results, key=lambda x: x.filepath):
        if not r.patches and not r.review_items:
            continue
        lines.append(f"## `{r.filepath}`\n")

        if r.patches:
            lines.append("### Aplicado automaticamente\n")
            lines.append("| Linha | Regra | Original | Substituido |")
            lines.append("|-------|-------|----------|-------------|")
            for p in r.patches:
                orig = p.original.strip()[:80].replace("|", "\\|")
                repl = p.replacement.strip()[:80].replace("|", "\\|")
                lines.append(f"| {p.line} | `{p.rule_id}` | `{orig}` | `{repl}` |")
            lines.append("")

        if r.review_items:
            lines.append("### Requer revisao humana\n")
            lines.append("| Linha | Regra | Trecho |")
            lines.append("|-------|-------|--------|")
            for p in r.review_items:
                orig = p.original.strip()[:100].replace("|", "\\|")
                lines.append(f"| {p.line} | `{p.rule_id}` | `{orig}` |")
            lines.append("")

    Path(out_path).write_text("\n".join(lines), encoding="utf-8")
    print(f"Relatorio salvo em: {out_path}")


# ─── comandos ────────────────────────────────────────────────────────────────

def cmd_validate(args: argparse.Namespace) -> None:
    """Executa os testes de cada repo em `path` e exibe o resultado."""
    results = validate_directory(args.path, timeout=args.timeout)

    if not results:
        print(f"Nenhum repo com build tool encontrado em '{args.path}'")
        raise SystemExit(1)

    w = 52
    print(f"\n{'='*w}")
    print(f"  Validate: {args.path}")
    print(f"{'='*w}")

    failed: list[ValidateResult] = []
    for r in results:
        if r.skipped:
            status = "SKIP"
        elif r.success:
            status = "OK  "
        else:
            status = "FAIL"
            failed.append(r)
        duration = f"{r.duration}s" if not r.skipped else "-"
        print(f"  [{status}] {r.repo:<35} {r.tool:<8} {duration}")

    print(f"{'='*w}")
    print(f"  {len(results) - len(failed)} OK  |  {len(failed)} FAIL  |  "
          f"{sum(1 for r in results if r.skipped)} SKIP")
    print(f"{'='*w}\n")

    if failed:
        for r in failed:
            print(f"--- FALHA: {r.repo} ({r.tool}) ---")
            print(r.output[-2000:])
            print()
        raise SystemExit(1)


def cmd_check(args: argparse.Namespace) -> None:
    """Modo CI: exit 0 se nao ha ocorrencias, exit 1 caso contrario."""
    _load_rule_meta()
    paths = _repos_from_args(args)
    rules = _load_rules()

    if paths:
        from migrate.transformer import ScanStats
        combined = ScanStats()
        for p in paths:
            s = transform_directory(p, rules=rules, dry_run=True)
            combined.projects += s.projects
            combined.files_scanned += s.files_scanned
            combined.results.extend(s.results)
        stats = combined
    else:
        stats = transform_directory(args.path, rules=rules, dry_run=True)

    s = _summary(stats)
    total = s["total"]

    if total == 0:
        print(f"OK  Nenhuma ocorrencia encontrada")
        return

    print(f"FAIL  {total} ocorrencia(s) encontrada(s)")
    print(f"      Auto corrigiveis : {s['auto_patches']}")
    print(f"      Revisao humana   : {s['review_items']}")
    if s["by_rule"]:
        for rid, counts in s["by_rule"].items():
            auto_v = f"+{counts['auto']}" if counts["auto"] else ""
            rev_v  = f"!{counts['review']}" if counts["review"] else ""
            parts  = "  ".join(filter(None, [auto_v, rev_v]))
            print(f"      {rid:<12} {parts}")
    raise SystemExit(1)


def _repos_from_args(args: argparse.Namespace) -> list[str] | None:
    """
    Retorna lista de caminhos de repos a partir de --flow ou --from-scan.
    Retorna None se nenhum dos dois foi usado (usa `path` diretamente).
    """
    repos_root = getattr(args, "repos_root", "repos")
    config     = getattr(args, "config", "scanner-config.yaml")

    # --flow tem prioridade sobre --from-scan
    flow = getattr(args, "flow", None)
    if flow:
        try:
            repos = repos_from_flow(flow, repos_root=repos_root, config_path=config)
        except (FileNotFoundError, ValueError) as e:
            print(f"[flow] {e}")
            raise SystemExit(1)
        if not repos:
            print(f"Nenhum repo local encontrado em '{repos_root}' para o fluxo '{flow}'.")
            available = flow_names(config)
            if available:
                print(f"Fluxos disponiveis: {', '.join(available)}")
            raise SystemExit(1)
        print(f"Fluxo '{flow}': {len(repos)} repo(s) -> {', '.join(r.name for r in repos)}")
        return [r.path for r in repos]

    if not getattr(args, "from_scan", None):
        return None

    scan_file = args.from_scan
    repos = repos_from_scan(scan_file, repos_root=repos_root)
    if not repos:
        print(f"Nenhum repo local encontrado em '{repos_root}' para o scan '{scan_file}'.")
        raise SystemExit(1)
    s = summary_from_scan(scan_file)
    print(f"Scan {s['scan_id']} ({s['data']}): {s['repos']} repos, {s['total']} impactos, {s['alta']} Alta")
    print(f"Repos priorizados: {', '.join(r.name for r in repos[:5])}"
          + (f" (+{len(repos)-5})" if len(repos) > 5 else ""))
    return [r.path for r in repos]


def cmd_scan(args: argparse.Namespace) -> None:
    _load_rule_meta()
    paths = _repos_from_args(args)
    rules = _load_rules()

    if paths:
        # Agrega stats de múltiplos repos
        from migrate.transformer import ScanStats
        combined = ScanStats()
        for p in paths:
            print(f"Escaneando: {p}")
            s = transform_directory(p, rules=rules, dry_run=True)
            combined.projects += s.projects
            combined.files_scanned += s.files_scanned
            combined.results.extend(s.results)
        stats = combined
    else:
        print(f"Escaneando: {args.path}")
        stats = transform_directory(args.path, rules=rules, dry_run=True)

    _print_summary(stats, mode="scan (dry-run)")
    _history.record(_summary(stats), command="scan", path=args.path, dry_run=True,
                    scan_json=getattr(args, "from_scan", None))

    if args.json:
        out = {
            "summary": _summary(stats),
            "files": [
                {
                    "filepath": r.filepath,
                    "auto":   [{"line": p.line, "rule": p.rule_id, "original": p.original} for p in r.patches],
                    "review": [{"line": p.line, "rule": p.rule_id, "original": p.original} for p in r.review_items],
                }
                for r in stats.results
            ],
        }
        print(json.dumps(out, ensure_ascii=False, indent=2))


def cmd_fix(args: argparse.Namespace) -> None:
    _load_rule_meta()
    dry   = args.dry_run
    mode  = "fix (dry-run)" if dry else "fix"
    rules = _load_rules()
    paths = _repos_from_args(args)

    if paths:
        from migrate.transformer import ScanStats
        combined = ScanStats()
        for p in paths:
            if not dry:
                try:
                    git_check(p, ci=args.ci)
                except GitDirtyError as e:
                    print(f"[git] {p}: {e}")
                    raise SystemExit(1)
            print(f"{'Simulando' if dry else 'Aplicando'} em: {p}")
            s = transform_directory(p, rules=rules, dry_run=dry)
            combined.projects += s.projects
            combined.files_scanned += s.files_scanned
            combined.results.extend(s.results)
        stats = combined
    else:
        if not dry:
            try:
                git_check(args.path, ci=args.ci)
            except GitDirtyError as e:
                print(f"[git] {e}")
                raise SystemExit(1)
        print(f"{'Simulando' if dry else 'Aplicando'} transformacoes em: {args.path}")
        stats = transform_directory(args.path, rules=rules, dry_run=dry)

    _print_summary(stats, mode=mode)
    _history.record(_summary(stats), command="fix", path=args.path, dry_run=dry,
                    scan_json=getattr(args, "from_scan", None))
    if not dry:
        print("Arquivos modificados em disco. Execute os testes antes de commitar.")


def cmd_history(args: argparse.Namespace) -> None:
    entries = _history.load(args.file)
    _history.print_history(entries, last=args.last)


def cmd_report(args: argparse.Namespace) -> None:
    _load_rule_meta()
    paths = _repos_from_args(args)
    rules = _load_rules()

    if paths:
        from migrate.transformer import ScanStats
        combined = ScanStats()
        for p in paths:
            print(f"Analisando: {p}")
            s = transform_directory(p, rules=rules, dry_run=True)
            combined.projects += s.projects
            combined.files_scanned += s.files_scanned
            combined.results.extend(s.results)
        stats = combined
    else:
        print(f"Gerando relatorio para: {args.path}")
        stats = transform_directory(args.path, rules=rules, dry_run=True)

    flow = getattr(args, "flow", None)
    default_name = f"migration_report_{flow}.md" if flow else "migration_report.md"
    out_md = args.out or default_name
    _generate_report(stats, out_md)
    if args.html:
        out_html = Path(out_md).with_suffix(".html")
        generate_html(stats, _summary(stats), _RULE_META, str(out_html))
    _print_summary(stats, mode="report")


# ─── entry point ─────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        prog="cnpj-migrate",
        description="Migrador automatico CNPJ alfanumerico",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_validate = sub.add_parser("validate", help="Executa os testes dos repos apos o fix")
    p_validate.add_argument("path", help="Diretorio de repos (ex: repos/)")
    p_validate.add_argument("--timeout", type=int, default=300, help="Timeout por repo em segundos (padrao: 300)")
    p_validate.set_defaults(func=cmd_validate)

    p_check = sub.add_parser("check", help="Modo CI: exit 1 se houver ocorrencias nao migradas")
    p_check.add_argument("path", nargs="?", default=".", help="Diretorio a verificar (padrao: .)")
    p_check.add_argument("--flow", metavar="FLUXO", help="Fluxo definido no scanner-config.yaml")
    p_check.add_argument("--config", default="scanner-config.yaml", metavar="CFG", help="Config do scanner (padrao: scanner-config.yaml)")
    p_check.add_argument("--repos-root", default="repos", metavar="DIR", help="Raiz dos repos clonados (padrao: repos/)")
    p_check.set_defaults(func=cmd_check)

    p_scan = sub.add_parser("scan", help="Detecta ocorrencias sem alterar arquivos")
    p_scan.add_argument("path", nargs="?", default=".", help="Diretorio ou arquivo a escanear (padrao: .)")
    p_scan.add_argument("--flow", metavar="FLUXO", help="Fluxo definido no scanner-config.yaml")
    p_scan.add_argument("--config", default="scanner-config.yaml", metavar="CFG", help="Config do scanner (padrao: scanner-config.yaml)")
    p_scan.add_argument("--json", action="store_true", help="Saida em JSON")
    p_scan.add_argument("--from-scan", metavar="JSON", help="JSON do scanner.py para priorizar repos")
    p_scan.add_argument("--repos-root", default="repos", metavar="DIR", help="Raiz dos repos clonados (padrao: repos/)")
    p_scan.set_defaults(func=cmd_scan)

    p_fix = sub.add_parser("fix", help="Aplica transformacoes automaticas")
    p_fix.add_argument("path", nargs="?", default=".", help="Diretorio ou arquivo a transformar (padrao: .)")
    p_fix.add_argument("--flow", metavar="FLUXO", help="Fluxo definido no scanner-config.yaml")
    p_fix.add_argument("--config", default="scanner-config.yaml", metavar="CFG", help="Config do scanner (padrao: scanner-config.yaml)")
    p_fix.add_argument("--dry-run", action="store_true", help="Simula sem escrever em disco")
    p_fix.add_argument("--ci", action="store_true", help="Modo CI: aborta se working tree suja")
    p_fix.add_argument("--from-scan", metavar="JSON", help="JSON do scanner.py para priorizar repos")
    p_fix.add_argument("--repos-root", default="repos", metavar="DIR", help="Raiz dos repos clonados (padrao: repos/)")
    p_fix.set_defaults(func=cmd_fix)

    p_hist = sub.add_parser("history", help="Exibe historico de execucoes do migrador")
    p_hist.add_argument("--file", default="migrate_history.jsonl", help="Arquivo JSONL de historico")
    p_hist.add_argument("--last", type=int, default=20, help="Numero de entradas a exibir (padrao: 20)")
    p_hist.set_defaults(func=cmd_history)

    p_report = sub.add_parser("report", help="Gera relatorio Markdown (e HTML com --html)")
    p_report.add_argument("path", nargs="?", default=".", help="Diretorio a analisar (padrao: .)")
    p_report.add_argument("--flow", metavar="FLUXO", help="Fluxo definido no scanner-config.yaml")
    p_report.add_argument("--config", default="scanner-config.yaml", metavar="CFG", help="Config do scanner (padrao: scanner-config.yaml)")
    p_report.add_argument("--repos-root", default="repos", metavar="DIR", help="Raiz dos repos clonados (padrao: repos/)")
    p_report.add_argument("--out", help="Arquivo de saida (padrao: migration_report.md)")
    p_report.add_argument("--html", action="store_true", help="Gera tambem o relatorio HTML")
    p_report.set_defaults(func=cmd_report)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
