"""
report_html.py — gera relatório HTML do migrador CNPJ alfanumérico.

Funcionalidades:
  - Cards de métricas no topo
  - Tabela de regras com contagem auto/revisão
  - Navegação por arquivo com âncoras
  - Filtro por tipo (auto / revisão / todos)
  - Highlight de código inline
  - Zero dependências externas (HTML/CSS/JS puro)
"""

from __future__ import annotations

from html import escape
from pathlib import Path

from migrate.transformer import ScanStats


def _badge(text: str, color: str) -> str:
    return f'<span class="badge" style="background:{color}">{escape(text)}</span>'


def _rule_row(rid: str, counts: dict, meta: dict) -> str:
    prio = meta.get("priority", 50)
    desc = escape(meta.get("description", ""))
    auto_v = f'+{counts["auto"]}' if counts["auto"] else "—"
    rev_v  = f'!{counts["review"]}' if counts["review"] else "—"
    auto_cls = "auto-val" if counts["auto"] else "empty"
    rev_cls  = "rev-val"  if counts["review"] else "empty"
    return (
        f'<tr>'
        f'<td><code>{escape(rid)}</code></td>'
        f'<td class="center">{prio}</td>'
        f'<td class="center {auto_cls}">{auto_v}</td>'
        f'<td class="center {rev_cls}">{rev_v}</td>'
        f'<td>{desc}</td>'
        f'</tr>'
    )


def _patch_rows(patches: list, kind: str) -> str:
    rows = []
    cls  = "auto-row" if kind == "auto" else "rev-row"
    for p in patches:
        orig = escape(p.original.strip()[:120])
        repl = escape(p.replacement.strip()[:120])
        rows.append(
            f'<tr class="{cls}" data-kind="{kind}">'
            f'<td class="center">{p.line}</td>'
            f'<td><code class="rule-tag">{escape(p.rule_id)}</code></td>'
            f'<td><code>{orig}</code></td>'
            f'<td><code>{repl}</code></td>'
            f'</tr>'
        )
    return "\n".join(rows)


def _file_section(r) -> str:
    anchor = escape(r.filepath.replace("\\", "/").replace("/", "_").replace(".", "_"))
    filepath = escape(r.filepath.replace("\\", "/"))
    auto_count = len(r.patches)
    rev_count  = len(r.review_items)

    badges = ""
    if auto_count:
        badges += _badge(f"+{auto_count} auto", "#2e7d32")
    if rev_count:
        badges += _badge(f"!{rev_count} revisão", "#e65100")

    rows = ""
    if r.patches:
        rows += _patch_rows(r.patches, "auto")
    if r.review_items:
        rows += _patch_rows(r.review_items, "review")

    return f"""
<div class="file-card" id="{anchor}">
  <div class="file-header">
    <span class="file-path">{filepath}</span>
    <span class="file-badges">{badges}</span>
  </div>
  <table class="patch-table">
    <thead>
      <tr><th>Linha</th><th>Regra</th><th>Original</th><th>Substituição / Sugestão</th></tr>
    </thead>
    <tbody>
      {rows}
    </tbody>
  </table>
</div>"""


