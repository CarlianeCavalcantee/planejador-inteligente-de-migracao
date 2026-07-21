# dashboard.py
import json
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _badge(complexidade: str) -> str:
    colors = {"Alta": "#ef4444", "Média": "#f59e0b", "Baixa": "#22c55e"}
    c = colors.get(complexidade, "#6b7280")
    return f'<span style="background:{c};color:#fff;padding:2px 8px;border-radius:9999px;font-size:11px;font-weight:600">{complexidade}</span>'

def _dual_badge(val: bool) -> str:
    return '<span style="color:#3b82f6;font-weight:700">✔ Dual</span>' if val else '<span style="color:#9ca3af">—</span>'

def _prio_badge(p: str) -> str:
    colors = {"P1": ("#fef2f2","#ef4444"), "P2": ("#fffbeb","#f59e0b"), "P3": ("#f0fdf4","#22c55e")}
    bg, fg = colors.get(p, ("#f3f4f6","#6b7280"))
    return f'<span style="background:{bg};color:{fg};padding:2px 8px;border-radius:9999px;font-size:11px;font-weight:700;border:1px solid {fg}33">{p}</span>'

def _status_badge(s: str) -> str:
    cfg = {"pendente": ("#fef3c7","#92400e","⏳"), "em_andamento": ("#dbeafe","#1e40af","🔄"), "em_progresso": ("#dbeafe","#1e40af","🔄"), "resolvido": ("#d1fae5","#065f46","✅"), "falso_positivo": ("#f1f5f9","#475569","🚫")}
    bg, fg, icon = cfg.get(s, ("#f3f4f6","#374151","•"))
    return f'<span style="background:{bg};color:{fg};padding:2px 8px;border-radius:9999px;font-size:11px;font-weight:600">{icon} {s}</span>'

def _alinhamento_badge(s: str) -> str:
    cfg = {"pendente": ("#fef3c7","#92400e","⏳"), "confirmado": ("#d1fae5","#065f46","✅"), "em_negociacao": ("#dbeafe","#1e40af","🔄"), "bloqueado": ("#fee2e2","#991b1b","🚫")}
    bg, fg, icon = cfg.get(s, ("#fef3c7","#92400e","⏳"))
    return f'<span style="background:{bg};color:{fg};padding:3px 10px;border-radius:9999px;font-size:11px;font-weight:600">{icon} {s}</span>'

def _short(path: str, n: int = 55) -> str:
    return ("…" + path[-(n-1):]) if len(path) > n else path

def _build_trilhas_html(trilhas_data: dict) -> str:
    if not trilhas_data:
        return ""

    grupos  = trilhas_data["grupos"]
    deps    = trilhas_data.get("dependencias_cruzadas", [])
    n_init  = trilhas_data["n_trilhas"]

    # Serializa grupos para JS — o recálculo acontece inteiramente no browser
    grupos_js = json.dumps([
        {
            "totalAlta": g["total_alta"],
            "totalImpactos": g["total_impactos"],
            "perfil": g["perfil"],
            "fluxos": g.get("fluxos", []),
            "repos": [
                {"modulo": r["modulo"], "passo": r["passo"],
                 "alta": r["alta"], "total": r["total"], "perfil": g["perfil"],
                 "fluxos": r.get("fluxos", [])}
                for r in g["repositorios"]
            ],
        }
        for g in grupos
    ])

    partidos_js = json.dumps(trilhas_data.get("fluxos_partidos", []))
    grafo_js    = json.dumps(trilhas_data.get("grafo_dependencias", {"nos": [], "arestas": []}))

    deps_html = ""
    if deps:
        dep_items = "".join(
            f'<li style="margin-bottom:6px"><strong>{d["area"]}</strong>: '
            + ", ".join(f'<code style="background:#fef3c7;color:#92400e;padding:1px 6px;border-radius:4px;font-size:11px">{m}</code>' for m in d["repositorios"])
            + " &#8212; definir quem faz a migration/vers&#227;o de API primeiro.</li>"
            for d in deps
        )
        deps_html = f"""
        <div id="trilhas-deps" style="background:#fef3c7;border:1px solid #fcd34d;border-radius:8px;padding:12px 16px;margin-top:16px">
          <div style="font-weight:700;color:#92400e;margin-bottom:8px">&#9888;&#65039; Coordenar antes do merge</div>
          <ul style="margin:0;padding-left:18px;font-size:12px;color:#78350f">{dep_items}</ul>
        </div>"""

    # Tabela de grupos (estática — os grupos não mudam com o seletor)
    grupo_rows = ""
    for g in grupos:
        repos_tags = " ".join(
            f'<code style="background:#e0e7ff;color:#4338ca;padding:1px 6px;border-radius:4px;font-size:11px">{r["modulo"]}</code>'
            for r in g["repositorios"]
        )
        grupo_rows += (
            f'<tr>'
            f'<td style="text-align:center;font-weight:700;color:#6366f1">{g["grupo"]}</td>'
            f'<td><span style="background:#ede9fe;color:#5b21b6;padding:2px 8px;border-radius:6px;font-size:11px;font-weight:600">{g["perfil"]}</span></td>'
            f'<td style="line-height:2">{repos_tags}</td>'
            f'<td style="text-align:center;font-weight:700;color:#ef4444">{g["total_alta"]}</td>'
            f'<td style="text-align:center;color:#6b7280">{g["total_impactos"]}</td>'
            f'</tr>'
        )

    return f"""
  <div class="section" id="sec-trilhas">
    <details open>
    <summary style="list-style:none;cursor:pointer;display:flex;align-items:center;justify-content:space-between;margin-bottom:16px">
      <h2 style="margin:0">&#128256; Divis&#227;o em Trilhas Paralelas</h2>
      <span style="font-size:16px;color:#94a3b8">&#9662;</span>
    </summary>

    <div style="display:flex;align-items:center;gap:12px;margin-bottom:16px;flex-wrap:wrap">
      <label style="font-size:12px;font-weight:600;color:#475569">N&#250;mero de trilhas:</label>
      <div style="display:flex;gap:6px">
        <button onclick="setTrilhas(1)" class="trilha-btn" data-n="1">1</button>
        <button onclick="setTrilhas(2)" class="trilha-btn" data-n="2">2</button>
        <button onclick="setTrilhas(3)" class="trilha-btn" data-n="3">3</button>
        <button onclick="setTrilhas(4)" class="trilha-btn" data-n="4">4</button>
        <button onclick="setTrilhas(5)" class="trilha-btn" data-n="5">5</button>
      </div>
      <span id="trilhas-delta" style="font-size:11px;color:#64748b"></span>
    </div>

    <div style="display:flex;gap:20px;flex-wrap:wrap;margin-bottom:20px;align-items:flex-start">
      <div style="min-width:220px;max-width:360px">
        <div style="font-size:12px;font-weight:600;color:#475569;margin-bottom:8px">Carga por trilha (impactos dif&#237;ceis)</div>
        <canvas id="chartTrilhas" height="160"></canvas>
      </div>
    </div>

    <div id="trilhas-cards" style="display:flex;gap:16px;flex-wrap:wrap;margin-bottom:24px"></div>
    <div id="trilhas-partidos"></div>

    <h3 style="font-size:13px;font-weight:600;color:#475569;margin-bottom:8px">&#128279; Dependências entre Trilhas</h3>
    <div id="trilhas-grafo" style="margin-bottom:20px"></div>

    <h3 style="font-size:13px;font-weight:600;color:#475569;margin-bottom:10px">Grupos de Repos com Perfil Parecido</h3>
    <div style="overflow-x:auto">
      <table class="imp-table">
        <thead><tr>
          <th style="text-align:center">Grupo</th><th>Perfil de &#193;reas</th>
          <th>Reposit&#243;rios</th><th style="text-align:center">Dif&#237;ceis</th><th style="text-align:center">Total</th>
        </tr></thead>
        <tbody>{grupo_rows}</tbody>
      </table>
    </div>
    {deps_html}
    </details>
  </div>

  <style>
  .trilha-btn{{padding:5px 14px;border:1px solid #e2e8f0;border-radius:8px;background:#fff;cursor:pointer;font-size:13px;font-weight:600;color:#475569;transition:all .15s}}
  .trilha-btn:hover{{background:#f1f5f9}}
  .trilha-btn.active{{background:#1e293b;color:#fff;border-color:#1e293b}}
  </style>

  <script>
  (function() {{
    const COLORS = ['#6366f1','#10b981','#f59e0b','#ef4444','#3b82f6','#8b5cf6','#ec4899','#14b8a6'];
    const GRUPOS = {grupos_js};
    const PARTIDOS = {partidos_js};
    const GRAFO = {grafo_js};
    let trilhasChart = null;

    function dividir(n) {{
      const trilhas = Array.from({{length: n}}, (_,i) => ({{t: i+1, repos: [], alta: 0, total: 0, fluxosCompletos: []}}));
      const carga   = new Array(n).fill(0);
      [...GRUPOS].sort((a,b) => b.totalAlta - a.totalAlta).forEach(g => {{
        const t = carga.indexOf(Math.min(...carga));
        trilhas[t].repos.push(...g.repos);
        trilhas[t].alta  += g.totalAlta;
        trilhas[t].total += g.totalImpactos;
        carga[t] += g.totalAlta;
      }});
      trilhas.forEach(t => t.repos.sort((a,b) => a.passo - b.passo));
      // calcular fluxos completos (todos os repos do fluxo na mesma trilha)
      const fluxoTrilhas = {{}};
      trilhas.forEach(t => t.repos.forEach(r => (r.fluxos||[]).forEach(f => {{
        if (!fluxoTrilhas[f]) fluxoTrilhas[f] = new Set();
        fluxoTrilhas[f].add(t.t);
      }})));
      trilhas.forEach(t => {{
        t.fluxosCompletos = Object.entries(fluxoTrilhas)
          .filter(([f, ts]) => ts.size === 1 && [...ts][0] === t.t)
          .map(([f]) => f).sort();
      }});
      return trilhas;
    }}

    function renderCards(trilhas) {{
      const wrap = document.getElementById('trilhas-cards');
      wrap.innerHTML = '';
      // fluxos partidos para esta distribuição
      const fluxoTrilhas = {{}};
      trilhas.forEach(t => t.repos.forEach(r => (r.fluxos||[]).forEach(f => {{
        if (!fluxoTrilhas[f]) fluxoTrilhas[f] = new Set();
        fluxoTrilhas[f].add(t.t);
      }})));
      const partidosAtivos = Object.entries(fluxoTrilhas)
        .filter(([,ts]) => ts.size > 1)
        .map(([f, ts]) => ({{fluxo: f, trilhas: [...ts].sort()}}));

      trilhas.forEach((t, i) => {{
        const c = COLORS[i % COLORS.length];
        const rows = t.repos.map(r => {{
          const fluxoTags = (r.fluxos || []).map(f => {{
            const partido = fluxoTrilhas[f] && fluxoTrilhas[f].size > 1;
            return `<span style="background:${{partido?'#fef3c7':'#f0fdf4'}};color:${{partido?'#92400e':'#065f46'}};padding:1px 6px;border-radius:4px;font-size:10px;white-space:nowrap${{partido?' border:1px solid #fcd34d':''}}">${{f}}${{partido?' ⚠️':''}}</span>`;
          }}).join(' ');
          return `<tr>
            <td style="text-align:center;color:#6b7280;font-size:11px">${{r.passo}}</td>
            <td style="font-weight:600;font-size:12px"><code style="background:#e0e7ff;color:#4338ca;padding:1px 6px;border-radius:4px">${{r.modulo}}</code></td>
            <td style="text-align:center;font-weight:700;color:#ef4444">${{r.alta}}</td>
            <td style="text-align:center;color:#6b7280">${{r.total}}</td>
            <td style="font-size:11px;color:#5b21b6">${{r.perfil}}</td>
            <td style="line-height:1.8">${{fluxoTags || '<span style="color:#9ca3af">&#8212;</span>'}}</td>
          </tr>`;
        }}).join('');
        const completosPills = t.fluxosCompletos.map(f =>
          `<span style="background:#f0fdf4;color:#065f46;border:1px solid #bbf7d0;padding:2px 8px;border-radius:9999px;font-size:11px">${{f}}</span>`
        ).join(' ');
        wrap.innerHTML += `
          <div style="flex:1;min-width:300px;border:2px solid ${{c}}22;border-radius:12px;overflow:hidden">
            <div style="background:${{c}};color:#fff;padding:12px 16px;display:flex;align-items:center;justify-content:space-between">
              <span style="font-weight:700;font-size:14px">Trilha ${{t.t}}</span>
              <div style="text-align:right">
                <div style="font-size:18px;font-weight:800">${{t.alta}}</div>
                <div style="font-size:10px;opacity:.8">impactos dif&#237;ceis</div>
              </div>
            </div>
            <div style="padding:12px;background:#fafafa">
              <div style="font-size:11px;color:#64748b;margin-bottom:8px">${{t.total}} impactos &middot; ${{t.repos.length}} repos</div>
              ${{t.fluxosCompletos.length ? `<div style="margin-bottom:10px"><span style="font-size:11px;font-weight:700;color:#065f46">&#10003; Fluxos completos nesta trilha:</span><div style="display:flex;flex-wrap:wrap;gap:4px;margin-top:4px">${{completosPills}}</div></div>` : ''}}
              <div style="overflow-x:auto">
                <table class="imp-table">
                  <thead><tr>
                    <th style="text-align:center">Ordem</th><th>Repo</th>
                    <th style="text-align:center">Dif&#237;ceis</th><th style="text-align:center">Total</th><th>&#193;reas</th><th>Fluxos</th>
                  </tr></thead>
                  <tbody>${{rows}}</tbody>
                </table>
              </div>
            </div>
          </div>`;
      }});

      // painel de fluxos partidos
      const partidosEl = document.getElementById('trilhas-partidos');
      if (partidosEl) {{
        if (partidosAtivos.length) {{
          const _gColor = {{Crítico:'#991b1b', Alto:'#c2410c', Médio:'#92400e', Baixo:'#065f46'}};
          const _gBg    = {{Crítico:'#fee2e2', Alto:'#ffedd5', Médio:'#fef3c7', Baixo:'#f0fdf4'}};
          const _gIcon  = {{Crítico:'🔴', Alto:'🟠', Médio:'🟡', Baixo:'🟢'}};
          const items = partidosAtivos.map(p => {{
            const g = p.gravidade || '';
            const badge = g ? `<span style="background:${{_gBg[g]||'#fef3c7'}};color:${{_gColor[g]||'#92400e'}};padding:1px 8px;border-radius:9999px;font-size:10px;font-weight:700;border:1px solid ${{_gColor[g]||'#92400e'}}33">${{_gIcon[g]||''}} ${{g}}</span>` : '';
            const repos = (p.repositorios||[]).map(r=>`<code style="background:#fef3c7;color:#92400e;padding:1px 5px;border-radius:4px;font-size:10px">${{r}}</code>`).join(' ');
            return `<li style="margin-bottom:8px;display:flex;align-items:flex-start;gap:8px">${{badge}}<span><strong>${{p.fluxo}}</strong> — partido entre Trilha${{p.trilhas.length>1?'s':''}} ${{p.trilhas.map(t=>'<strong>'+t+'</strong>').join(' e ')}} (${{p.n_repositorios||p.repositorios?.length||'?'}} repos) — ${{repos}}</span></li>`;
          }}).join('');
          partidosEl.innerHTML = `<div style="background:#fef3c7;border:1px solid #fcd34d;border-radius:8px;padding:12px 16px;margin-top:16px"><div style="font-weight:700;color:#92400e;margin-bottom:8px">⚠️ Fluxos partidos entre trilhas — coordenar entrega</div><ul style="margin:0;padding-left:0;list-style:none;font-size:12px;color:#78350f">${{items}}</ul></div>`;
          partidosEl.style.display = '';
        }} else {{
          partidosEl.innerHTML = '';
          partidosEl.style.display = 'none';
        }}
      }}
    }}

    function renderChart(trilhas) {{
      const ctx = document.getElementById('chartTrilhas');
      if (!ctx) return;
      const labels = trilhas.map(t => 'Trilha ' + t.t);
      const values = trilhas.map(t => t.alta);
      const colors = trilhas.map((_,i) => COLORS[i % COLORS.length]);
      if (trilhasChart) trilhasChart.destroy();
      trilhasChart = new Chart(ctx.getContext('2d'), {{
        type: 'bar',
        data: {{ labels, datasets: [{{ data: values, backgroundColor: colors, borderRadius: 6, borderSkipped: false }}] }},
        options: {{ plugins: {{ legend: {{ display: false }} }}, scales: {{ y: {{ beginAtZero: true, grid: {{ color: '#f1f5f9' }} }}, x: {{ grid: {{ display: false }} }} }} }}
      }});
    }}

    function renderDelta(trilhas) {{
      const cargas = trilhas.map(t => t.alta);
      const max = Math.max(...cargas), min = Math.min(...cargas);
      const total = cargas.reduce((a,b) => a+b, 0);
      const pct = total ? Math.round((max - min) / total * 100) : 0;
      const el = document.getElementById('trilhas-delta');
      if (el) el.textContent = 'Desequil&#237;brio: ' + pct + '% — quanto menor, mais equilibrado';
    }}

    window.setTrilhas = function(n) {{
      document.querySelectorAll('.trilha-btn').forEach(b => b.classList.toggle('active', +b.dataset.n === n));
      const trilhas = dividir(n);
      renderCards(trilhas);
      renderChart(trilhas);
      renderDelta(trilhas);
      renderGrafo(trilhas);
    }};

    function renderGrafo(trilhas) {{
      const el = document.getElementById('trilhas-grafo');
      if (!el) return;
      // recalcula arestas para a distribuição atual
      const repoTrilha = {{}};
      trilhas.forEach(t => t.repos.forEach(r => repoTrilha[r.modulo] = t.t));
      const arestas = {{}}; // "de-para" -> motivos[]
      (GRAFO.arestas || []).forEach(a => {{
        // remapeia de/para para a distribuição atual via fluxos partidos
        const key = a.de + '->' + a.para;
        if (!arestas[key]) arestas[key] = {{de: a.de, para: a.para, motivos: []}};
        arestas[key].motivos.push(...a.motivos);
      }});
      const lista = Object.values(arestas);
      if (!lista.length) {{
        el.innerHTML = '<span style="font-size:12px;color:#9ca3af">Nenhuma dependência entre trilhas detectada.</span>';
        return;
      }}
      const COLORS = ['#6366f1','#10b981','#f59e0b','#ef4444','#3b82f6','#8b5cf6','#ec4899','#14b8a6'];
      // renderiza como lista de arestas com seta
      el.innerHTML = lista.map(a => {{
        const c1 = COLORS[(a.de-1) % COLORS.length];
        const c2 = COLORS[(a.para-1) % COLORS.length];
        const motivos = a.motivos.slice(0,3).join('; ') + (a.motivos.length > 3 ? ` (+${{a.motivos.length-3}})` : '');
        return `<div style="display:flex;align-items:center;gap:10px;padding:8px 12px;background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;margin-bottom:6px;flex-wrap:wrap">
          <span style="background:${{c1}};color:#fff;padding:3px 12px;border-radius:9999px;font-size:12px;font-weight:700">Trilha ${{a.de}}</span>
          <span style="font-size:18px;color:#94a3b8">→</span>
          <span style="background:${{c2}};color:#fff;padding:3px 12px;border-radius:9999px;font-size:12px;font-weight:700">Trilha ${{a.para}}</span>
          <span style="font-size:11px;color:#64748b;flex:1">${{motivos}}</span>
        </div>`;
      }}).join('');
    }}

    // inicializa com o valor do scan
    setTrilhas({n_init});
  }})();
  </script>"""


