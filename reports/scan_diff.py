"""
Compara dois JSONs de scan e gera um relatório de diff.

Uso:
    python reports/scan_diff.py scan_anterior.json scan_atual.json
    python reports/scan_diff.py scan_anterior.json scan_atual.json --out diff.json
    python reports/scan_diff.py scan_anterior.json scan_atual.json --embed
        (embute o diff no JSON atual como campo "diff" e regenera o dashboard)
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.output import build_diff


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Compara dois scans CNPJ Impact Scanner")
    parser.add_argument("anterior", help="JSON do scan anterior")
    parser.add_argument("atual",    help="JSON do scan atual")
    parser.add_argument("--out",    default=None, help="Arquivo de saída do diff (padrão: diff_<scan_id>.json)")
    parser.add_argument("--embed",  action="store_true",
                        help="Embute o diff no JSON atual e regenera o dashboard HTML")
    args = parser.parse_args()

    ant_path = Path(args.anterior)
    atu_path = Path(args.atual)

    if not ant_path.exists():
        print(f"[erro] Arquivo não encontrado: {ant_path}")
        sys.exit(1)
    if not atu_path.exists():
        print(f"[erro] Arquivo não encontrado: {atu_path}")
        sys.exit(1)

    scan_ant = json.loads(ant_path.read_text(encoding="utf-8"))
    scan_atu = json.loads(atu_path.read_text(encoding="utf-8"))

    diff = build_diff(scan_ant, scan_atu)
    r = diff["resumo"]

    print(f"\n📊 Diff: {diff['scan_id_anterior']} → {diff['scan_id_atual']}")
    print(f"   🔴 Novos:      {r['novos']}")
    print(f"   🟢 Resolvidos: {r['resolvidos']}")
    print(f"   🟡 Alterados:  {r['alterados']}")
    print(f"   ⚪ Mantidos:   {r['mantidos']}")
    delta = r["delta"]
    print(f"   Δ Total:       {'+' if delta > 0 else ''}{delta} ({r['total_anterior']} → {r['total_atual']})\n")

    if args.embed:
        scan_atu["diff"] = diff
        atu_path.write_text(json.dumps(scan_atu, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[ok] Diff embutido em: {atu_path}")

        # Regenera dashboard se existir
        try:
            from reports.dashboard import build_dashboard
            html = build_dashboard(scan_atu)
            html_path = atu_path.with_suffix(".html")
            html_path.write_text(html, encoding="utf-8")
            print(f"[ok] Dashboard atualizado: {html_path}")
        except Exception as e:
            print(f"[aviso] Não foi possível regenerar o dashboard: {e}")
    else:
        out_path = Path(args.out) if args.out else Path(f"diff_{diff['scan_id_atual']}.json")
        out_path.write_text(json.dumps(diff, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[ok] Diff salvo em: {out_path}")


if __name__ == "__main__":
    main()