def generate_html(stats: ScanStats, summary: dict, rule_meta: dict, out_path: str) -> None:
    s = summary

    # ── cards de métricas ──────────────────────────────────────────────────
    cards = f"""
<div class="cards">
  <div class="card"><div class="card-val">{s['projects']}</div><div class="card-lbl">Projetos</div></div>
  <div class="card"><div class="card-val">{s['files_scanned']}</div><div class="card-lbl">Arquivos</div></div>
  <div class="card"><div class="card-val">{s['total']}</div><div class="card-lbl">Ocorrências</div></div>
  <div class="card card-auto"><div class="card-val">{s['auto_patches']}</div><div class="card-lbl">Auto corrigidos</div></div>
  <div class="card card-rev"><div class="card-val">{s['review_items']}</div><div class="card-lbl">Revisão humana</div></div>
  <div class="card card-rate"><div class="card-val">{s['automation_rate']}%</div><div class="card-lbl">Taxa automação</div></div>
</div>"""

    # ── tabela de regras ───────────────────────────────────────────────────
    rule_rows = "\n".join(
        _rule_row(rid, counts, rule_meta.get(rid, {}))
        for rid, counts in s["by_rule"].items()
    )
    rules_table = f"""
<h2>Ocorrências por regra</h2>
<table class="rule-table">
  <thead><tr><th>Regra</th><th>P</th><th>Auto</th><th>Revisão</th><th>Descrição</th></tr></thead>
  <tbody>{rule_rows}</tbody>
</table>"""

    # ── índice de arquivos ─────────────────────────────────────────────────
    index_items = []
    for r in sorted(stats.results, key=lambda x: x.filepath):
        anchor   = escape(r.filepath.replace("\\", "/").replace("/", "_").replace(".", "_"))
        filepath = escape(r.filepath.replace("\\", "/"))
        tags = ""
        if r.patches:
            tags += f'<span class="badge" style="background:#2e7d32">+{len(r.patches)}</span>'
        if r.review_items:
            tags += f'<span class="badge" style="background:#e65100">!{len(r.review_items)}</span>'
        index_items.append(f'<li><a href="#{anchor}">{filepath}</a> {tags}</li>')

    file_index = f"""
<h2>Arquivos ({len(stats.results)})</h2>
<div class="filter-bar">
  Filtrar:
  <button onclick="filterRows('all')"   class="btn-filter active" id="f-all">Todos</button>
  <button onclick="filterRows('auto')"  class="btn-filter" id="f-auto">Auto</button>
  <button onclick="filterRows('review')" class="btn-filter" id="f-review">Revisão</button>
</div>
<ul class="file-index">{''.join(index_items)}</ul>"""

    # ── seções por arquivo ─────────────────────────────────────────────────
    file_sections = "\n".join(
        _file_section(r)
        for r in sorted(stats.results, key=lambda x: x.filepath)
        if r.patches or r.review_items
    )

    html = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Migração CNPJ Alfanumérico</title>