def _build_diff_html(diff: dict | None) -> str:
    if not diff:
        return ""
    r = diff["resumo"]
    delta = r["delta"]
    delta_str = f'+{delta}' if delta > 0 else str(delta)
    delta_color = "#ef4444" if delta > 0 else "#10b981" if delta < 0 else "#6b7280"

    def _rows(items: list, tag_color: str, tag_label: str) -> str:
        out = ""
        for m in items[:100]:
            ev = m["evidencia"]
            ant = m.get("_anterior", {})
            ant_str = ""
            if ant:
                ant_str = (f'<span style="font-size:10px;color:#92400e;background:#fef3c7;'
                           f'padding:1px 6px;border-radius:4px">'
                           f'{ant["complexidade"]} / {ant["area"][:10]}</span> → ')
            out += f"""
            <tr>
              <td><span style="background:{tag_color}22;color:{tag_color};padding:1px 8px;
                border-radius:9999px;font-size:10px;font-weight:700;border:1px solid {tag_color}44">{tag_label}</span></td>
              <td style="font-size:11px"><code style="background:#e0e7ff;color:#4338ca;padding:1px 5px;border-radius:4px">{m['repositorio']}</code></td>
              <td style="font-family:monospace;font-size:10px;color:#6b7280">{ev['arquivo'].split('/')[-1]}:{ev['linha']}</td>
              <td>{ant_str}<span style="background:#ede9fe;color:#5b21b6;padding:1px 6px;border-radius:4px;font-size:10px">{m['area'][:14]}</span></td>
              <td style="font-size:10px;color:#374151">{m['descricao_impacto'][:70]}{'...' if len(m['descricao_impacto'])>70 else ''}</td>
            </tr>"""
        if len(items) > 100:
            out += f'<tr><td colspan="5" style="text-align:center;color:#9ca3af;font-size:11px">+{len(items)-100} itens (ver JSON)</td></tr>'
        return out

    rows_novos     = _rows(diff["novos"],     "#ef4444", "Novo")
    rows_resolvidos = _rows(diff["resolvidos"], "#10b981", "Resolvido")
    rows_alterados  = _rows(diff["alterados"],  "#f59e0b", "Alterado")

    return f"""
  <div class="section" id="sec-diff">
    <details open>
    <summary style="list-style:none;cursor:pointer;display:flex;align-items:center;justify-content:space-between;margin-bottom:16px">
      <h2 style="margin:0">&#128260; Compara&ccedil;&atilde;o entre Scans</h2>
      <span style="font-size:16px;color:#94a3b8">&#9662;</span>
    </summary>
    <div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;padding:12px 16px;font-size:12px;margin-bottom:14px;display:flex;gap:24px;flex-wrap:wrap;align-items:center">
      <span style="color:#64748b">Anterior: <code style="background:#e0e7ff;color:#4338ca;padding:1px 6px;border-radius:4px">{diff['scan_id_anterior']}</code></span>
      <span style="font-size:16px;color:#94a3b8">→</span>
      <span style="color:#64748b">Atual: <code style="background:#e0e7ff;color:#4338ca;padding:1px 6px;border-radius:4px">{diff['scan_id_atual']}</code></span>
      <span style="margin-left:auto;font-size:18px;font-weight:800;color:{delta_color}">{delta_str} impactos</span>
    </div>
    <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:16px">
      <div style="background:#fee2e2;border-radius:10px;padding:12px 16px;border-left:4px solid #ef4444">
        <div style="font-size:22px;font-weight:800;color:#991b1b">{r['novos']}</div>
        <div style="font-size:11px;color:#991b1b">Novos</div>
      </div>
      <div style="background:#d1fae5;border-radius:10px;padding:12px 16px;border-left:4px solid #10b981">
        <div style="font-size:22px;font-weight:800;color:#065f46">{r['resolvidos']}</div>
        <div style="font-size:11px;color:#065f46">Resolvidos</div>
      </div>
      <div style="background:#fef3c7;border-radius:10px;padding:12px 16px;border-left:4px solid #f59e0b">
        <div style="font-size:22px;font-weight:800;color:#92400e">{r['alterados']}</div>
        <div style="font-size:11px;color:#92400e">Alterados</div>
      </div>
      <div style="background:#f1f5f9;border-radius:10px;padding:12px 16px;border-left:4px solid #94a3b8">
        <div style="font-size:22px;font-weight:800;color:#475569">{r['mantidos']}</div>
        <div style="font-size:11px;color:#475569">Mantidos</div>
      </div>
    </div>
    {'<div style="overflow-x:auto"><table class="imp-table"><thead><tr><th>Status</th><th>Repo</th><th>Arquivo:Linha</th><th>Área</th><th>Descrição</th></tr></thead><tbody>' + rows_novos + rows_resolvidos + rows_alterados + '</tbody></table></div>' if (diff['novos'] or diff['resolvidos'] or diff['alterados']) else '<div style="color:#9ca3af;text-align:center;padding:20px">Nenhuma alteração detectada entre os scans.</div>'}
    </details>
  </div>"""


def _build_esforco_html(esforco: list) -> str:
    if not esforco:
        return ""
    dias_total = sum(e["dias_estimados"] for e in esforco)
    sp_total   = sum(e["story_points"] for e in esforco)
    max_dias   = max(e["dias_estimados"] for e in esforco) or 1
    rows = ""
    for e in esforco:
        bar_w = round(e["dias_estimados"] / max_dias * 100)
        dual_badge = '<span style="color:#3b82f6;font-weight:700;font-size:11px">✔ Dual</span>' if e["requer_dual"] else '<span style="color:#9ca3af">—</span>'
        maior_area = e["esforco_por_area"][0]["area"] if e["esforco_por_area"] else "—"
        area_tags = " ".join(
            f'<span style="background:#ede9fe;color:#5b21b6;padding:1px 6px;border-radius:4px;font-size:10px">'
            f'{a["area"][:12]} {a["dias"]}d</span>'
            for a in e["esforco_por_area"][:3]
        )
        sp_color = "#ef4444" if e["story_points"] >= 13 else "#f59e0b" if e["story_points"] >= 5 else "#10b981"
        rows += f"""
        <tr>
          <td style="text-align:center;font-weight:700;color:#6366f1">{e['passo']}</td>
          <td><code style="background:#e0e7ff;color:#4338ca;padding:1px 6px;border-radius:4px">{e['modulo']}</code></td>
          <td style="min-width:130px">
            <div style="display:flex;align-items:center;gap:6px">
              <div style="flex:1;background:#e2e8f0;border-radius:9999px;height:6px">
                <div style="width:{bar_w}%;background:#6366f1;border-radius:9999px;height:6px"></div>
              </div>
              <span style="font-weight:700;color:#475569;min-width:32px;font-size:11px">{e['dias_estimados']}d</span>
            </div>
          </td>
          <td style="text-align:center">
            <span style="background:{sp_color}22;color:{sp_color};padding:2px 10px;border-radius:9999px;font-size:12px;font-weight:800;border:1px solid {sp_color}44">{e['story_points']}</span>
          </td>
          <td style="text-align:center">{dual_badge}</td>
          <td style="line-height:2">{area_tags}</td>
        </tr>"""
    return f"""
  <div class="section" id="sec-esforco">
    <details open>
    <summary style="list-style:none;cursor:pointer;display:flex;align-items:center;justify-content:space-between;margin-bottom:16px">
      <h2 style="margin:0">&#9201;&#65039; Estimativa de Esfor&ccedil;o por M&oacute;dulo</h2>
      <span style="font-size:16px;color:#94a3b8">&#9662;</span>
    </summary>
    <div style="background:#eff6ff;border:1px solid #bfdbfe;border-radius:8px;padding:10px 14px;font-size:12px;color:#1e40af;margin-bottom:14px;display:flex;gap:24px;flex-wrap:wrap">
      <span>&#8505;&#65039; F&oacute;rmula: &Sigma;(dias por impacto &times; fator dual) + overhead fixo (2 dias). Story points em escala Fibonacci.</span>
      <span style="font-weight:700">Total: {dias_total:.1f} dias &nbsp;|&nbsp; {sp_total} SP</span>
    </div>
    <div style="overflow-x:auto">
      <table class="imp-table">
        <thead><tr>
          <th style="text-align:center">Sprint</th>
          <th>M&oacute;dulo</th>
          <th>Dias Estimados</th>
          <th style="text-align:center">Story Points</th>
          <th style="text-align:center">Dual</th>
          <th>Esfor&ccedil;o por &Aacute;rea (top 3)</th>
        </tr></thead>
        <tbody>{rows}</tbody>
      </table>
    </div>
    </details>
  </div>"""


def _build_criterios_html(criterios: list) -> str:
    if not criterios:
        return ""
    cards = ""
    for c in criterios:
        area_blocks = ""
        for ca in c["criterios_por_area"]:
            items = "".join(
                f'<li style="margin-bottom:4px;display:flex;align-items:flex-start;gap:6px">'
                f'<input type="checkbox" style="margin-top:2px;flex-shrink:0">'
                f'<span style="font-size:12px;color:#374151">{cr}</span></li>'
                for cr in ca["criterios"]
            )
            area_blocks += (
                f'<div style="margin-bottom:10px">'
                f'<div style="font-size:11px;font-weight:700;color:#5b21b6;margin-bottom:4px">'
                f'<span style="background:#ede9fe;padding:2px 8px;border-radius:6px">{ca["area"]}</span></div>'
                f'<ul style="margin:0;padding-left:0;list-style:none">{items}</ul></div>'
            )
        enc_items = "".join(
            f'<li style="margin-bottom:4px;display:flex;align-items:flex-start;gap:6px">'
            f'<input type="checkbox" style="margin-top:2px;flex-shrink:0">'
            f'<span style="font-size:12px;color:#374151">{cr}</span></li>'
            for cr in c["criterios_encerramento"]
        )
        cards += f"""
        <details style="border:1px solid #e2e8f0;border-radius:10px;margin-bottom:8px;overflow:hidden">
          <summary style="display:flex;align-items:center;gap:12px;padding:12px 16px;background:#f8fafc;cursor:pointer;list-style:none">
            <div style="min-width:28px;height:28px;border-radius:50%;background:#6366f1;color:#fff;
              display:flex;align-items:center;justify-content:center;font-weight:700;font-size:12px">{c['passo']}</div>
            <span style="font-weight:700;font-size:13px;flex:1"><code style="background:#e0e7ff;color:#4338ca;padding:1px 8px;border-radius:4px">{c['modulo']}</code></span>
            <span style="font-size:11px;color:#94a3b8">{len(c['criterios_por_area'])} área(s)</span>
            <span style="font-size:16px;color:#94a3b8">▾</span>
          </summary>
          <div style="padding:14px 16px">
            {area_blocks}
            <div style="border-top:1px dashed #e2e8f0;padding-top:10px;margin-top:4px">
              <div style="font-size:11px;font-weight:700;color:#065f46;margin-bottom:4px">
                <span style="background:#d1fae5;padding:2px 8px;border-radius:6px">✅ Encerramento</span>
              </div>
              <ul style="margin:0;padding-left:0;list-style:none">{enc_items}</ul>
            </div>
          </div>
        </details>"""
    return f"""
  <div class="section" id="sec-criterios">
    <details open>
    <summary style="list-style:none;cursor:pointer;display:flex;align-items:center;justify-content:space-between;margin-bottom:16px">
      <h2 style="margin:0">&#9989; Crit&eacute;rios de Aceite por M&oacute;dulo</h2>
      <span style="font-size:16px;color:#94a3b8">&#9662;</span>
    </summary>
    <div style="background:#f0fdf4;border:1px solid #bbf7d0;border-radius:8px;padding:10px 14px;font-size:12px;color:#065f46;margin-bottom:14px">
      &#9989; Condi&ccedil;&otilde;es que devem ser verdadeiras para considerar o m&oacute;dulo migrado e pronto para go-live.
      Marque cada item ap&oacute;s valida&ccedil;&atilde;o. Os checkboxes s&atilde;o locais (n&atilde;o persistem).
    </div>
    {cards}
    </details>
  </div>"""


def _build_risk_score_html(risk_score: list) -> str:
    if not risk_score:
        return ""
    _H_COLOR = {
        "Cr\u00edtico": ("#fee2e2", "#991b1b", "#ef4444"),
        "Alto":    ("#ffedd5", "#c2410c", "#f97316"),
        "M\u00e9dio":   ("#fef3c7", "#92400e", "#f59e0b"),
        "Baixo":   ("#f0fdf4", "#065f46", "#22c55e"),
    }
    _H_ICON = {"Cr\u00edtico": "\U0001f534", "Alto": "\U0001f7e0", "M\u00e9dio": "\U0001f7e1", "Baixo": "\U0001f7e2"}
    max_score = max((h["score"] for h in risk_score), default=1) or 1
    rows = ""
    for h in risk_score:
        bg, fg, bar_c = _H_COLOR.get(h["nivel"], ("#f3f4f6", "#374151", "#6b7280"))
        icon  = _H_ICON.get(h["nivel"], "")
        bar_w = round(h["score"] / max_score * 100)
        fator_tags = " ".join(
            '<span style="background:#e0e7ff;color:#4338ca;padding:1px 6px;border-radius:4px;font-size:10px" '
            f'title="{f["detalhe"]}">{f["fator"]} +{f["pontos"]}</span>'
            for f in h["fatores"]
        ) or '<span style="color:#9ca3af">\u2014</span>'
        rows += f"""
        <tr>
          <td style="text-align:center;font-weight:700;color:#6366f1">{h['passo']}</td>
          <td><code style="background:#e0e7ff;color:#4338ca;padding:1px 6px;border-radius:4px">{h['modulo']}</code></td>
          <td><span style="background:{bg};color:{fg};padding:2px 10px;border-radius:9999px;font-size:11px;font-weight:700">{icon} {h['nivel']}</span></td>
          <td style="min-width:130px">
            <div style="display:flex;align-items:center;gap:6px">
              <div style="flex:1;background:#e2e8f0;border-radius:9999px;height:6px">
                <div style="width:{bar_w}%;background:{bar_c};border-radius:9999px;height:6px"></div>
              </div>
              <span style="font-weight:800;color:{fg};min-width:32px;font-size:12px">{h['score']}</span>
            </div>
          </td>
          <td style="line-height:2">{fator_tags}</td>
        </tr>"""
    criticos = sum(1 for h in risk_score if h["nivel"] == "Cr\u00edtico")
    altos    = sum(1 for h in risk_score if h["nivel"] == "Alto")
    alert = ""
    if criticos:
        alert = (f'<div style="background:#fee2e2;border:1px solid #fecaca;border-radius:8px;'
                 f'padding:10px 14px;font-size:12px;color:#991b1b;margin-bottom:14px">'
                 f'\U0001f6a8 <strong>{criticos} m\u00f3dulo(s) Cr\u00edtico</strong> e <strong>{altos} Alto</strong>. '
                 f'Priorize esses m\u00f3dulos com feature flags e testes de regress\u00e3o.</div>')
    return f"""
  <div class="section" id="sec-risk-score">
    <details open>
    <summary style="list-style:none;cursor:pointer;display:flex;align-items:center;justify-content:space-between;margin-bottom:16px">
      <h2 style="margin:0">&#127922; Risk Score por M&#243;dulo</h2>
      <span style="font-size:16px;color:#94a3b8">&#9662;</span>
    </summary>
    <div style="background:#eff6ff;border:1px solid #bfdbfe;border-radius:8px;padding:10px 14px;font-size:12px;color:#1e40af;margin-bottom:14px">
      &#8505;&#65039; Score composto 0&#8211;100: Impactos Alta (&times;3) + M&#233;dia (&times;1) + SPOF (+10) + Gargalo (+3&#8211;8) + Fluxo partido (+6/fluxo) + Dual (+4) + Depend&#234;ncias (+2). Normalizado sobre o m&#225;ximo do conjunto.
    </div>
    {alert}
    <div style="overflow-x:auto">
      <table class="imp-table">
        <thead><tr>
          <th style="text-align:center">Sprint</th>
          <th>M&#243;dulo</th>
          <th>N&#237;vel</th>
          <th>Score (0&#8211;100)</th>
          <th>Fatores</th>
        </tr></thead>
        <tbody>{rows}</tbody>
      </table>
    </div>
    </details>
  </div>"""


def _build_sugestoes_html(sugestoes: list) -> str:
    if not sugestoes:
        return ""
    _G_COLOR = {"Cr\u00edtico": ("#fee2e2","#991b1b"), "Alto": ("#ffedd5","#c2410c")}
    _G_ICON  = {"Cr\u00edtico": "\U0001f534", "Alto": "\U0001f7e0"}
    cards = ""
    for s in sugestoes:
        bg, fg = _G_COLOR.get(s["gravidade"], ("#fef3c7","#92400e"))
        icon   = _G_ICON.get(s["gravidade"], "\U0001f7e1")
        cards += f"""
        <div style="border:1px solid {fg}33;border-radius:10px;padding:14px 16px;margin-bottom:10px;background:{bg}22">
          <div style="display:flex;align-items:center;gap:10px;margin-bottom:8px;flex-wrap:wrap">
            <span style="background:{bg};color:{fg};padding:2px 10px;border-radius:9999px;font-size:11px;font-weight:700;border:1px solid {fg}44">{icon} {s['gravidade']}</span>
            <strong style="font-size:13px">{s['fluxo']}</strong>
            <span style="font-size:11px;color:#64748b;margin-left:auto">{s['impactos_alta_repo']} impactos Alta</span>
          </div>
          <div style="display:flex;align-items:center;gap:8px;margin-bottom:8px;flex-wrap:wrap">
            <code style="background:#e0e7ff;color:#4338ca;padding:2px 8px;border-radius:6px;font-size:12px">{s['repo']}</code>
            <span style="font-size:16px;color:#94a3b8">&#8594;</span>
            <span style="background:#e0e7ff;color:#4338ca;padding:2px 10px;border-radius:9999px;font-size:12px;font-weight:700">Trilha {s['para_trilha']}</span>
            <span style="font-size:11px;color:#64748b">(de Trilha {s['de_trilha']})</span>
          </div>
          <div style="font-size:12px;color:#374151;margin-bottom:6px">{s['justificativa']}</div>
          <div style="display:flex;gap:16px;font-size:11px;color:#64748b">
            <span>Carga Trilha {s['de_trilha']} ap&#243;s: <strong>{s['nova_carga_trilha_origem']}</strong></span>
            <span>Carga Trilha {s['para_trilha']} ap&#243;s: <strong>{s['nova_carga_trilha_destino']}</strong></span>
          </div>
        </div>"""
    return f"""
  <div class="section" id="sec-sugestoes">
    <details open>
    <summary style="list-style:none;cursor:pointer;display:flex;align-items:center;justify-content:space-between;margin-bottom:16px">
      <h2 style="margin:0">&#128260; Sugest&#245;es de Movimenta&#231;&#227;o entre Trilhas</h2>
      <span style="font-size:16px;color:#94a3b8">&#9662;</span>
    </summary>
    <div style="background:#eff6ff;border:1px solid #bfdbfe;border-radius:8px;padding:10px 14px;font-size:12px;color:#1e40af;margin-bottom:14px">
      &#8505;&#65039; Movimenta&#231;&#245;es sugeridas para consolidar fluxos partidos em uma &#250;nica trilha, reduzindo necessidade de sincroniza&#231;&#227;o entre equipes. Apenas fluxos Alto/Cr&#237;tico s&#227;o considerados.
    </div>
    {cards}
    </details>
  </div>"""


def _build_refatoracao_html(oportunidades: list) -> str:
    if not oportunidades:
        return ""
    _TIPO_COLOR = {
        "Utilit\u00e1rio compartilhado":       ("#ede9fe", "#5b21b6"),
        "God Object / Alta coes\u00e3o":       ("#fee2e2", "#991b1b"),
        "Extrair CnpjUtils":                ("#d1fae5", "#065f46"),
        "Componente de Input compartilhado":("#eff6ff", "#1e40af"),
    }
    cards = ""
    for o in oportunidades:
        bg, fg = _TIPO_COLOR.get(o["tipo"], ("#f3f4f6", "#374151"))
        repo_tags = " ".join(
            f'<code style="background:#e0e7ff;color:#4338ca;padding:1px 6px;border-radius:4px;font-size:11px">{r}</code>'
            for r in o["repositorios"]
        )
        cards += f"""
        <div style="border:1px solid {fg}33;border-radius:10px;padding:14px 16px;margin-bottom:10px">
          <div style="display:flex;align-items:center;gap:10px;margin-bottom:8px;flex-wrap:wrap">
            <span style="background:{bg};color:{fg};padding:2px 10px;border-radius:9999px;font-size:11px;font-weight:700">{o['tipo']}</span>
            {f'<span style="background:#e0e7ff;color:#4338ca;padding:1px 8px;border-radius:6px;font-size:11px">{o["regra"]}</span>' if o["regra"] != "\u2014" else ""}
            <span style="font-size:11px;color:#64748b;margin-left:auto">{o['n_repos']} repo(s)</span>
          </div>
          <div style="font-size:12px;color:#374151;margin-bottom:8px">{o['descricao']}</div>
          <div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:6px;padding:8px 12px;font-size:11px;color:#059669">
            &#9989; <strong>A&#231;&#227;o:</strong> {o['acao']}
          </div>
          <div style="margin-top:8px;display:flex;flex-wrap:wrap;gap:4px">{repo_tags}</div>
        </div>"""
    return f"""
  <div class="section" id="sec-refatoracao">
    <details open>
    <summary style="list-style:none;cursor:pointer;display:flex;align-items:center;justify-content:space-between;margin-bottom:16px">
      <h2 style="margin:0">&#9881;&#65039; Oportunidades de Refatora&#231;&#227;o</h2>
      <span style="font-size:16px;color:#94a3b8">&#9662;</span>
    </summary>
    <div style="background:#f0fdf4;border:1px solid #bbf7d0;border-radius:8px;padding:10px 14px;font-size:12px;color:#065f46;margin-bottom:14px">
      &#9989; Padr&#245;es recorrentes detectados que indicam oportunidades de centralizar a corre&#231;&#227;o e reduzir retrabalho entre reposit&#243;rios.
    </div>
    {cards}
    </details>
  </div>"""


def _build_progresso_html(progresso: dict, total: int) -> str:
    if not progresso or total == 0:
        return ""
    pendente     = progresso.get("pendente", 0)
    em_progresso = progresso.get("em_progresso", 0)
    resolvido    = progresso.get("resolvido", 0)
    falso_pos    = progresso.get("falso_positivo", 0)
    concluidos   = resolvido + falso_pos
    pct          = round(concluidos / total * 100)
    pct_res      = round(resolvido    / total * 100)
    pct_fp       = round(falso_pos    / total * 100)
    pct_prog     = round(em_progresso / total * 100)
    pct_pend     = 100 - pct_res - pct_fp - pct_prog
    pct_color    = '#10b981' if pct >= 80 else '#f59e0b' if pct >= 40 else '#ef4444'

    segments = [
        (pct_res,  '#10b981'),
        (pct_fp,   '#94a3b8'),
        (pct_prog, '#3b82f6'),
        (pct_pend, '#e2e8f0'),
    ]
    seg_html = "".join(
        f'<div class="prog-seg" style="width:0%;background:{c}" data-w="{w}"></div>'
        for w, c in segments
    )

    cards = (
        f'<div style="display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-top:4px">'
        f'<div style="background:#fef3c7;border-radius:10px;padding:14px 16px;border-left:4px solid #f59e0b">'
        f'<div style="font-size:24px;font-weight:800;color:#92400e">{pendente}</div>'
        f'<div style="font-size:11px;color:#78350f;margin-top:2px">⏳ Pendente <span style="color:#92400e;font-weight:700">{pct_pend}%</span></div></div>'
        f'<div style="background:#dbeafe;border-radius:10px;padding:14px 16px;border-left:4px solid #3b82f6">'
        f'<div style="font-size:24px;font-weight:800;color:#1e40af">{em_progresso}</div>'
        f'<div style="font-size:11px;color:#1e40af;margin-top:2px">🔄 Em progresso <span style="font-weight:700">{pct_prog}%</span></div></div>'
        f'<div style="background:#d1fae5;border-radius:10px;padding:14px 16px;border-left:4px solid #10b981">'
        f'<div style="font-size:24px;font-weight:800;color:#065f46">{resolvido}</div>'
        f'<div style="font-size:11px;color:#065f46;margin-top:2px">✅ Resolvido <span style="font-weight:700">{pct_res}%</span></div></div>'
        f'<div style="background:#f1f5f9;border-radius:10px;padding:14px 16px;border-left:4px solid #94a3b8">'
        f'<div style="font-size:24px;font-weight:800;color:#475569">{falso_pos}</div>'
        f'<div style="font-size:11px;color:#475569;margin-top:2px">🚫 Falso positivo <span style="font-weight:700">{pct_fp}%</span></div></div>'
        f'</div>'
    )
    return f"""
  <div class="section" id="sec-progresso">
    <details open>
    <summary style="list-style:none;cursor:pointer;display:flex;align-items:center;justify-content:space-between;margin-bottom:16px"><h2 style="margin:0">📈 Progresso da Migração</h2><span style="font-size:16px;color:#94a3b8">&#9662;</span></summary>
    <div style="display:flex;align-items:center;justify-content:space-between">
      <span style="font-size:13px;color:#475569">{concluidos} de {total} impactos endereçados</span>
      <span style="font-size:22px;font-weight:800;color:{pct_color}">{pct}%</span>
    </div>
    <div style="height:12px;border-radius:9999px;background:#e2e8f0;overflow:hidden;margin:12px 0;display:flex">
      {seg_html}
    </div>
    <div style="display:flex;gap:16px;font-size:11px;color:#64748b;margin-bottom:12px">
      <span><span style="display:inline-block;width:10px;height:10px;border-radius:2px;background:#10b981;margin-right:4px"></span>Resolvido</span>
      <span><span style="display:inline-block;width:10px;height:10px;border-radius:2px;background:#94a3b8;margin-right:4px"></span>Falso positivo</span>
      <span><span style="display:inline-block;width:10px;height:10px;border-radius:2px;background:#3b82f6;margin-right:4px"></span>Em progresso</span>
      <span><span style="display:inline-block;width:10px;height:10px;border-radius:2px;background:#e2e8f0;border:1px solid #cbd5e1;margin-right:4px"></span>Pendente</span>
    </div>
    {cards}
    </details>
  </div>
  <script>
  (function() {{
    const segs = document.querySelectorAll('.prog-seg');
    requestAnimationFrame(() => {{
      segs.forEach(s => {{
        s.style.transition = 'width 0.8s cubic-bezier(.4,0,.2,1)';
        s.style.width = s.dataset.w + '%';
      }});
    }});
  }})();
  </script>"""

def _build_parceiros_html(parceiros: list) -> str:
    if not parceiros:
        return ""
    rows = ""
    for p in parceiros:
        repos_tags = " ".join(
            f'<code style="background:#f1f5f9;color:#475569;padding:1px 6px;border-radius:4px;font-size:11px">{r}</code>'
            for r in p.get("repositorios", [])
        ) or '<span style="color:#9ca3af">—</span>'
        status = p.get("status_alinhamento", "pendente")
        rows += f"""
        <tr data-status="{status}">
          <td style="font-weight:700;font-size:12px">{p['parceiro'].upper()}</td>
          <td style="font-size:12px;color:#374151;max-width:320px">{p['descricao']}</td>
          <td style="line-height:2">{repos_tags}</td>
          <td>{_alinhamento_badge(status)}</td>
        </tr>"""
    pendentes = sum(1 for p in parceiros if p.get("status_alinhamento","pendente") == "pendente")
    alert = f'<div style="background:#fef3c7;border:1px solid #fcd34d;border-radius:8px;padding:10px 14px;font-size:12px;color:#78350f;margin-bottom:14px">'\
            f'⚠️ <strong>{pendentes} parceiro(s)</strong> ainda sem confirmação de suporte ao CNPJ alfanumérico. '\
            f'Cada um pode rejeitar silenciosamente payloads com letras no CNPJ.</div>' if pendentes else ""
    status_opts = "".join(
        f'<option value="{s}">{s}</option>'
        for s in sorted({p.get("status_alinhamento", "pendente") for p in parceiros})
    )
    return f"""
  <div class="section" id="sec-parceiros">
    <details open>
    <summary style="list-style:none;cursor:pointer;display:flex;align-items:center;justify-content:space-between;margin-bottom:16px"><h2 style="margin:0">🤝 Parceiros Externos — Alinhamento Necessário</h2><span style="font-size:16px;color:#94a3b8">&#9662;</span></summary>
    {alert}
    <div style="margin-bottom:10px;display:flex;gap:8px;align-items:center">
      <select id="parc-status" onchange="filterParceiros()"
        style="padding:5px 8px;border:1px solid #d1d5db;border-radius:6px;font-size:12px">
        <option value="">Todos os status</option>
        {status_opts}
      </select>
      <span id="parc-count" style="font-size:11px;color:#6366f1;font-weight:600"></span>
    </div>
    <div style="overflow-x:auto">
      <table class="imp-table" id="tbl-parceiros">
        <thead><tr><th>Parceiro</th><th>Risco</th><th>Repositórios afetados</th><th>Status alinhamento</th></tr></thead>
        <tbody>{rows}</tbody>
      </table>
    </div>
    </details>
  </div>
  <script>
  function filterParceiros() {{
    const sel  = document.getElementById('parc-status').value;
    const rows = document.querySelectorAll('#tbl-parceiros tbody tr');
    let vis = 0;
    rows.forEach(tr => {{
      const show = !sel || tr.dataset.status === sel;
      tr.style.display = show ? '' : 'none';
      if (show) vis++;
    }});
    const el = document.getElementById('parc-count');
    if (el) el.textContent = sel ? vis + ' de ' + rows.length + ' visíveis' : '';
  }}
  </script>"""