<style>
  *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: system-ui, sans-serif; background: #f5f5f5; color: #212121; }}
  header {{ background: #1565c0; color: #fff; padding: 1.2rem 2rem; }}
  header h1 {{ font-size: 1.3rem; font-weight: 600; }}
  main {{ max-width: 1200px; margin: 0 auto; padding: 1.5rem 1rem; }}
  h2 {{ font-size: 1rem; font-weight: 600; margin: 1.8rem 0 .6rem; color: #1565c0; text-transform: uppercase; letter-spacing: .05em; }}

  /* cards */
  .cards {{ display: flex; flex-wrap: wrap; gap: .75rem; margin-bottom: 1.5rem; }}
  .card {{ background: #fff; border-radius: 8px; padding: .9rem 1.2rem; min-width: 120px;
           box-shadow: 0 1px 3px rgba(0,0,0,.12); flex: 1; }}
  .card-val {{ font-size: 1.8rem; font-weight: 700; color: #1565c0; }}
  .card-lbl {{ font-size: .75rem; color: #757575; margin-top: .2rem; }}
  .card-auto .card-val {{ color: #2e7d32; }}
  .card-rev  .card-val {{ color: #e65100; }}
  .card-rate .card-val {{ color: #6a1b9a; }}

  /* tabela de regras */
  .rule-table {{ width: 100%; border-collapse: collapse; background: #fff;
                 border-radius: 8px; overflow: hidden; box-shadow: 0 1px 3px rgba(0,0,0,.12); }}
  .rule-table th {{ background: #1565c0; color: #fff; padding: .5rem .75rem; font-size: .8rem; text-align: left; }}
  .rule-table td {{ padding: .45rem .75rem; font-size: .82rem; border-bottom: 1px solid #f0f0f0; }}
  .rule-table tr:last-child td {{ border-bottom: none; }}
  .auto-val {{ color: #2e7d32; font-weight: 600; }}
  .rev-val  {{ color: #e65100; font-weight: 600; }}
  .empty    {{ color: #bdbdbd; }}
  .center   {{ text-align: center; }}

  /* filtro */
  .filter-bar {{ margin: .5rem 0 .75rem; display: flex; align-items: center; gap: .5rem; font-size: .85rem; }}
  .btn-filter {{ border: 1px solid #1565c0; background: #fff; color: #1565c0;
                 padding: .25rem .75rem; border-radius: 20px; cursor: pointer; font-size: .8rem; }}
  .btn-filter.active {{ background: #1565c0; color: #fff; }}

  /* índice */
  .file-index {{ list-style: none; columns: 2; gap: 1rem; margin-bottom: 1rem; }}
  .file-index li {{ font-size: .82rem; padding: .15rem 0; break-inside: avoid; }}
  .file-index a {{ color: #1565c0; text-decoration: none; }}
  .file-index a:hover {{ text-decoration: underline; }}

  /* badge */
  .badge {{ display: inline-block; color: #fff; font-size: .7rem; font-weight: 600;
            padding: .1rem .4rem; border-radius: 10px; margin-left: .25rem; }}

  /* cards de arquivo */
  .file-card {{ background: #fff; border-radius: 8px; margin-bottom: 1rem;
                box-shadow: 0 1px 3px rgba(0,0,0,.12); overflow: hidden; }}
  .file-header {{ display: flex; justify-content: space-between; align-items: center;
                  padding: .6rem 1rem; background: #e3f2fd; border-bottom: 1px solid #bbdefb; }}
  .file-path {{ font-size: .82rem; font-weight: 600; color: #0d47a1; word-break: break-all; }}
  .file-badges {{ white-space: nowrap; }}

  /* tabela de patches */
  .patch-table {{ width: 100%; border-collapse: collapse; font-size: .8rem; }}
  .patch-table th {{ background: #f5f5f5; padding: .4rem .75rem; text-align: left;
                     font-size: .75rem; color: #616161; border-bottom: 1px solid #e0e0e0; }}
  .patch-table td {{ padding: .4rem .75rem; border-bottom: 1px solid #f5f5f5;
                     vertical-align: top; word-break: break-all; }}
  .patch-table tr:last-child td {{ border-bottom: none; }}
  .auto-row {{ background: #f1f8e9; }}
  .rev-row  {{ background: #fff3e0; }}
  .rule-tag {{ background: #e8eaf6; color: #283593; padding: .1rem .35rem; border-radius: 4px; }}
  code {{ font-family: "Cascadia Code", "Fira Code", monospace; font-size: .78rem; }}
</style>
</head>
<body>
<header>
  <h1>Migração CNPJ Alfanumérico — Relatório</h1>
</header>
<main>
  {cards}
  {rules_table}
  {file_index}
  <h2>Detalhes por arquivo</h2>
  {file_sections}
</main>
<script>
function filterRows(kind) {{
  document.querySelectorAll('.btn-filter').forEach(b => b.classList.remove('active'));
  document.getElementById('f-' + kind).classList.add('active');
  document.querySelectorAll('tr[data-kind]').forEach(tr => {{
    tr.style.display = (kind === 'all' || tr.dataset.kind === kind) ? '' : 'none';
  }});
  // Oculta cards de arquivo que ficaram sem linhas visíveis
  document.querySelectorAll('.file-card').forEach(card => {{
    const visible = card.querySelectorAll('tr[data-kind]:not([style*="none"])').length;
    card.style.display = visible ? '' : 'none';
  }});
}}
</script>
</body>
</html>"""

    Path(out_path).write_text(html, encoding="utf-8")
    print(f"Relatorio HTML salvo em: {out_path}")