def _build_telas_qa_html(telas_qa: list) -> str:
    if not telas_qa:
        return ""
    rows = ""
    for t in telas_qa:
        repos_tags = " ".join(
            f'<code style="background:#f1f5f9;color:#475569;padding:1px 6px;border-radius:4px;font-size:11px">{r}</code>'
            for r in t["repositorios"]
        )
        areas_tags = " ".join(
            f'<span class="area-tag">{a}</span>' for a in t["areas_impactadas"]
        )
        testes = "<br>".join(
            f'<span style="font-size:11px;color:#374151">• {ts}</span>' for ts in t["testes_sugeridos"]
        )
        dual = '<span style="color:#3b82f6;font-weight:700">✔ Dual</span>' if t["requer_compatibilidade_dual"] else '<span style="color:#9ca3af">—</span>'
        rows += f"""
        <tr>
          <td style="text-align:center">{_prio_badge(t['prioridade'])}</td>
          <td style="font-weight:600;font-size:12px">{t['tela']}</td>
          <td style="line-height:2">{repos_tags}</td>
          <td style="line-height:2">{areas_tags}</td>
          <td style="text-align:center;font-weight:700;color:#6366f1">{t['total_impactos']}</td>
          <td>{testes}</td>
          <td style="text-align:center">{dual}</td>
        </tr>"""
    p1 = sum(1 for t in telas_qa if t["prioridade"] == "P1")
    p2 = sum(1 for t in telas_qa if t["prioridade"] == "P2")
    return f"""
  <div class="section" id="sec-telas-qa">
    <details open>
    <summary style="list-style:none;cursor:pointer;display:flex;align-items:center;justify-content:space-between;margin-bottom:16px"><h2 style="margin:0">\U0001f9ea Telas para QA</h2><span style="font-size:16px;color:#94a3b8">&#9662;</span></summary>
    <div style="background:#eff6ff;border:1px solid #bfdbfe;border-radius:8px;padding:10px 14px;font-size:12px;color:#1e40af;margin-bottom:14px">
      ℹ️ Telas e fluxos inferidos a partir dos impactos de código. Testar com CNPJ alfanumérico (ex: <code>12.ABC.345/01DE-35</code>)
      e verificar que o CNPJ numérico antigo continua funcionando.
      <strong>{p1} tela(s) P1</strong> e <strong>{p2} tela(s) P2</strong> identificadas.
    </div>
    <div style="overflow-x:auto">
      <table class="imp-table">
        <thead><tr>
          <th style="text-align:center">Prio</th>
          <th>Tela / Fluxo</th>
          <th>Repositórios</th>
          <th>Áreas</th>
          <th style="text-align:center">Impactos</th>
          <th>Testes Sugeridos</th>
          <th style="text-align:center">Dual</th>
        </tr></thead>
        <tbody>{rows}</tbody>
      </table>
    </div>
    </details>
  </div>"""


# ---------------------------------------------------------------------------
# Pessoa Juridica
# ---------------------------------------------------------------------------

def _build_pj_html(matriz: list) -> str:
    pj_items = [m for m in matriz if m["area"] == "Pessoa Jurídica/PJ"]
    total = len(pj_items)
    alta  = sum(1 for m in pj_items if m["complexidade"] == "Alta")
    media = sum(1 for m in pj_items if m["complexidade"] == "Média")
    baixa = sum(1 for m in pj_items if m["complexidade"] == "Baixa")
    dual  = sum(1 for m in pj_items if m.get("requer_compatibilidade_dual"))

    # resumo por repositório
    repo_map: dict[str, dict] = {}
    for m in pj_items:
        r = m["repositorio"]
        if r not in repo_map:
            repo_map[r] = {"total": 0, "Alta": 0, "Média": 0, "Baixa": 0}
        repo_map[r]["total"] += 1
        repo_map[r][m["complexidade"]] += 1

    resumo_rows = ""
    for repo, info in sorted(repo_map.items(), key=lambda x: x[1]["total"], reverse=True):
        alta_cell = f'<span style="background:#fef2f2;color:#ef4444;padding:1px 8px;border-radius:9999px;font-size:11px;font-weight:700;border:1px solid #fecaca">{info["Alta"]}</span>' if info["Alta"] else f'<span style="color:#9ca3af">0</span>'
        resumo_rows += f"""
        <tr onclick="selectRepo('{repo}')" style="cursor:pointer">
          <td style="font-weight:600;font-size:12px"><code style="background:#e0e7ff;color:#4338ca;padding:1px 6px;border-radius:4px">{repo}</code></td>
          <td style="text-align:center;font-weight:700;color:#6366f1">{info['total']}</td>
          <td style="text-align:center">{alta_cell}</td>
          <td style="text-align:center;color:#f59e0b;font-weight:600">{info['Média']}</td>
          <td style="text-align:center;color:#22c55e;font-weight:600">{info['Baixa']}</td>
        </tr>"""

    # tabela de impactos detalhados
    detail_rows = ""
    for m in pj_items:
        ev = m["evidencia"]
        detail_rows += f"""
        <tr data-repo="{m['repositorio']}" data-compl="{m['complexidade']}">
          <td style="color:#6b7280;font-size:11px">{m['id']}</td>
          <td>{_prio_badge(m.get('prioridade','P3'))}</td>
          <td>{_status_badge(m.get('status','pendente'))}</td>
          <td><code style="background:#e0e7ff;color:#4338ca;padding:1px 6px;border-radius:4px;font-size:11px">{m['repositorio']}</code></td>
          <td title="{m['componente']}" style="font-family:monospace;font-size:11px">{_short(m['componente'])}</td>
          <td>{_badge(m['complexidade'])}</td>
          <td style="font-size:11px;color:#374151">{m['descricao_impacto'][:80]}{'…' if len(m['descricao_impacto'])>80 else ''}</td>
          <td style="font-family:monospace;font-size:10px;color:#6b7280">{ev['arquivo'].split('/')[-1]}:{ev['linha']}</td>
        </tr>"""

    pills = ""
    if alta:  pills += f'<span style="background:#fef2f2;color:#ef4444;padding:2px 10px;border-radius:9999px;font-size:12px;font-weight:600;border:1px solid #fecaca">{alta} Alta</span>'
    if media: pills += f'<span style="background:#fffbeb;color:#f59e0b;padding:2px 10px;border-radius:9999px;font-size:12px;font-weight:600;border:1px solid #fde68a">{media} Média</span>'
    if baixa: pills += f'<span style="background:#f0fdf4;color:#22c55e;padding:2px 10px;border-radius:9999px;font-size:12px;font-weight:600;border:1px solid #bbf7d0">{baixa} Baixa</span>'
    if dual:  pills += f'<span style="background:#eff6ff;color:#3b82f6;padding:2px 10px;border-radius:9999px;font-size:12px;font-weight:600;border:1px solid #bfdbfe">{dual} Dual</span>'

    return f"""
  <div class="section" id="sec-pj">
    <details open>
    <summary style="list-style:none;cursor:pointer;display:flex;align-items:center;justify-content:space-between;margin-bottom:16px"><h2 style="margin:0">&#127962; Pessoa Jur&#237;dica / PJ &#8212; Impactos Detectados</h2><span style="font-size:16px;color:#94a3b8">&#9662;</span></summary>
    <div style="background:#eff6ff;border:1px solid #bfdbfe;border-radius:8px;padding:10px 14px;font-size:12px;color:#1e40af;margin-bottom:14px">
      &#8505;&#65039; Impactos reais detectados pelo scanner na &#225;rea <strong>Pessoa Jur&#237;dica/PJ</strong>.
      Todo c&#243;digo nesta &#225;rea referencia entidades PJ assumindo CNPJ exclusivamente num&#233;rico e pode quebrar com o formato alfanum&#233;rico.
    </div>
    <div style="display:flex;gap:10px;flex-wrap:wrap;align-items:center;margin-bottom:16px">
      <span style="font-size:22px;font-weight:800;color:#6366f1">{total}</span>
      <span style="font-size:12px;color:#64748b">impactos em {len(repo_map)} reposit&#243;rio(s)</span>
      <div style="display:flex;gap:6px;flex-wrap:wrap;margin-left:8px">{pills}</div>
    </div>

    <h3 style="font-size:13px;font-weight:600;margin:0 0 8px;color:#475569">Resumo por Reposit&#243;rio</h3>
    <div style="overflow-x:auto;margin-bottom:20px">
      <table class="imp-table">
        <thead><tr>
          <th>Reposit&#243;rio</th>
          <th style="text-align:center">Total</th>
          <th style="text-align:center">Alta</th>
          <th style="text-align:center">M&#233;dia</th>
          <th style="text-align:center">Baixa</th>
        </tr></thead>
        <tbody>{resumo_rows}</tbody>
      </table>
    </div>

    <h3 style="font-size:13px;font-weight:600;margin:0 0 8px;color:#475569">Todos os Impactos PJ</h3>
    <div style="margin-bottom:8px;display:flex;gap:6px;flex-wrap:wrap;align-items:center">
      <input type="text" id="pj-search" placeholder="&#128269; Buscar reposit&#243;rio, componente, evidência…" oninput="filterPJ()"
        style="padding:5px 10px;border:1px solid #d1d5db;border-radius:6px;font-size:12px;width:300px">
      <select id="pj-compl" onchange="filterPJ()" style="padding:5px 8px;border:1px solid #d1d5db;border-radius:6px;font-size:12px">
        <option value="">Todas complexidades</option>
        <option value="Alta">Alta</option>
        <option value="Média">Média</option>
        <option value="Baixa">Baixa</option>
      </select>
      <span id="pj-count" style="font-size:11px;color:#6366f1;font-weight:600"></span>
    </div>
    <div style="overflow-x:auto">
      <table class="imp-table" id="tbl-pj">
        <thead><tr>
          <th>ID</th><th>Prio</th><th>Status</th><th>Reposit&#243;rio</th>
          <th>Componente</th><th>Complexidade</th><th>Descri&#231;&#227;o</th><th>Evid&#234;ncia</th>
        </tr></thead>
        <tbody>{detail_rows}</tbody>
      </table>
    </div>
    </details>
  </div>
  <script>
  function filterPJ() {{
    const q     = document.getElementById('pj-search').value.toLowerCase();
    const compl = document.getElementById('pj-compl').value;
    const rows  = document.querySelectorAll('#tbl-pj tbody tr');
    let vis = 0;
    rows.forEach(tr => {{
      const okCompl = !compl || tr.dataset.compl === compl;
      const okText  = !q || tr.textContent.toLowerCase().includes(q);
      tr.style.display = okCompl && okText ? '' : 'none';
      if (okCompl && okText) vis++;
    }});
    const el = document.getElementById('pj-count');
    if (el) el.textContent = vis < rows.length ? vis + ' de ' + rows.length + ' vis&#237;veis' : '';
  }}
  </script>"""


def _build_heatmap_html(heatmap: list) -> str:
    if not heatmap:
        return ""
    _H_COLOR = {
        "Crítico": ("#fee2e2", "#991b1b", "#ef4444"),
        "Alto":    ("#ffedd5", "#c2410c", "#f97316"),
        "Médio":   ("#fef3c7", "#92400e", "#f59e0b"),
        "Baixo":   ("#f0fdf4", "#065f46", "#22c55e"),
    }
    _H_ICON = {"Crítico": "🔴", "Alto": "🟠", "Médio": "🟡", "Baixo": "🟢"}
    max_score = max((h["score_normalizado"] for h in heatmap), default=1) or 1
    rows = ""
    for h in heatmap:
        bg, fg, bar_c = _H_COLOR.get(h["nivel_risco"], ("#f3f4f6", "#374151", "#6b7280"))
        icon  = _H_ICON.get(h["nivel_risco"], "")
        bar_w = round(h["score_normalizado"] / max_score * 100)
        fatores_tags = " ".join(
            f'<span style="background:#e0e7ff;color:#4338ca;padding:1px 6px;border-radius:4px;font-size:10px">{f}</span>'
            for f in h["fatores"]
        ) or '<span style="color:#9ca3af">—</span>'
        rows += f"""
        <tr>
          <td style="text-align:center;font-weight:700;color:#6366f1">{h['passo']}</td>
          <td><code style="background:#e0e7ff;color:#4338ca;padding:1px 6px;border-radius:4px">{h['modulo']}</code></td>
          <td><span style="background:{bg};color:{fg};padding:2px 10px;border-radius:9999px;font-size:11px;font-weight:700">{icon} {h['nivel_risco']}</span></td>
          <td style="min-width:120px">
            <div style="display:flex;align-items:center;gap:6px">
              <div style="flex:1;background:#e2e8f0;border-radius:9999px;height:6px">
                <div style="width:{bar_w}%;background:{bar_c};border-radius:9999px;height:6px"></div>
              </div>
              <span style="font-weight:700;color:{fg};min-width:28px;font-size:11px">{h['score_normalizado']}</span>
            </div>
          </td>
          <td style="line-height:2">{fatores_tags}</td>
        </tr>"""
    criticos = sum(1 for h in heatmap if h["nivel_risco"] == "Crítico")
    altos    = sum(1 for h in heatmap if h["nivel_risco"] == "Alto")
    alert = ""
    if criticos:
        alert = (f'<div style="background:#fee2e2;border:1px solid #fecaca;border-radius:8px;'
                 f'padding:10px 14px;font-size:12px;color:#991b1b;margin-bottom:14px">'
                 f'🌡️ <strong>{criticos} sprint(s) Crítico</strong> e <strong>{altos} Alto</strong> '
                 f'detectados. Priorize esses módulos com feature flags e testes de regressão.</div>')
    return f"""
  <div class="section" id="sec-heatmap">
    <details open>
    <summary style="list-style:none;cursor:pointer;display:flex;align-items:center;justify-content:space-between;margin-bottom:16px">
      <h2 style="margin:0">&#127777;&#65039; Mapa de Calor de Risco por Sprint</h2>
      <span style="font-size:16px;color:#94a3b8">&#9662;</span>
    </summary>
    <div style="background:#eff6ff;border:1px solid #bfdbfe;border-radius:8px;padding:10px 14px;font-size:12px;color:#1e40af;margin-bottom:14px">
      &#8505;&#65039; Score composto por sprint: impactos Alta (&times;2) + SPOF (+5) + Gargalo (+3&times;n&iacute;vel) + Fluxo partido (+4). Normalizado 0&ndash;100.
    </div>
    {alert}
    <div style="overflow-x:auto">
      <table class="imp-table">
        <thead><tr>
          <th style="text-align:center">Sprint</th>
          <th>M&oacute;dulo</th>
          <th>N&iacute;vel de Risco</th>
          <th>Score (0&ndash;100)</th>
          <th>Fatores</th>
        </tr></thead>
        <tbody>{rows}</tbody>
      </table>
    </div>
    </details>
  </div>"""


def _build_spof_html(spof: list) -> str:
    if not spof:
        return ""
    rows = ""
    for s in spof:
        rows += f"""
        <tr>
          <td style="font-weight:700;font-size:12px;color:#7c3aed">{s['dominio']}</td>
          <td><code style="background:#e0e7ff;color:#4338ca;padding:1px 6px;border-radius:4px">{s['repositorio']}</code></td>
          <td style="text-align:center;color:#6b7280">{s.get('passo_migracao', '—')}</td>
          <td style="text-align:center;font-weight:700;color:#ef4444">{s['impactos_alta']}</td>
          <td style="font-size:11px;color:#374151">{s['motivo']}</td>
        </tr>"""
    return f"""
  <div class="section" id="sec-spof">
    <details open>
    <summary style="list-style:none;cursor:pointer;display:flex;align-items:center;justify-content:space-between;margin-bottom:16px">
      <h2 style="margin:0">&#9889; SPOFs &mdash; Pontos &Uacute;nicos de Falha</h2>
      <span style="font-size:16px;color:#94a3b8">&#9662;</span>
    </summary>
    <div style="background:#faf5ff;border:1px solid #e9d5ff;border-radius:8px;padding:10px 14px;font-size:12px;color:#6b21a8;margin-bottom:14px">
      &#9889; Repos que s&atilde;o o <strong>&uacute;nico</strong> representante de um dom&iacute;nio cr&iacute;tico.
      Se atrasarem, <strong>nenhum outro repo pode cobrir o dom&iacute;nio</strong>. Priorize feature flags e testes de regress&atilde;o antes dos demais.
    </div>
    <div style="overflow-x:auto">
      <table class="imp-table">
        <thead><tr>
          <th>Dom&iacute;nio</th><th>Reposit&oacute;rio</th>
          <th style="text-align:center">Sprint</th>
          <th style="text-align:center">Alta</th>
          <th>Motivo</th>
        </tr></thead>
        <tbody>{rows}</tbody>
      </table>
    </div>
    </details>
  </div>"""


def _build_gargalos_html(gargalos: list) -> str:
    if not gargalos:
        return ""
    _G_COLOR = {"Crítico": ("#fee2e2","#991b1b"), "Alto": ("#ffedd5","#c2410c"), "Médio": ("#fef3c7","#92400e")}
    _G_ICON  = {"Crítico": "🔴", "Alto": "🟠", "Médio": "🟡"}
    rows = ""
    for g in gargalos:
        bg, fg = _G_COLOR.get(g["nivel"], ("#f3f4f6","#374151"))
        icon   = _G_ICON.get(g["nivel"], "")
        fluxos_tags = " ".join(
            f'<span style="background:#e0e7ff;color:#4338ca;padding:1px 6px;border-radius:4px;font-size:10px">{f}</span>'
            for f in g["fluxos"]
        )
        rows += f"""
        <tr>
          <td><span style="background:{bg};color:{fg};padding:2px 10px;border-radius:9999px;font-size:11px;font-weight:700">{icon} {g['nivel']}</span></td>
          <td style="font-weight:700;font-size:12px"><code style="background:#e0e7ff;color:#4338ca;padding:1px 6px;border-radius:4px">{g['repositorio']}</code></td>
          <td style="text-align:center;font-weight:700;color:#6366f1">{g['n_fluxos']}</td>
          <td style="text-align:center;color:#64748b">{g['pct_fluxos']}%</td>
          <td style="text-align:center;color:#6b7280">{g.get('passo_migracao', '—')}</td>
          <td style="line-height:2">{fluxos_tags}</td>
        </tr>"""
    criticos = sum(1 for g in gargalos if g["nivel"] == "Crítico")
    alert = f'<div style="background:#fee2e2;border:1px solid #fecaca;border-radius:8px;padding:10px 14px;font-size:12px;color:#991b1b;margin-bottom:14px">' \
            f'🔥 <strong>{criticos} gargalo(s) crítico(s)</strong> detectado(s). ' \
            f'Qualquer atraso nesses repos impacta múltiplos fluxos simultaneamente.</div>' if criticos else ""
    return f"""
  <div class="section" id="sec-gargalos">
    <details open>
    <summary style="list-style:none;cursor:pointer;display:flex;align-items:center;justify-content:space-between;margin-bottom:16px">
      <h2 style="margin:0">🔥 Gargalos Arquiteturais</h2>
      <span style="font-size:16px;color:#94a3b8">&#9662;</span>
    </summary>
    <div style="background:#eff6ff;border:1px solid #bfdbfe;border-radius:8px;padding:10px 14px;font-size:12px;color:#1e40af;margin-bottom:14px">
      ℹ️ Repos que participam de muitos fluxos distintos. Qualquer atraso neles atrasa a migração inteira.
      Priorize a migração desses repos e garanta que tenham feature flags e testes de regressão antes dos demais.
    </div>
    {alert}
    <div style="overflow-x:auto">
      <table class="imp-table">
        <thead><tr>
          <th>Nível</th><th>Repositório</th>
          <th style="text-align:center">Fluxos</th>
          <th style="text-align:center">% Total</th>
          <th style="text-align:center">Sprint</th>
          <th>Fluxos Afetados</th>
        </tr></thead>
        <tbody>{rows}</tbody>
      </table>
    </div>
    </details>
  </div>"""


# ---------------------------------------------------------------------------
# Build HTML
# ---------------------------------------------------------------------------

def build_dashboard(data: dict) -> str:
    stats     = data["estatisticas"]
    matriz    = data["matriz_impacto"]
    criticos  = data.get("arquivos_criticos", [])
    ordem     = data.get("ordem_migracao", [])
    repos     = data["repositorios_analisados"]
    cobertura = data.get("cobertura", {})
    pontos_cegos      = cobertura.get("pontos_cegos", [])
    repos_sem_impacto = cobertura.get("repositorios_sem_impacto", [])
    aliases_suspeitos = cobertura.get("repos_sem_impacto_com_aliases", {})
    parceiros         = data.get("parceiros_externos", [])
    telas_qa          = data.get("telas_qa", [])
    progresso         = stats.get("progresso", {})
    candidatos        = stats.get("candidatos_por_repositorio", {})
    trilhas_data      = data.get("trilhas")
    heatmap          = data.get("heatmap_risco", [])
    spof             = data.get("spof", [])
    gargalos          = data.get("gargalos", [])
    criterios         = data.get("criterios_aceite", [])
    esforco           = data.get("esforco", [])
    diff              = data.get("diff")
    risk_score        = data.get("risk_score", [])
    sugestoes         = data.get("sugestoes_movimentacao", [])
    oportunidades     = data.get("oportunidades_refatoracao", [])
    pj_html           = _build_pj_html(matriz)

    # ---- dados para gráficos ----
    areas     = stats["impactos_por_area"]
    complexid = stats["impactos_por_complexidade"]
    area_labels  = list(areas.keys())
    area_values  = list(areas.values())
    compl_labels = list(complexid.keys())
    compl_values = list(complexid.values())

    AREA_COLORS  = ["#6366f1","#f59e0b","#10b981","#ef4444","#3b82f6","#8b5cf6","#ec4899","#14b8a6"]
    COMPL_COLORS = {"Alta":"#ef4444","Média":"#f59e0b","Baixa":"#22c55e"}
    compl_bg = [COMPL_COLORS.get(l,"#6b7280") for l in compl_labels]

    # ---- impactos por repositório ----
    repo_counts: dict[str, int] = {}
    for m in matriz:
        repo_counts[m["repositorio"]] = repo_counts.get(m["repositorio"], 0) + 1

    # ---- sprint por módulo (ordem_migracao) ----
    repo_sprint = {s["modulo"]: s["passo"] for s in ordem}

    # ---- tabela resumo repos ----
    resumo_rows = ""
    max_cnt = max(repo_counts.values()) if repo_counts else 1
    for repo in sorted(repos, key=lambda r: repo_counts.get(r, 0), reverse=True):
        cnt  = repo_counts.get(repo, 0)
        if cnt == 0:
            continue
        info = candidatos.get(repo, {})
        cand = info.get("candidatos", "—") if isinstance(info, dict) else "—"
        taxa = f"{info.get('taxa_conversao', 0):.0%}" if isinstance(info, dict) and info.get("taxa_conversao") is not None else "—"
        alta = sum(1 for m in matriz if m["repositorio"] == repo and m["complexidade"] == "Alta")
        dual = sum(1 for m in matriz if m["repositorio"] == repo and m.get("requer_compatibilidade_dual"))
        sprint = repo_sprint.get(repo, "—")
        bar_w = round(cnt / max_cnt * 100)
        alta_pct = round(alta / cnt * 100) if cnt else 0
        row_cls = "row-p1" if alta_pct >= 70 else ("row-p2" if alta_pct >= 40 else "")
        alta_cell = f'<span style="background:#fef2f2;color:#ef4444;padding:1px 8px;border-radius:9999px;font-size:11px;font-weight:700;border:1px solid #fecaca">{alta}</span>' if alta else f'<span style="color:#9ca3af">{alta}</span>'
        sprint_cell = f'<span style="background:#e0e7ff;color:#4338ca;padding:1px 8px;border-radius:9999px;font-size:11px;font-weight:700">{sprint}</span>' if sprint != "—" else '<span style="color:#9ca3af">—</span>'
        resumo_rows += f"""
        <tr class="{row_cls}" onclick="selectRepo('{repo}')" style="cursor:pointer"
            data-repo="{repo}" data-cnt="{cnt}" data-alta="{alta}" data-dual="{dual}" data-sprint="{sprint if sprint != '—' else 9999}">
          <td style="font-weight:600;font-size:12px">{repo}</td>
          <td style="text-align:center">{sprint_cell}</td>
          <td style="text-align:center;color:#6b7280">{cand}</td>
          <td>
            <div style="display:flex;align-items:center;gap:8px">
              <div style="flex:1;background:#e2e8f0;border-radius:9999px;height:6px">
                <div style="width:{bar_w}%;background:#6366f1;border-radius:9999px;height:6px"></div>
              </div>
              <span style="font-weight:700;color:#6366f1;min-width:24px">{cnt}</span>
            </div>
          </td>
          <td style="text-align:center">{alta_cell}</td>
          <td style="text-align:center;color:#3b82f6">{dual}</td>
          <td style="text-align:center;color:#64748b">{taxa}</td>
        </tr>"""

    # ---- visão macro por fluxo ----
    fluxos: dict[str, dict] = {}
    for m in matriz:
        f = m.get("fluxo") or "Sem fluxo mapeado"
        if f not in fluxos:
            fluxos[f] = {"total": 0, "alta": 0, "repos": set(), "areas": set()}
        fluxos[f]["total"] += 1
        if m["complexidade"] == "Alta":
            fluxos[f]["alta"] += 1
        fluxos[f]["repos"].add(m["repositorio"])
        fluxos[f]["areas"].add(m["area"])

    fluxo_cards = ""
    for nome, info in sorted(fluxos.items(), key=lambda x: (-x[1]["alta"], -x[1]["total"])):
        repos_tags = " ".join(
            f'<code style="background:#e0e7ff;color:#4338ca;padding:1px 6px;border-radius:4px;font-size:11px">{r}</code>'
            for r in sorted(info["repos"])
        )
        area_tags = " ".join(
            f'<span class="area-tag">{a}</span>' for a in sorted(info["areas"])
        )
        alta_badge = f'<span style="background:#fef2f2;color:#ef4444;padding:1px 8px;border-radius:9999px;font-size:11px;font-weight:700;border:1px solid #fecaca">{info["alta"]} Alta</span>' if info["alta"] else ""
        fluxo_cards += f"""
        <details style="border:1px solid #e2e8f0;border-radius:10px;margin-bottom:8px;overflow:hidden">
          <summary style="display:flex;align-items:center;gap:12px;padding:12px 16px;background:#f8fafc;cursor:pointer;list-style:none;user-select:none">
            <span style="font-weight:700;font-size:13px;flex:1">{nome}</span>
            <span style="background:#e0e7ff;color:#4338ca;padding:1px 10px;border-radius:9999px;font-size:12px;font-weight:700">{info['total']}</span>
            {alta_badge}
            <span style="font-size:11px;color:#94a3b8">{len(info['repos'])} repo(s)</span>
            <span style="font-size:16px;color:#94a3b8">&#9662;</span>
          </summary>
          <div style="padding:10px 16px 14px;display:flex;flex-direction:column;gap:8px">
            <div style="display:flex;flex-wrap:wrap;gap:4px;align-items:center">
              <span style="font-size:11px;color:#64748b;font-weight:600;margin-right:4px">Repos:</span>{repos_tags}
            </div>
            <div style="display:flex;flex-wrap:wrap;gap:4px;align-items:center">
              <span style="font-size:11px;color:#64748b;font-weight:600;margin-right:4px">Áreas:</span>{area_tags}
            </div>
          </div>
        </details>"""

    todas_areas  = sorted({m["area"] for m in matriz})
    todas_compl  = ["Alta", "Média", "Baixa"]
    area_chips   = "".join(f'<button class="chip" data-filter="area" data-val="{a}" onclick="toggleChip(this)">{a}</button>' for a in todas_areas)
    compl_chips  = "".join(f'<button class="chip" data-filter="compl" data-val="{c}" onclick="toggleChip(this)">{c}</button>' for c in todas_compl)

    # ---- tabelas por repositório ----
    repo_tables = ""
    for repo in repos:
        items = [m for m in matriz if m["repositorio"] == repo]
        rows = ""
        for m in items:
            ev     = m["evidencia"]
            motivo = m.get("motivo_compatibilidade_dual") or ""
            dual_cell = f'<span title="{motivo}" style="color:#3b82f6;font-weight:700;cursor:help">✔ Dual</span>' if m.get("requer_compatibilidade_dual") else '<span style="color:#9ca3af">—</span>'
            prio   = m.get('prioridade', 'P3')
            critico = m.get('arquivo_critico', False)
            row_cls = f"row-p1{' row-critico' if critico else ''}" if prio == 'P1' else ("row-p2" if prio == 'P2' else "")
            rows += f"""
            <tr class="{row_cls}" data-area="{m['area']}" data-compl="{m['complexidade']}" data-status="{m.get('status','pendente')}">
              <td style="color:#6b7280;font-size:11px">{m['id']}</td>
              <td>{_prio_badge(m.get('prioridade','P3'))}</td>
              <td>{_status_badge(m.get('status','pendente'))}</td>
              <td><span class="area-tag">{m['area']}</span></td>
              <td title="{m['componente']}" style="font-family:monospace;font-size:11px">{_short(m['componente'])}</td>
              <td>{_badge(m['complexidade'])}</td>
              <td style="text-align:center">{m.get('chamadores_estimados',0)}</td>
              <td style="text-align:center">{dual_cell}</td>
              <td style="font-size:11px;color:#374151">{m['descricao_impacto'][:80]}{'…' if len(m['descricao_impacto'])>80 else ''}</td>
              <td style="font-family:monospace;font-size:10px;color:#6b7280">{ev['arquivo'].split('/')[-1]}:{ev['linha']}</td>
            </tr>"""
        # mini-resumo de complexidade para o cabeçalho do painel
        alta_r  = sum(1 for m in items if m['complexidade'] == 'Alta')
        media_r = sum(1 for m in items if m['complexidade'] == 'Média')
        baixa_r = sum(1 for m in items if m['complexidade'] == 'Baixa')
        compl_pills = ""
        if alta_r:  compl_pills += f'<span style="background:#fef2f2;color:#ef4444;padding:1px 8px;border-radius:9999px;font-size:11px;font-weight:600;border:1px solid #fecaca">{alta_r} Alta</span>'
        if media_r: compl_pills += f'<span style="background:#fffbeb;color:#f59e0b;padding:1px 8px;border-radius:9999px;font-size:11px;font-weight:600;border:1px solid #fde68a">{media_r} Média</span>'
        if baixa_r: compl_pills += f'<span style="background:#f0fdf4;color:#22c55e;padding:1px 8px;border-radius:9999px;font-size:11px;font-weight:600;border:1px solid #bbf7d0">{baixa_r} Baixa</span>'
        repo_tables += f"""
        <div class="repo-panel" id="repo-{repo}" style="display:none">
          <div style="display:flex;align-items:center;gap:10px;margin-bottom:12px;flex-wrap:wrap;padding:12px 16px;background:#f8fafc;border-radius:10px;border:1px solid #e2e8f0">
            <h3 style="margin:0;font-size:15px">📦 {repo}</h3>
            <span style="background:#e0e7ff;color:#4338ca;padding:2px 10px;border-radius:9999px;font-size:12px;font-weight:600">{len(items)} impactos</span>
            {compl_pills}
            <span id="cnt-{repo}" style="font-size:11px;color:#64748b"></span>
            <input type="text" id="search-{repo}" placeholder="🔍 Buscar…" oninput="applyFilters('{repo}')"
              style="margin-left:auto;padding:5px 10px;border:1px solid #d1d5db;border-radius:6px;font-size:12px;width:200px">
          </div>
          <div style="overflow-x:auto">
            <table id="tbl-{repo}" class="imp-table">
              <thead><tr>
                <th>ID</th><th>Prio</th><th>Status</th><th>Área</th><th>Componente</th>
                <th>Complexidade</th><th>Chamadores</th><th>Dual</th><th>Descrição</th><th>Evidência</th>
              </tr></thead>
              <tbody>{rows if rows else '<tr><td colspan="10" style="text-align:center;color:#9ca3af;padding:24px">Nenhum impacto detectado</td></tr>'}</tbody>
            </table>
          </div>
        </div>"""

    # ---- arquivos críticos ----
    crit_rows = ""
    for i, arq in enumerate(criticos[:15], 1):
        dual = _dual_badge(arq.get("requer_compatibilidade_dual", False))
        linhas = ", ".join(str(l) for l in sorted(set(arq["linhas_afetadas"]))[:6])
        if len(arq["linhas_afetadas"]) > 6:
            linhas += f" +{len(arq['linhas_afetadas'])-6}"
        nome = arq["arquivo"].split("/")[-1]
        crit_rows += f"""
        <tr>
          <td style="color:#6b7280;font-size:12px">{i}</td>
          <td><code style="font-size:11px">{arq['repositorio']}</code></td>
          <td title="{arq['arquivo']}"><code style="font-size:11px">{nome}</code></td>
          <td><span class="area-tag">{arq['area']}</span></td>
          <td style="text-align:center;font-weight:700;color:#ef4444">{arq['chamadores_estimados']}</td>
          <td style="text-align:center">{arq['impactos_no_arquivo']}</td>
          <td style="text-align:center">{dual}</td>
          <td style="font-size:11px;color:#6b7280">{linhas}</td>
        </tr>"""

    # ---- ordem de migração por módulo ----
    step_colors = ["#ef4444","#f59e0b","#3b82f6","#8b5cf6","#10b981"]
    ordem_cards = ""
    for s in ordem:
        c = step_colors[(s["passo"]-1) % len(step_colors)]
        areas_html = ""
        for i, a in enumerate(s.get("areas", []), start=1):
            areas_html += (
                f'<div style="display:flex;align-items:center;gap:10px;padding:6px 0;'
                f'border-bottom:1px dashed #f3f4f6">'
                f'<span style="min-width:20px;height:20px;border-radius:50%;background:{c}22;'
                f'color:{c};display:flex;align-items:center;justify-content:center;'
                f'font-weight:700;font-size:11px">{i}</span>'
                f'<span class="area-tag">{a["area"]}</span>'
                f'<span style="font-size:11px;color:#6b7280;flex:1">{a["rationale"]}</span>'
                f'<span style="font-size:11px;color:#374151;white-space:nowrap">'
                f'{a["total_impactos"]} imp · {a["impactos_alta_complexidade"]} alta</span>'
                f'</div>'
            )
        is_first = s["passo"] == 1
        deps_badges = ""
        for d in s.get("depende_de", []):
            deps_badges += f'<code style="background:#fef3c7;color:#92400e;padding:1px 6px;border-radius:4px;font-size:10px;margin-right:3px">{d}</code>'
        deps_html_str = f'<div style="font-size:11px;color:#92400e;margin-top:4px">&#128279; Depende de: {deps_badges}</div>' if deps_badges else ""
        ordem_cards += f"""
        <details {'open ' if is_first else ''}style="border:1px solid #e2e8f0;border-radius:10px;margin-bottom:12px;overflow:hidden">
          <summary style="display:flex;gap:16px;align-items:center;padding:14px 16px;background:#f8fafc;cursor:pointer;list-style:none">
            <div style="min-width:36px;height:36px;border-radius:50%;background:{c};color:#fff;
              display:flex;align-items:center;justify-content:center;font-weight:700;font-size:15px">{s['passo']}</div>
            <div style="flex:1">
              <div style="font-weight:700;font-size:14px">Módulo: <code style="background:#e0e7ff;color:#4338ca;padding:1px 8px;border-radius:4px">{s['modulo']}</code></div>
              <div style="font-size:11px;color:#6b7280;margin-top:2px">{len(s.get('areas',[]))} área(s) a migrar</div>
              {deps_html_str}
            </div>
            <div style="text-align:right">
              <div style="font-size:18px;font-weight:700;color:{c}">{s['total_impactos']}</div>
              <div style="font-size:10px;color:#9ca3af">impactos</div>
              <div style="font-size:10px;color:#9ca3af">{s['impactos_alta_complexidade']} alta · {s['requerem_compatibilidade_dual']} dual</div>
            </div>
            <span style="font-size:16px;color:#94a3b8;margin-left:8px">▾</span>
          </summary>
          <div style="padding:8px 16px 12px">{areas_html}</div>
        </details>"""

    # ---- tab buttons ----
    tab_buttons_com = ""
    tab_buttons_sem = ""
    for repo in repos:
        cnt  = repo_counts.get(repo, 0)
        cand = candidatos.get(repo, {}).get("candidatos", 0) if isinstance(candidatos.get(repo), dict) else candidatos.get(repo, 0)
        if repo in aliases_suspeitos:
            extra  = ' style="border-color:#f59e0b;color:#92400e"'
            suffix = ' <span title="Aliases suspeitos" style="color:#f59e0b">⚠️</span>'
        else:
            extra  = ""
            suffix = ""
        cand_tip = f' title="{cand} candidatos analisados"' if cand else ""
        btn = f'<button class="tab-btn"{extra}{cand_tip} onclick="showRepo(\'{repo}\')">{repo}{suffix} <span class="tab-count">{cnt}</span></button>'
        if cnt > 0 or repo in aliases_suspeitos:
            tab_buttons_com += btn
        else:
            tab_buttons_sem += btn
    tab_buttons = tab_buttons_com
    if tab_buttons_sem:
        tab_buttons += f'<button onclick="toggleSemImpacto(this)" style="padding:7px 12px;border:1px dashed #cbd5e1;border-radius:8px;background:#f8fafc;cursor:pointer;font-size:11px;color:#94a3b8;margin-top:4px" id="btn-sem-impacto">+ {len([r for r in repos if repo_counts.get(r,0)==0 and r not in aliases_suspeitos])} sem impacto</button>'
        tab_buttons += f'<span id="tabs-sem-impacto" style="display:none">{tab_buttons_sem}</span>'

    # ---- seção de cobertura / pontos cegos ----
    pc_rows = ""
    for pc in pontos_cegos:
        pc_rows += f"""
        <tr>
          <td style="font-weight:700;color:#6366f1;white-space:nowrap">{pc['id']}</td>
          <td style="font-size:12px;color:#374151">{pc['descricao']}</td>
          <td style="font-size:12px;color:#059669">{pc['recomendacao']}</td>
        </tr>"""

    alias_rows = ""
    for repo, als in aliases_suspeitos.items():
        tags = " ".join(f'<code style="background:#fef3c7;color:#92400e;padding:1px 6px;border-radius:4px;font-size:11px">{a}</code>' for a in als)
        alias_rows += f"""
        <tr>
          <td><code style="font-size:12px">{repo}</code></td>
          <td>{tags}</td>
          <td style="font-size:11px;color:#6b7280">Revisar manualmente — pode processar CNPJ via alias</td>
        </tr>"""

    sem_impacto_tags = " ".join(
        f'<code style="background:#f1f5f9;color:#475569;padding:2px 8px;border-radius:6px;font-size:11px;margin:2px;display:inline-block">{r}</code>'
        for r in repos_sem_impacto
    )

    cobertura_card_val = f"{len(repos) - len(repos_sem_impacto)}/{len(repos)}"

    # ---- JSON para gráficos ----
    area_labels_js  = json.dumps(area_labels)
    area_values_js  = json.dumps(area_values)
    area_colors_js  = json.dumps(AREA_COLORS[:len(area_labels)])
    compl_labels_js = json.dumps(compl_labels)
    compl_values_js = json.dumps(compl_values)
    compl_bg_js     = json.dumps(compl_bg)
    repo_labels_js  = json.dumps(list(repo_counts.keys()))
    repo_values_js  = json.dumps(list(repo_counts.values()))

    data_exec = data.get("data_execucao","")[:19].replace("T"," ")
    scan_id       = data.get("scan_id", "")
    versao_regras = data.get("versao_regras", "—")
    data_limite   = data.get("data_limite_migracao") or "A definir"

    return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Dashboard – Impacto CNPJ | {data['sistema_escopo']}</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
  *{{box-sizing:border-box;margin:0;padding:0}}
  body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#f8fafc;color:#1e293b;font-size:13px}}
  .topbar{{background:linear-gradient(135deg,#1e293b 0%,#334155 100%);color:#fff;padding:18px 32px;display:flex;align-items:center;justify-content:space-between}}
  .topbar h1{{font-size:20px;font-weight:700;letter-spacing:-.3px}}
  .topbar .meta{{font-size:11px;color:#94a3b8;margin-top:2px}}
  .layout{{display:flex;align-items:flex-start}}
  .sidenav{{position:sticky;top:16px;width:200px;min-width:200px;background:#fff;border-radius:12px;box-shadow:0 1px 3px rgba(0,0,0,.07);padding:12px 0;margin:24px 0 24px 24px;align-self:flex-start}}
  .sidenav a{{display:flex;align-items:center;gap:8px;padding:8px 16px;font-size:12px;color:#475569;text-decoration:none;border-left:3px solid transparent;transition:all .15s;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
  .sidenav a:hover{{background:#f8fafc;color:#1e293b;border-left-color:#6366f1}}
  .sidenav a.active{{background:#f0f4ff;color:#4338ca;border-left-color:#6366f1;font-weight:600}}
  .sidenav .nav-sep{{height:1px;background:#f1f5f9;margin:6px 12px}}
  .nav-cnt{{margin-left:auto;background:#e0e7ff;color:#4338ca;border-radius:9999px;padding:1px 7px;font-size:10px;font-weight:700;flex-shrink:0}}
  .container{{flex:1;min-width:0;padding:24px 24px 24px 16px}}
  .cards{{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:14px;margin-bottom:24px}}
  .card{{background:#fff;border-radius:12px;padding:18px 20px;box-shadow:0 1px 3px rgba(0,0,0,.07);border-top:3px solid var(--accent)}}
  .card .val{{font-size:28px;font-weight:800;color:var(--accent)}}
  .card .lbl{{font-size:11px;color:#64748b;margin-top:2px;font-weight:500}}
  .section{{background:#fff;border-radius:12px;padding:20px 24px;box-shadow:0 1px 3px rgba(0,0,0,.07);margin-bottom:20px}}
  .section h2{{font-size:15px;font-weight:700;margin-bottom:16px;display:flex;align-items:center;gap:8px}}
  .charts-row{{display:grid;grid-template-columns:1fr 1fr 1fr;gap:20px;margin-bottom:20px}}
  .chart-box{{background:#fff;border-radius:12px;padding:20px;box-shadow:0 1px 3px rgba(0,0,0,.07)}}
  .chart-box h3{{font-size:13px;font-weight:600;color:#475569;margin-bottom:14px}}
  .tab-bar{{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:16px;max-height:180px;overflow-y:auto;padding:4px 2px}}
  .tab-btn{{padding:7px 16px;border:1px solid #e2e8f0;border-radius:8px;background:#fff;cursor:pointer;font-size:12px;font-weight:500;color:#475569;transition:all .15s}}
  .tab-btn:hover{{background:#f1f5f9}}
  .tab-btn.active{{background:#1e293b;color:#fff;border-color:#1e293b}}
  .tab-count{{background:#e0e7ff;color:#4338ca;border-radius:9999px;padding:1px 7px;font-size:10px;font-weight:700;margin-left:4px}}
  .tab-btn.active .tab-count{{background:#334155;color:#c7d2fe}}
  .imp-table{{width:100%;border-collapse:collapse;font-size:12px}}
  .imp-table th{{background:#f8fafc;padding:8px 10px;text-align:left;font-weight:600;color:#475569;border-bottom:2px solid #e2e8f0;white-space:nowrap}}
  .imp-table td{{padding:7px 10px;border-bottom:1px solid #f1f5f9;vertical-align:top}}
  .imp-table tbody tr:nth-child(even) td{{background:#fafcff}}
  .imp-table tbody tr:hover td{{background:#f0f4ff!important}}
  .imp-table tbody tr.row-p1 td:first-child{{border-left:3px solid #ef4444}}
  .imp-table tbody tr.row-p1:nth-child(even) td{{background:#fff8f8}}
  .imp-table tbody tr.row-p1:hover td{{background:#fee2e2!important}}
  .imp-table tbody tr.row-p2 td:first-child{{border-left:3px solid #f59e0b}}
  .imp-table tbody tr.row-p2:nth-child(even) td{{background:#fffdf5}}
  .imp-table tbody tr.row-p2:hover td{{background:#fef3c7!important}}
  .imp-table tbody tr.row-critico td:first-child::after{{content:' 🔥';font-size:10px}}
  .area-tag{{background:#ede9fe;color:#5b21b6;padding:2px 8px;border-radius:6px;font-size:10px;font-weight:600;white-space:nowrap}}
  .warn-box{{background:#fffbeb;border:1px solid #fcd34d;border-radius:10px;padding:14px 18px;margin-bottom:16px;font-size:12px;color:#78350f}}
  .chip{{padding:4px 12px;border:1px solid #e2e8f0;border-radius:9999px;background:#fff;cursor:pointer;font-size:11px;font-weight:500;color:#475569;margin:2px;transition:all .15s}}
  .chip:hover{{background:#f1f5f9}}
  .chip.active{{background:#1e293b;color:#fff;border-color:#1e293b}}
  details summary::-webkit-details-marker{{display:none}}
  details summary{{user-select:none}}
  details[open] summary span:last-child{{transform:rotate(180deg);display:inline-block}}
  @media(max-width:900px){{.charts-row{{grid-template-columns:1fr 1fr}}.cards{{grid-template-columns:repeat(2,1fr)}}}}
  @media(max-width:600px){{.charts-row{{grid-template-columns:1fr}}.topbar{{flex-direction:column;align-items:flex-start;gap:4px}}}}
  .nav-toggle{{display:none;position:fixed;bottom:20px;right:20px;z-index:999;background:#1e293b;color:#fff;border:none;border-radius:50%;width:44px;height:44px;font-size:20px;cursor:pointer;box-shadow:0 4px 12px rgba(0,0,0,.25)}}
  @media(max-width:768px){{
    .sidenav{{position:fixed;top:0;left:-220px;height:100vh;z-index:998;border-radius:0;margin:0;transition:left .25s;overflow-y:auto}}
    .sidenav.open{{left:0;box-shadow:4px 0 20px rgba(0,0,0,.15)}}
    .nav-toggle{{display:flex;align-items:center;justify-content:center}}
    .container{{padding:16px}}
    .layout{{display:block}}
  }}
</style>
</head>
<body>

<div class="topbar">
  <div>
    <div class="meta">CNPJ Impact Scanner &nbsp;·&nbsp; Regras: {versao_regras} &nbsp;·&nbsp; Spec v{data['spec_versao']}</div>
    <h1>📊 Dashboard de Impacto – CNPJ Alfanumérico</h1>
    <div class="meta">Sistema: <strong>{data['sistema_escopo']}</strong> &nbsp;·&nbsp; Gerado em: {data_exec}{f' &nbsp;·&nbsp; <code style="background:#334155;color:#94a3b8;padding:1px 6px;border-radius:4px;font-size:10px">{scan_id}</code>' if scan_id else ''} &nbsp;·&nbsp; Prazo migração: <strong>{data_limite}</strong></div>
  </div>
  <div style="display:flex;gap:10px;align-items:center">
    <a href="impacto_cnpj.md" target="_blank"
       style="display:flex;align-items:center;gap:6px;padding:7px 14px;background:#334155;color:#e2e8f0;border-radius:8px;font-size:12px;font-weight:600;text-decoration:none;border:1px solid #475569">
      📄 Ver MD
    </a>
    <button onclick="window.print()"
       style="display:flex;align-items:center;gap:6px;padding:7px 14px;background:#6366f1;color:#fff;border-radius:8px;font-size:12px;font-weight:600;border:none;cursor:pointer">
      🖨️ Imprimir
    </button>
  </div>
</div>

<button class="nav-toggle" id="nav-toggle" onclick="toggleNav()" title="Menu">☰</button>
<div class="layout">
<nav class="sidenav" id="sidenav">
  <a href="#sec-kpi">📊 KPIs</a>
  <a href="#sec-progresso">📈 Progresso</a>
  <a href="#sec-fluxos">🔀 Fluxos <span class="nav-cnt">{len(fluxos)}</span></a>
  <a href="#sec-charts">📉 Gráficos</a>
  <div class="nav-sep"></div>
  <a href="#sec-cobertura">🔭 Cobertura <span class="nav-cnt">{len(pontos_cegos)}</span></a>
  <a href="#sec-parceiros">🤝 Parceiros <span class="nav-cnt">{len(parceiros)}</span></a>
  <div class="nav-sep"></div>
  <a href="#sec-trilhas">&#128256; Trilhas <span class="nav-cnt">{trilhas_data['n_trilhas'] if trilhas_data else 0}</span></a>
  <a href="#sec-heatmap">&#127777;&#65039; Heatmap <span class="nav-cnt">{len(heatmap)}</span></a>
  <a href="#sec-spof">&#9889; SPOFs <span class="nav-cnt">{len(spof)}</span></a>
  <a href="#sec-gargalos">🔥 Gargalos <span class="nav-cnt">{len(gargalos)}</span></a>
  <a href="#sec-risk-score">&#127922; Risk Score <span class="nav-cnt">{len(risk_score)}</span></a>
  <a href="#sec-sugestoes">&#128260; Movimenta&#231;&#227;o <span class="nav-cnt">{len(sugestoes)}</span></a>
  <a href="#sec-refatoracao">&#9881;&#65039; Refatora&#231;&#227;o <span class="nav-cnt">{len(oportunidades)}</span></a>
  <a href="#sec-diff">&#128260; Diff <span class="nav-cnt">{(diff['resumo']['novos'] + diff['resumo']['resolvidos'] + diff['resumo']['alterados']) if diff else 0}</span></a>
  <a href="#sec-esforco">&#9201;&#65039; Esfor&ccedil;o <span class="nav-cnt">{len(esforco)}</span></a>
  <a href="#sec-criterios">&#9989; Aceite <span class="nav-cnt">{len(criterios)}</span></a>
  <a href="#sec-telas-qa">🧪 Telas QA <span class="nav-cnt">{len(telas_qa)}</span></a>
  <a href="#sec-pj">&#127962; Pessoa Jur&#237;dica</a>
  <a href="#sec-correcoes">🔧 Correções</a>
  <a href="#sec-ordem">🗺️ Módulos <span class="nav-cnt">{len(ordem)}</span></a>
  <a href="#sec-criticos">🚨 Críticos <span class="nav-cnt">{len(criticos)}</span></a>
  <a href="#sec-matriz">📋 Matriz <span class="nav-cnt">{len(repos)}</span></a>
</nav>
<div class="container">

  <!-- KPI Cards -->
  <div id="sec-kpi" class="cards">
    <div class="card" style="--accent:#6366f1">
      <div class="val">{stats['total_impactos_encontrados']}</div>
      <div class="lbl">Total de Impactos</div>
    </div>
    <div class="card" style="--accent:#ef4444">
      <div class="val">{complexid.get('Alta',0)}</div>
      <div class="lbl">Alta Complexidade</div>
    </div>
    <div class="card" style="--accent:#f59e0b">
      <div class="val">{complexid.get('Média',0)}</div>
      <div class="lbl">Média Complexidade</div>
    </div>
    <div class="card" style="--accent:#3b82f6">
      <div class="val">{stats.get('requerem_compatibilidade_dual',0)}</div>
      <div class="lbl">Requerem Dual Compat</div>
    </div>
    <div class="card" style="--accent:#10b981">
      <div class="val">{stats.get('arquivos_criticos',0)}</div>
      <div class="lbl">Arquivos Críticos</div>
    </div>
    <div class="card" style="--accent:#8b5cf6">
      <div class="val">{cobertura_card_val}</div>
      <div class="lbl">Repos com Impacto</div>
    </div>
    <div class="card" style="--accent:#f59e0b">
      <div class="val">{len(aliases_suspeitos)}</div>
      <div class="lbl">Repos Suspeitos ⚠️</div>
    </div>
    <div class="card" style="--accent:#7c3aed">
      <div class="val">{len(spof)}</div>
      <div class="lbl">&#9889; SPOFs</div>
    </div>
    <div class="card" style="--accent:#ef4444">
      <div class="val">{len(gargalos)}</div>
      <div class="lbl">🔥 Gargalos</div>
    </div>
  </div>

  <!-- Progresso -->
  {_build_progresso_html(progresso, stats['total_impactos_encontrados'])}

  <!-- Fluxos de Negócio (visão macro) -->
  <div class="section" id="sec-fluxos">
    <h2>🔀 Fluxos de Negócio — Visão Macro</h2>
    <div style="background:#eff6ff;border:1px solid #bfdbfe;border-radius:8px;padding:10px 14px;font-size:12px;color:#1e40af;margin-bottom:14px">
      ℹ️ Impactos agrupados por fluxo funcional inferido. Clique em um fluxo para ver repos e áreas envolvidas.
    </div>
    {fluxo_cards}
  </div>

  <!-- Charts -->
  <div id="sec-charts" class="section">
    <div class="charts-row">
      <div class="chart-box">
        <h3>🗂️ Impactos por Área</h3>
        <canvas id="chartArea"></canvas>
      </div>
      <div class="chart-box">
        <h3>⚡ Distribuição por Complexidade</h3>
        <canvas id="chartCompl" height="220"></canvas>
      </div>
      <div class="chart-box">
        <h3>📦 Impactos por Repositório (top)</h3>
        <canvas id="chartRepo" height="220"></canvas>
      </div>
    </div>
  </div>

  <!-- Cobertura / Pontos Cegos -->
  <div class="section" id="sec-cobertura">
    <details open>
    <summary style="list-style:none;cursor:pointer;display:flex;align-items:center;justify-content:space-between;margin-bottom:16px"><h2 style="margin:0">🔭 Cobertura da Varredura</h2><span style="font-size:16px;color:#94a3b8">&#9662;</span></summary>
    <div class="warn-box">
      ⚠️ Esta varredura detecta apenas onde o código <strong>trata CNPJ como numérico</strong> (regex <code>&#92;d{{14}}</code>, máscaras, <code>Long.parseLong</code>, etc.).
      Campos declarados como <code>String</code> ou <code>VARCHAR</code> sem constraint numérica passam invisíveis mesmo que quebrem com letras.
      Repos marcados com ⚠️ na aba abaixo usam aliases suspeitos e requerem revisão manual.
    </div>

    <h3 style="font-size:13px;font-weight:600;margin-bottom:10px;color:#475569">Pontos Cegos Identificados</h3>
    <div style="overflow-x:auto;margin-bottom:20px">
      <table class="imp-table">
        <thead><tr><th>ID</th><th>Limitação</th><th>Recomendação</th></tr></thead>
        <tbody>{pc_rows}</tbody>
      </table>
    </div>

    {'<h3 style="font-size:13px;font-weight:600;margin-bottom:10px;color:#92400e">⚠️ Repos sem impacto mas com aliases suspeitos</h3><div style="overflow-x:auto;margin-bottom:20px"><table class="imp-table"><thead><tr><th>Repositório</th><th>Aliases encontrados</th><th>Ação</th></tr></thead><tbody>' + alias_rows + '</tbody></table></div>' if alias_rows else ''}

    <h3 style="font-size:13px;font-weight:600;margin-bottom:10px;color:#475569">Repositórios sem impacto detectado ({len(repos_sem_impacto)})</h3>
    <div style="line-height:2">{sem_impacto_tags if sem_impacto_tags else '<span style="color:#9ca3af">Nenhum — todos os repos têm ao menos um impacto.</span>'}</div>
    </details>
  </div>

  <!-- Parceiros Externos -->
  {_build_parceiros_html(parceiros)}

  <!-- Heatmap de Risco -->
  {_build_heatmap_html(heatmap)}

  <!-- SPOFs -->
  {_build_spof_html(spof)}

  <!-- Gargalos Arquiteturais -->
  {_build_gargalos_html(gargalos)}

  <!-- Trilhas Paralelas -->
  {_build_trilhas_html(trilhas_data)}

  <!-- Risk Score -->
  {_build_risk_score_html(risk_score)}

  <!-- Sugestões de Movimentação -->
  {_build_sugestoes_html(sugestoes)}

  <!-- Oportunidades de Refatoração -->
  {_build_refatoracao_html(oportunidades)}

  <!-- Diff entre Scans -->
  {_build_diff_html(diff)}

  <!-- Estimativa de Esforço -->
  {_build_esforco_html(esforco)}

  <!-- Critérios de Aceite -->
  {_build_criterios_html(criterios)}

  <!-- Telas QA -->
  {_build_telas_qa_html(telas_qa)}

  <!-- Pessoa Juridica -->
  {pj_html}



  <!-- Correções por Área -->
  <div class="section" id="sec-correcoes">
    <details open>
    <summary style="list-style:none;cursor:pointer;display:flex;align-items:center;justify-content:space-between;margin-bottom:16px"><h2 style="margin:0">🔧 Exemplos de Correção por Área</h2><span style="font-size:16px;color:#94a3b8">&#9662;</span></summary>
    <div style="background:#f0fdf4;border:1px solid #bbf7d0;border-radius:8px;padding:10px 14px;font-size:12px;color:#065f46;margin-bottom:14px">
      ℹ️ Padrões de correção mais comuns por área. <strong style="color:#991b1b">Antes</strong> = código problemático. <strong style="color:#065f46">Depois</strong> = correção recomendada.
    </div>
    <div style="overflow-x:auto">
      <table class="imp-table">
        <thead><tr>
          <th>Área</th><th>Problema</th>
          <th style="background:#fee2e2;color:#991b1b">❌ Antes</th>
          <th style="background:#d1fae5;color:#065f46">✅ Depois</th>
        </tr></thead>
        <tbody>
        <tr><td style="font-weight:700;font-size:11px;vertical-align:top;white-space:nowrap"><span class="area-tag">Banco de Dados</span></td><td style="font-size:11px;color:#374151">Coluna com tamanho insuficiente</td><td><code style="background:#fee2e2;color:#991b1b;padding:2px 6px;border-radius:4px;font-size:11px;white-space:nowrap">VARCHAR(14)</code></td><td><code style="background:#d1fae5;color:#065f46;padding:2px 6px;border-radius:4px;font-size:11px;white-space:nowrap">VARCHAR(20)</code></td></tr>
        <tr><td></td><td style="font-size:11px;color:#374151">Tipo numérico para CNPJ</td><td><code style="background:#fee2e2;color:#991b1b;padding:2px 6px;border-radius:4px;font-size:11px;white-space:nowrap">NUMBER(14) / BIGINT</code></td><td><code style="background:#d1fae5;color:#065f46;padding:2px 6px;border-radius:4px;font-size:11px;white-space:nowrap">VARCHAR(20)</code></td></tr>
        <tr><td></td><td style="font-size:11px;color:#374151">Constraint de tamanho fixo</td><td><code style="background:#fee2e2;color:#991b1b;padding:2px 6px;border-radius:4px;font-size:11px;white-space:nowrap">CHECK (LENGTH(cnpj) = 14)</code></td><td><code style="background:#d1fae5;color:#065f46;padding:2px 6px;border-radius:4px;font-size:11px;white-space:nowrap">CHECK (LENGTH(cnpj) BETWEEN 14 AND 20)</code></td></tr>
        <tr><td></td><td style="font-size:11px;color:#374151">Script Flyway com tipo errado</td><td><code style="background:#fee2e2;color:#991b1b;padding:2px 6px;border-radius:4px;font-size:11px;white-space:nowrap">MODIFY cnpj NUMBER(14)</code></td><td><code style="background:#d1fae5;color:#065f46;padding:2px 6px;border-radius:4px;font-size:11px;white-space:nowrap">MODIFY cnpj VARCHAR2(20)</code></td></tr>
        <tr><td style="font-weight:700;font-size:11px;vertical-align:top;white-space:nowrap"><span class="area-tag">Backend</span></td><td style="font-size:11px;color:#374151">Regex numérica de validação</td><td><code style="background:#fee2e2;color:#991b1b;padding:2px 6px;border-radius:4px;font-size:11px;white-space:nowrap">\d&#123;14&#125;</code></td><td><code style="background:#d1fae5;color:#065f46;padding:2px 6px;border-radius:4px;font-size:11px;white-space:nowrap">[A-Z0-9]&#123;14,20&#125;</code></td></tr>
        <tr><td></td><td style="font-size:11px;color:#374151">Manipulação posicional (raiz)</td><td><code style="background:#fee2e2;color:#991b1b;padding:2px 6px;border-radius:4px;font-size:11px;white-space:nowrap">cnpj.substring(0, 8)</code></td><td><code style="background:#d1fae5;color:#065f46;padding:2px 6px;border-radius:4px;font-size:11px;white-space:nowrap">CnpjUtils.getRaiz(cnpj)</code></td></tr>
        <tr><td></td><td style="font-size:11px;color:#374151">Manipulação posicional (filial)</td><td><code style="background:#fee2e2;color:#991b1b;padding:2px 6px;border-radius:4px;font-size:11px;white-space:nowrap">cnpj.substring(8, 12)</code></td><td><code style="background:#d1fae5;color:#065f46;padding:2px 6px;border-radius:4px;font-size:11px;white-space:nowrap">CnpjUtils.getFilial(cnpj)</code></td></tr>
        <tr><td></td><td style="font-size:11px;color:#374151">Parse numérico</td><td><code style="background:#fee2e2;color:#991b1b;padding:2px 6px;border-radius:4px;font-size:11px;white-space:nowrap">Long.parseLong(cnpj)</code></td><td><code style="background:#d1fae5;color:#065f46;padding:2px 6px;border-radius:4px;font-size:11px;white-space:nowrap">manter como String</code></td></tr>
        <tr><td style="font-weight:700;font-size:11px;vertical-align:top;white-space:nowrap"><span class="area-tag">Frontend</span></td><td style="font-size:11px;color:#374151">Máscara numérica</td><td><code style="background:#fee2e2;color:#991b1b;padding:2px 6px;border-radius:4px;font-size:11px;white-space:nowrap">mask='##.###.###/####-##'</code></td><td><code style="background:#d1fae5;color:#065f46;padding:2px 6px;border-radius:4px;font-size:11px;white-space:nowrap">mask='AA.AAA.AAA/AAAA-##'</code></td></tr>
        <tr><td></td><td style="font-size:11px;color:#374151">inputMode numérico</td><td><code style="background:#fee2e2;color:#991b1b;padding:2px 6px;border-radius:4px;font-size:11px;white-space:nowrap">inputMode="numeric"</code></td><td><code style="background:#d1fae5;color:#065f46;padding:2px 6px;border-radius:4px;font-size:11px;white-space:nowrap">inputMode="text"</code></td></tr>
        <tr><td></td><td style="font-size:11px;color:#374151">Regex de validação no input</td><td><code style="background:#fee2e2;color:#991b1b;padding:2px 6px;border-radius:4px;font-size:11px;white-space:nowrap">/^\d&#123;14&#125;$/</code></td><td><code style="background:#d1fae5;color:#065f46;padding:2px 6px;border-radius:4px;font-size:11px;white-space:nowrap">/^[A-Z0-9]&#123;14,20&#125;$/</code></td></tr>
        <tr><td style="font-weight:700;font-size:11px;vertical-align:top;white-space:nowrap"><span class="area-tag">API/Contrato</span></td><td style="font-size:11px;color:#374151">Pattern numérico no OpenAPI</td><td><code style="background:#fee2e2;color:#991b1b;padding:2px 6px;border-radius:4px;font-size:11px;white-space:nowrap">pattern: '^\d&#123;14&#125;$'</code></td><td><code style="background:#d1fae5;color:#065f46;padding:2px 6px;border-radius:4px;font-size:11px;white-space:nowrap">pattern: '^[A-Z0-9]&#123;14,20&#125;$'</code></td></tr>
        <tr><td></td><td style="font-size:11px;color:#374151">maxLength insuficiente</td><td><code style="background:#fee2e2;color:#991b1b;padding:2px 6px;border-radius:4px;font-size:11px;white-space:nowrap">maxLength: 14</code></td><td><code style="background:#d1fae5;color:#065f46;padding:2px 6px;border-radius:4px;font-size:11px;white-space:nowrap">maxLength: 20</code></td></tr>
        <tr><td style="font-weight:700;font-size:11px;vertical-align:top;white-space:nowrap"><span class="area-tag">Integrações</span></td><td style="font-size:11px;color:#374151">Validação numérica no payload</td><td><code style="background:#fee2e2;color:#991b1b;padding:2px 6px;border-radius:4px;font-size:11px;white-space:nowrap">cnpj.matches('&#92;&#92;d&#123;14&#125;')</code></td><td><code style="background:#d1fae5;color:#065f46;padding:2px 6px;border-radius:4px;font-size:11px;white-space:nowrap">cnpj.matches('[A-Z0-9]&#123;14,20&#125;')</code></td></tr>
        <tr><td style="font-weight:700;font-size:11px;vertical-align:top;white-space:nowrap"><span class="area-tag">Processamento/Batch</span></td><td style="font-size:11px;color:#374151">Máscara de formatação numérica</td><td><code style="background:#fee2e2;color:#991b1b;padding:2px 6px;border-radius:4px;font-size:11px;white-space:nowrap">##.###.###/####-##</code></td><td><code style="background:#d1fae5;color:#065f46;padding:2px 6px;border-radius:4px;font-size:11px;white-space:nowrap">remover máscara fixa — aceitar alfanumérico</code></td></tr>
        <tr><td></td><td style="font-size:11px;color:#374151">Layout fixo SPED/CNAB</td><td><code style="background:#fee2e2;color:#991b1b;padding:2px 6px;border-radius:4px;font-size:11px;white-space:nowrap">posição 1-14 numérico</code></td><td><code style="background:#d1fae5;color:#065f46;padding:2px 6px;border-radius:4px;font-size:11px;white-space:nowrap">posição 1-20 alfanumérico</code></td></tr>
        <tr><td style="font-weight:700;font-size:11px;vertical-align:top;white-space:nowrap"><span class="area-tag">Segurança/LGPD</span></td><td style="font-size:11px;color:#374151">CNPJ real hardcoded</td><td><code style="background:#fee2e2;color:#991b1b;padding:2px 6px;border-radius:4px;font-size:11px;white-space:nowrap">cnpj = '11.222.333/0001-81'</code></td><td><code style="background:#d1fae5;color:#065f46;padding:2px 6px;border-radius:4px;font-size:11px;white-space:nowrap">cnpj = System.getenv('CNPJ_TEST')</code></td></tr>
        <tr><td style="font-weight:700;font-size:11px;vertical-align:top;white-space:nowrap"><span class="area-tag">Configuração</span></td><td style="font-size:11px;color:#374151">CNPJ fixo em properties</td><td><code style="background:#fee2e2;color:#991b1b;padding:2px 6px;border-radius:4px;font-size:11px;white-space:nowrap">app.cnpj=11222333000181</code></td><td><code style="background:#d1fae5;color:#065f46;padding:2px 6px;border-radius:4px;font-size:11px;white-space:nowrap">app.cnpj=$&#123;CNPJ_EMPRESA&#125;</code></td></tr></tbody>
      </table>
    </div>
    </details>
  </div>

  <!-- Ordem de Migração por Módulo -->
  <div class="section" id="sec-ordem">
    <h2>🗺️ Ordem de Migração por Módulo</h2>
    <div style="background:#eff6ff;border:1px solid #bfdbfe;border-radius:8px;padding:10px 14px;font-size:12px;color:#1e40af;margin-bottom:14px">
      ℹ️ Cada módulo (repositório) é migrado de forma independente. A sequência interna de áreas dentro de cada módulo segue a ordem de dependência técnica.
    </div>
    {ordem_cards}
  </div>

  <!-- Arquivos Críticos -->
  <div class="section" id="sec-criticos">
    <details open>
    <summary style="list-style:none;cursor:pointer;display:flex;align-items:center;justify-content:space-between;margin-bottom:16px"><h2 style="margin:0">🚨 Arquivos Críticos <span style="font-size:11px;font-weight:400;color:#64748b;margin-left:4px">(maior número de chamadores — efeito cascata)</span></h2><span style="font-size:16px;color:#94a3b8">&#9662;</span></summary>
    <div style="overflow-x:auto">
      <table class="imp-table">
        <thead><tr>
          <th>#</th><th>Repositório</th><th>Arquivo</th><th>Área</th>
          <th>Chamadores</th><th>Impactos</th><th>Dual</th><th>Linhas</th>
        </tr></thead>
        <tbody>{crit_rows}</tbody>
      </table>
    </div>
    </details>
  </div>

  <!-- Matriz por Repositório -->
  <div class="section" id="sec-matriz">
    <h2>📋 Matriz de Impacto por Repositório</h2>
    <div style="font-size:11px;color:#6b7280;margin-bottom:12px">
      Repos com <span style="color:#f59e0b;font-weight:700">⚠️</span> têm aliases suspeitos.
      Passe o mouse sobre os botões para ver quantos candidatos foram analisados.
      Clique em uma linha da tabela para abrir o repositório.
    </div>

    <!-- Tabela resumo -->
    <div style="overflow-x:auto;margin-bottom:20px">
      <table class="imp-table" id="tbl-resumo">
        <thead><tr>
          <th onclick="sortResumo('repo')" style="cursor:pointer">Repositório <span class="sort-icon">↕</span></th>
          <th onclick="sortResumo('sprint')" style="cursor:pointer;text-align:center">Sprint <span class="sort-icon">↕</span></th>
          <th onclick="sortResumo('cand')" style="cursor:pointer;text-align:center">Candidatos <span class="sort-icon">↕</span></th>
          <th onclick="sortResumo('cnt')" style="cursor:pointer">Impactos <span class="sort-icon">↕</span></th>
          <th onclick="sortResumo('alta')" style="cursor:pointer;text-align:center">Alta <span class="sort-icon">↕</span></th>
          <th onclick="sortResumo('dual')" style="cursor:pointer;text-align:center">Dual <span class="sort-icon">↕</span></th>
          <th style="text-align:center">Taxa conv.</th>
        </tr></thead>
        <tbody>{resumo_rows}</tbody>
      </table>
    </div>

    <input type="text" placeholder="🔍 Buscar repositório…" oninput="filterTabs(this)"
      style="width:100%;max-width:360px;padding:7px 12px;border:1px solid #d1d5db;border-radius:8px;font-size:12px;margin-bottom:10px;display:block">

    <!-- Chips de filtro global -->
    <div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:10px;padding:10px 14px;margin-bottom:14px;display:flex;flex-wrap:wrap;align-items:center;gap:6px">
      <span style="font-size:11px;color:#64748b;font-weight:600;margin-right:2px">Área:</span>{area_chips}
      <span style="width:1px;height:20px;background:#e2e8f0;margin:0 6px"></span>
      <span style="font-size:11px;color:#64748b;font-weight:600;margin-right:2px">Complexidade:</span>{compl_chips}
      <button onclick="clearChips()" style="margin-left:auto;padding:4px 10px;border:1px solid #e2e8f0;border-radius:6px;background:#fff;font-size:11px;color:#64748b;cursor:pointer">✕ Limpar</button>
      <span id="filter-count" style="font-size:11px;color:#6366f1;font-weight:600"></span>
    </div>

    <div class="tab-bar" id="tab-bar">{tab_buttons}</div>
    {repo_tables}
    <div id="repo-placeholder" style="color:#94a3b8;text-align:center;padding:32px;font-size:13px">
      ← Selecione um repositório para ver os impactos
    </div>
  </div>

</div><!-- /container -->
</div><!-- /layout -->

<script>
const areaCtx = document.getElementById('chartArea').getContext('2d');
(function() {{
  const pairs = {area_labels_js}.map((l,i) => [l, {area_values_js}[i]]).sort((a,b) => b[1]-a[1]);
  new Chart(areaCtx, {{
    type: 'bar',
    data: {{ labels: pairs.map(p=>p[0]), datasets: [{{ data: pairs.map(p=>p[1]), backgroundColor: {area_colors_js}, borderRadius: 4, borderSkipped: false }}] }},
    options: {{
      indexAxis: 'y',
      plugins: {{ legend: {{ display: false }} }},
      scales: {{
        x: {{ beginAtZero: true, grid: {{ color: '#f1f5f9' }} }},
        y: {{ grid: {{ display: false }}, ticks: {{ font: {{ size: 11 }} }} }}
      }}
    }}
  }});
}})();

const complCtx = document.getElementById('chartCompl').getContext('2d');
new Chart(complCtx, {{
  type: 'bar',
  data: {{ labels: {compl_labels_js}, datasets: [{{ data: {compl_values_js}, backgroundColor: {compl_bg_js}, borderRadius: 6, borderSkipped: false }}] }},
  options: {{ plugins: {{ legend: {{ display: false }} }}, scales: {{ y: {{ beginAtZero: true, grid: {{ color: '#f1f5f9' }} }}, x: {{ grid: {{ display: false }} }} }} }}
}});

const repoCtx = document.getElementById('chartRepo').getContext('2d');
(function() {{
  const pairs = Object.entries({{}}).concat(
    {repo_labels_js}.map((l,i) => [l, {repo_values_js}[i]])
  ).sort((a,b) => b[1]-a[1]).slice(0,15);
  new Chart(repoCtx, {{
    type: 'bar',
    data: {{ labels: pairs.map(p=>p[0]), datasets: [{{ data: pairs.map(p=>p[1]), backgroundColor: '#6366f1', borderRadius: 4, borderSkipped: false }}] }},
    options: {{
      indexAxis: 'y',
      plugins: {{ legend: {{ display: false }} }},
      scales: {{
        x: {{ beginAtZero: true, grid: {{ color: '#f1f5f9' }} }},
        y: {{ grid: {{ display: false }}, ticks: {{ font: {{ size: 11 }} }} }}
      }}
    }}
  }});
}})();

function selectRepo(repo) {{
  document.querySelectorAll('.repo-panel').forEach(p => p.style.display = 'none');
  document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
  document.getElementById('repo-placeholder').style.display = 'none';
  const panel = document.getElementById('repo-' + repo);
  if (panel) panel.style.display = 'block';
  const btn = [...document.querySelectorAll('.tab-btn')].find(b => b.textContent.trim().startsWith(repo));
  if (btn) {{ btn.classList.add('active'); btn.scrollIntoView({{block:'nearest'}}); }}
  document.getElementById('tab-bar').scrollIntoView({{behavior:'smooth', block:'nearest'}});
  applyFilters(repo);
}}

function showRepo(repo) {{
  selectRepo(repo);
}}

function filterTabs(input) {{
  const q = input.value.toLowerCase();
  document.querySelectorAll('#tab-bar .tab-btn').forEach(btn => {{
    if (btn.id === 'btn-sem-impacto') return;
    btn.style.display = btn.textContent.toLowerCase().includes(q) ? '' : 'none';
  }});
}}

function toggleSemImpacto(btn) {{
  const el = document.getElementById('tabs-sem-impacto');
  if (!el) return;
  const open = el.style.display !== 'none';
  el.style.display = open ? 'none' : 'inline';
  btn.textContent = open ? btn.textContent.replace('▲','').trim() + '' : '▲ ocultar sem impacto';
}}

let activeFilters = {{area: new Set(), compl: new Set()}};

function toggleChip(btn) {{
  const type = btn.dataset.filter;
  const val  = btn.dataset.val;
  if (activeFilters[type].has(val)) {{
    activeFilters[type].delete(val);
    btn.classList.remove('active');
  }} else {{
    activeFilters[type].add(val);
    btn.classList.add('active');
  }}
  const panel = document.querySelector('.repo-panel[style*="block"]');
  if (panel) applyFilters(panel.id.replace('repo-', ''));
}}

function clearChips() {{
  activeFilters = {{area: new Set(), compl: new Set()}};
  document.querySelectorAll('.chip').forEach(c => c.classList.remove('active'));
  const panel = document.querySelector('.repo-panel[style*="block"]');
  if (panel) applyFilters(panel.id.replace('repo-', ''));
}}

function applyFilters(repo) {{
  const tbl   = document.getElementById('tbl-' + repo);
  if (!tbl) return;
  const q     = (document.getElementById('search-' + repo)?.value || '').toLowerCase();
  const areas = activeFilters.area;
  const compl = activeFilters.compl;
  let vis = 0, tot = 0;
  tbl.querySelectorAll('tbody tr').forEach(tr => {{
    tot++;
    const okArea  = areas.size === 0 || areas.has(tr.dataset.area);
    const okCompl = compl.size === 0 || compl.has(tr.dataset.compl);
    const okText  = q === '' || tr.textContent.toLowerCase().includes(q);
    const show    = okArea && okCompl && okText;
    tr.style.display = show ? '' : 'none';
    if (show) vis++;
  }});
  const cnt = document.getElementById('cnt-' + repo);
  if (cnt) cnt.textContent = (vis < tot) ? `${{vis}} de ${{tot}} visíveis` : '';
  const fc = document.getElementById('filter-count');
  if (fc) fc.textContent = (areas.size + compl.size) > 0 ? `${{areas.size + compl.size}} filtro(s) ativo(s)` : '';
}}

const firstBtn = document.querySelector('.tab-btn');
if (firstBtn) firstBtn.click();

// ---- ordenação tabela resumo ----
let _resumoSort = {{col: 'cnt', asc: false}};
function sortResumo(col) {{
  const tbody = document.querySelector('#tbl-resumo tbody');
  const rows  = [...tbody.querySelectorAll('tr')];
  _resumoSort.asc = _resumoSort.col === col ? !_resumoSort.asc : false;
  _resumoSort.col = col;
  const val = r => {{
    if (col === 'repo')   return r.dataset.repo || '';
    if (col === 'sprint') return +r.dataset.sprint || 9999;
    if (col === 'cnt')    return +r.dataset.cnt || 0;
    if (col === 'alta')   return +r.dataset.alta || 0;
    if (col === 'dual')   return +r.dataset.dual || 0;
    if (col === 'cand')   return +(r.cells[2]?.textContent.trim()) || 0;
    return 0;
  }};
  rows.sort((a,b) => {{
    const av = val(a), bv = val(b);
    const cmp = typeof av === 'string' ? av.localeCompare(bv) : av - bv;
    return _resumoSort.asc ? cmp : -cmp;
  }});
  rows.forEach(r => tbody.appendChild(r));
  document.querySelectorAll('#tbl-resumo .sort-icon').forEach(s => s.textContent = '↕');
  const ths = document.querySelectorAll('#tbl-resumo thead th');
  const colIdx = {{repo:0, sprint:1, cand:2, cnt:3, alta:4, dual:5}}[col];
  if (ths[colIdx]) ths[colIdx].querySelector('.sort-icon').textContent = _resumoSort.asc ? '↑' : '↓';
}}

// sidenav mobile toggle
function toggleNav() {{
  const nav = document.getElementById('sidenav');
  nav.classList.toggle('open');
}}
// fechar sidenav ao clicar em link (mobile)
document.querySelectorAll('.sidenav a').forEach(a => a.addEventListener('click', () => {{
  if (window.innerWidth <= 768) document.getElementById('sidenav').classList.remove('open');
}}));

// scroll spy sidenav
const navLinks = document.querySelectorAll('.sidenav a');
const sections = [...navLinks].map(a => document.querySelector(a.getAttribute('href'))).filter(Boolean);
window.addEventListener('scroll', () => {{
  let cur = sections[0];
  sections.forEach(s => {{ if (window.scrollY >= s.offsetTop - 80) cur = s; }});
  navLinks.forEach(a => a.classList.toggle('active', a.getAttribute('href') === '#' + cur.id));
}}, {{passive:true}});
</script>
</body>
</html>"""


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

_DEFAULT_JSON = Path(__file__).parent.parent / "docs" / "output" / "impacto_cnpj.json"

def main():
    src = Path(sys.argv[1]) if len(sys.argv) > 1 else _DEFAULT_JSON
    if not src.exists():
        # fallback: procura no diretório atual
        src = Path("impacto_cnpj.json")
    if not src.exists():
        print(f"[erro] Arquivo não encontrado: {src}")
        sys.exit(1)

    data = json.loads(src.read_text(encoding="utf-8"))
    html = build_dashboard(data)

    out = src.with_suffix(".html")
    out.write_text(html, encoding="utf-8")
    print(f"[ok] Dashboard gerado: {out}")


if __name__ == "__main__":
    main()
