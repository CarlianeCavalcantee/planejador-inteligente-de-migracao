from reportlab.platypus import (
    Paragraph, Spacer, Table, TableStyle, HRFlowable, PageBreak,
)
from reportlab.lib.units import cm
from reportlab.lib import colors

from styles import (
    build_styles, AZUL_ESCURO, AZUL_MEDIO, AZUL_CLARO,
    CINZA_LINHA, CINZA_BORDA, BRANCO, PRETO,
    cor_complexidade, cor_prioridade,
)

S = build_styles()

# ── Utilitários ──────────────────────────────────────────────────────────────
def _p(text, style="corpo"):
    return Paragraph(str(text or "—"), S[style])

def _hr():
    return HRFlowable(width="100%", thickness=0.5, color=CINZA_BORDA, spaceAfter=6)

def _header_table(cols, col_widths):
    """Linha de cabeçalho de tabela com fundo azul escuro."""
    row = [_p(f"<b>{c}</b>", "celula_bold") for c in cols]
    t = Table([row], colWidths=col_widths)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), AZUL_ESCURO),
        ("TEXTCOLOR",  (0, 0), (-1, 0), BRANCO),
        ("FONTNAME",   (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE",   (0, 0), (-1, 0), 8),
        ("TOPPADDING", (0, 0), (-1, 0), 5),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 5),
        ("LEFTPADDING",   (0, 0), (-1, 0), 6),
    ]))
    return t

def _section_title(text):
    bg = Table([[_p(f"<b>{text}</b>", "secao")]], colWidths=["100%"])
    bg.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), AZUL_ESCURO),
        ("TOPPADDING",    (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ("LEFTPADDING",   (0, 0), (-1, -1), 10),
        ("ROUNDEDCORNERS", [4, 4, 4, 4]),
    ]))
    return bg

# ── Capa ─────────────────────────────────────────────────────────────────────
def build_capa(meta: dict) -> list:
    elems = []
    capa = Table(
        [[_p("<b>SPEC – Análise de Impacto do CNPJ Alfanumérico</b>", "titulo_doc")],
         [_p(f"Sistema: {meta['sistema']}  |  Versão: {meta['versao']}  |  Data: {meta['data_execucao']}", "subtitulo_doc")]],
        colWidths=["100%"],
    )
    capa.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), AZUL_ESCURO),
        ("TOPPADDING",    (0, 0), (-1, -1), 28),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 28),
        ("LEFTPADDING",   (0, 0), (-1, -1), 20),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 20),
    ]))
    elems.append(capa)
    elems.append(Spacer(1, 0.5 * cm))
    return elems

# ── Sumário Executivo ────────────────────────────────────────────────────────
def build_sumario(stats: dict) -> list:
    elems = [_section_title("1. Sumário Executivo"), Spacer(1, 0.3 * cm)]

    # Cards de métricas
    cards_data = [
        ("Repositórios Analisados", stats["total_repos"]),
        ("Com Impacto",             stats["repos_com_impacto"]),
        ("Total de Impactos",       stats["total_impactos"]),
        ("Arquivos Críticos",       stats["arquivos_criticos"]),
        ("Requerem Dual-Mode",      stats["requerem_dual"]),
        ("Chamadores Críticos",     f"{stats['chamadores_criticos']:,}"),
    ]
    card_rows = []
    row = []
    for i, (label, val) in enumerate(cards_data):
        cell = Table(
            [[_p(f"<b>{val}</b>", "secao")], [_p(label, "celula")]],
            colWidths=[4.5 * cm],
        )
        cell.setStyle(TableStyle([
            ("BACKGROUND",    (0, 0), (-1, -1), AZUL_CLARO),
            ("ALIGN",         (0, 0), (-1, -1), "CENTER"),
            ("TOPPADDING",    (0, 0), (-1, -1), 8),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ("ROUNDEDCORNERS", [4, 4, 4, 4]),
        ]))
        row.append(cell)
        if len(row) == 3:
            card_rows.append(row)
            row = []
    if row:
        while len(row) < 3:
            row.append(Spacer(4.5 * cm, 1))
        card_rows.append(row)

    for r in card_rows:
        t = Table([r], colWidths=[4.7 * cm, 4.7 * cm, 4.7 * cm])
        t.setStyle(TableStyle([("LEFTPADDING", (0,0),(-1,-1), 4),
                                ("RIGHTPADDING",(0,0),(-1,-1), 4)]))
        elems.append(t)
        elems.append(Spacer(1, 0.2 * cm))

    elems.append(Spacer(1, 0.3 * cm))

    # Impactos por área
    elems.append(_p("<b>Impactos por Área</b>", "subsecao"))
    area_rows = [[_p("<b>Área</b>", "celula_bold"), _p("<b>Qtd</b>", "celula_bold")]]
    for area, qtd in sorted(stats["por_area"].items(), key=lambda x: -x[1]):
        area_rows.append([_p(area, "celula"), _p(str(qtd), "celula")])
    t_area = Table(area_rows, colWidths=[10 * cm, 4 * cm])
    t_area.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, 0), AZUL_ESCURO),
        ("TEXTCOLOR",     (0, 0), (-1, 0), BRANCO),
        ("ROWBACKGROUNDS",(0, 1), (-1, -1), [BRANCO, CINZA_LINHA]),
        ("GRID",          (0, 0), (-1, -1), 0.4, CINZA_BORDA),
        ("TOPPADDING",    (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING",   (0, 0), (-1, -1), 6),
    ]))
    elems.append(t_area)
    elems.append(Spacer(1, 0.3 * cm))

    # Impactos por complexidade
    elems.append(_p("<b>Impactos por Complexidade</b>", "subsecao"))
    comp_rows = [[_p("<b>Complexidade</b>", "celula_bold"), _p("<b>Qtd</b>", "celula_bold")]]
    for comp, qtd in stats["por_complexidade"].items():
        bg, fg = cor_complexidade(comp)
        comp_rows.append([_p(comp, "celula"), _p(str(qtd), "celula")])
    t_comp = Table(comp_rows, colWidths=[10 * cm, 4 * cm])
    t_comp.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, 0), AZUL_ESCURO),
        ("TEXTCOLOR",     (0, 0), (-1, 0), BRANCO),
        ("ROWBACKGROUNDS",(0, 1), (-1, -1), [BRANCO, CINZA_LINHA]),
        ("GRID",          (0, 0), (-1, -1), 0.4, CINZA_BORDA),
        ("TOPPADDING",    (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING",   (0, 0), (-1, -1), 6),
    ]))
    elems.append(t_comp)
    elems.append(Spacer(1, 0.3 * cm))

    # Progresso
    prog = stats["progresso"]
    elems.append(_p("<b>Progresso dos Itens</b>", "subsecao"))
    prog_rows = [[_p("<b>Status</b>", "celula_bold"), _p("<b>Qtd</b>", "celula_bold")]]
    for k, v in prog.items():
        prog_rows.append([_p(k.replace("_", " ").title(), "celula"), _p(str(v), "celula")])
    t_prog = Table(prog_rows, colWidths=[10 * cm, 4 * cm])
    t_prog.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, 0), AZUL_ESCURO),
        ("TEXTCOLOR",     (0, 0), (-1, 0), BRANCO),
        ("ROWBACKGROUNDS",(0, 1), (-1, -1), [BRANCO, CINZA_LINHA]),
        ("GRID",          (0, 0), (-1, -1), 0.4, CINZA_BORDA),
        ("TOPPADDING",    (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING",   (0, 0), (-1, -1), 6),
    ]))
    elems.append(t_prog)
    return elems

# ── Impactos por Repositório ─────────────────────────────────────────────────
def build_por_repositorio(stats: dict) -> list:
    elems = [PageBreak(), _section_title("2. Impactos por Repositório"), Spacer(1, 0.3 * cm)]
    header = ["Repositório", "Total", "Alta", "Média", "Baixa", "Áreas"]
    widths = [5.5*cm, 1.5*cm, 1.5*cm, 1.5*cm, 1.5*cm, 6.5*cm]
    rows = [[_p(f"<b>{h}</b>", "celula_bold") for h in header]]
    for repo, info in sorted(stats["por_repositorio"].items(), key=lambda x: -x[1]["total"]):
        areas = ", ".join(info.get("areas", []))
        rows.append([
            _p(repo, "celula"),
            _p(str(info.get("total", 0)), "celula"),
            _p(str(info.get("Alta", 0)), "celula"),
            _p(str(info.get("Média", 0)), "celula"),
            _p(str(info.get("Baixa", 0)), "celula"),
            _p(areas, "celula"),
        ])
    t = Table(rows, colWidths=widths, repeatRows=1)
    style = [
        ("BACKGROUND",    (0, 0), (-1, 0), AZUL_ESCURO),
        ("TEXTCOLOR",     (0, 0), (-1, 0), BRANCO),
        ("ROWBACKGROUNDS",(0, 1), (-1, -1), [BRANCO, CINZA_LINHA]),
        ("GRID",          (0, 0), (-1, -1), 0.4, CINZA_BORDA),
        ("TOPPADDING",    (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING",   (0, 0), (-1, -1), 5),
        ("VALIGN",        (0, 0), (-1, -1), "TOP"),
    ]
    # colorir coluna Alta
    for i, (_, info) in enumerate(sorted(stats["por_repositorio"].items(), key=lambda x: -x[1]["total"]), 1):
        if info.get("Alta", 0) > 0:
            bg, _ = cor_complexidade("Alta")
            style.append(("BACKGROUND", (2, i), (2, i), bg))
    t.setStyle(TableStyle(style))
    elems.append(t)
    return elems

# ── Matriz de Impacto ────────────────────────────────────────────────────────
def build_matriz(matriz: list) -> list:
    elems = [PageBreak(), _section_title("3. Matriz de Impacto"), Spacer(1, 0.3 * cm)]
    elems.append(_p(
        f"Total de itens: <b>{len(matriz)}</b>. "
        "A tabela abaixo lista todos os impactos identificados pelo scanner.",
        "corpo"
    ))
    elems.append(Spacer(1, 0.2 * cm))

    header = ["ID", "Área", "Repositório", "Componente", "Complexidade", "Prioridade", "Dual?"]
    widths = [1.5*cm, 2.5*cm, 3*cm, 6*cm, 2*cm, 1.8*cm, 1.2*cm]
    rows = [[_p(f"<b>{h}</b>", "celula_bold") for h in header]]

    for item in matriz:
        comp = item.get("complexidade", "")
        prio = item.get("prioridade", "")
        bg_comp, _ = cor_complexidade(comp)
        rows.append([
            _p(item.get("id", ""), "celula"),
            _p(item.get("area", ""), "celula"),
            _p(item.get("repositorio", ""), "celula"),
            _p(item.get("componente", ""), "celula"),
            _p(comp, "celula"),
            _p(prio, "celula"),
            _p("Sim" if item.get("requer_compatibilidade_dual") else "Não", "celula"),
        ])

    t = Table(rows, colWidths=widths, repeatRows=1)
    style = [
        ("BACKGROUND",    (0, 0), (-1, 0), AZUL_ESCURO),
        ("TEXTCOLOR",     (0, 0), (-1, 0), BRANCO),
        ("ROWBACKGROUNDS",(0, 1), (-1, -1), [BRANCO, CINZA_LINHA]),
        ("GRID",          (0, 0), (-1, -1), 0.4, CINZA_BORDA),
        ("TOPPADDING",    (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING",   (0, 0), (-1, -1), 4),
        ("VALIGN",        (0, 0), (-1, -1), "TOP"),
    ]
    for i, item in enumerate(matriz, 1):
        bg, _ = cor_complexidade(item.get("complexidade", ""))
        style.append(("BACKGROUND", (4, i), (4, i), bg))
        bg2, _ = cor_prioridade(item.get("prioridade", ""))
        style.append(("BACKGROUND", (5, i), (5, i), bg2))
    t.setStyle(TableStyle(style))
    elems.append(t)
    return elems

# ── Riscos ───────────────────────────────────────────────────────────────────
def build_riscos(riscos: list) -> list:
    elems = [PageBreak(), _section_title("4. Lista de Riscos"), Spacer(1, 0.3 * cm)]
    header = ["Risco", "Impacto", "Mitigação"]
    widths = [5.5*cm, 5.5*cm, 6*cm]
    rows = [[_p(f"<b>{h}</b>", "celula_bold") for h in header]]
    for r in riscos:
        rows.append([
            _p(r.get("risco", ""), "celula"),
            _p(r.get("impacto", ""), "celula"),
            _p(r.get("mitigacao", ""), "celula"),
        ])
    t = Table(rows, colWidths=widths, repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, 0), AZUL_ESCURO),
        ("TEXTCOLOR",     (0, 0), (-1, 0), BRANCO),
        ("ROWBACKGROUNDS",(0, 1), (-1, -1), [BRANCO, CINZA_LINHA]),
        ("GRID",          (0, 0), (-1, -1), 0.4, CINZA_BORDA),
        ("TOPPADDING",    (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING",   (0, 0), (-1, -1), 6),
        ("VALIGN",        (0, 0), (-1, -1), "TOP"),
    ]))
    elems.append(t)
    return elems

# ── Parceiros Externos ───────────────────────────────────────────────────────
def build_parceiros(parceiros: list) -> list:
    elems = [Spacer(1, 0.5*cm), _section_title("5. Parceiros Externos"), Spacer(1, 0.3*cm)]
    header = ["Parceiro", "Descrição", "Repositórios", "Status"]
    widths = [2.5*cm, 6*cm, 5*cm, 3.5*cm]
    rows = [[_p(f"<b>{h}</b>", "celula_bold") for h in header]]
    for p in parceiros:
        rows.append([
            _p(p.get("parceiro", "").upper(), "celula"),
            _p(p.get("descricao", ""), "celula"),
            _p(", ".join(p.get("repositorios", [])), "celula"),
            _p(p.get("status_alinhamento", ""), "celula"),
        ])
    t = Table(rows, colWidths=widths, repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, 0), AZUL_ESCURO),
        ("TEXTCOLOR",     (0, 0), (-1, 0), BRANCO),
        ("ROWBACKGROUNDS",(0, 1), (-1, -1), [BRANCO, CINZA_LINHA]),
        ("GRID",          (0, 0), (-1, -1), 0.4, CINZA_BORDA),
        ("TOPPADDING",    (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING",   (0, 0), (-1, -1), 6),
        ("VALIGN",        (0, 0), (-1, -1), "TOP"),
    ]))
    elems.append(t)
    return elems

# ── Pendências ───────────────────────────────────────────────────────────────
def build_pendencias(pendencias: list) -> list:
    elems = [PageBreak(), _section_title("6. Pendências Identificadas"), Spacer(1, 0.3*cm)]
    header = ["ID", "Descrição", "Responsável", "Prazo"]
    widths = [1.8*cm, 9*cm, 4.5*cm, 2.7*cm]
    rows = [[_p(f"<b>{h}</b>", "celula_bold") for h in header]]
    for p in pendencias:
        rows.append([
            _p(p.get("id", ""), "celula"),
            _p(p.get("descricao", ""), "celula"),
            _p(p.get("responsavel", ""), "celula"),
            _p(p.get("prazo_estimado", ""), "celula"),
        ])
    t = Table(rows, colWidths=widths, repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, 0), AZUL_ESCURO),
        ("TEXTCOLOR",     (0, 0), (-1, 0), BRANCO),
        ("ROWBACKGROUNDS",(0, 1), (-1, -1), [BRANCO, CINZA_LINHA]),
        ("GRID",          (0, 0), (-1, -1), 0.4, CINZA_BORDA),
        ("TOPPADDING",    (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING",   (0, 0), (-1, -1), 6),
        ("VALIGN",        (0, 0), (-1, -1), "TOP"),
    ]))
    elems.append(t)
    return elems

# ── Pontos Cegos ─────────────────────────────────────────────────────────────
def build_pontos_cegos(pontos: list) -> list:
    elems = [Spacer(1, 0.5*cm), _section_title("7. Pontos Cegos da Análise"), Spacer(1, 0.3*cm)]
    for pc in pontos:
        elems.append(_p(f"<b>{pc.get('id', '')} —</b> {pc.get('descricao', '')}", "corpo"))
        elems.append(_p(f"<i>Recomendação:</i> {pc.get('recomendacao', '')}", "corpo"))
        elems.append(_hr())
    return elems

# ── Critérios de Aceite ──────────────────────────────────────────────────────
def build_criterios() -> list:
    criterios = [
        "Todos os pontos do sistema que manipulam CNPJ foram plenamente identificados.",
        "Todas as estruturas de banco de dados relacionadas ao CNPJ estão devidamente mapeadas.",
        "Todas as APIs expostas e consumidas foram completamente analisadas.",
        "Todas as validações locais e regras de negócio relacionadas ao CNPJ foram documentadas.",
        "Todas as telas e componentes de UI que exibem ou recebem CNPJ foram inventariados.",
        "Todas as integrações internas e externas foram avaliadas e catalogadas.",
        "Todos os riscos e dependências de terceiros foram registrados.",
        "A matriz de impacto está integralmente preenchida e revisada pelo responsável técnico.",
        "O documento de análise está aprovado formalmente pela equipe de engenharia responsável.",
    ]
    elems = [PageBreak(), _section_title("8. Critérios de Aceite"), Spacer(1, 0.3*cm)]
    for c in criterios:
        elems.append(_p(f"☐  {c}", "corpo"))
        elems.append(Spacer(1, 0.15*cm))
    return elems

# ── Resultado Esperado ───────────────────────────────────────────────────────
def build_resultado() -> list:
    perguntas = [
        "Onde o CNPJ é persistido?",
        "Onde ele é validado?",
        "Onde ele é exibido?",
        "Onde ele é enviado ou recebido por integrações?",
        "Quais componentes precisarão ser alterados?",
        "Quais riscos e dependências existem para a futura implementação?",
        "Qual a estimativa de complexidade (Baixa, Média ou Alta) de cada impacto identificado?",
    ]
    elems = [Spacer(1, 0.5*cm), _section_title("9. Resultado Esperado"), Spacer(1, 0.3*cm)]
    elems.append(_p(
        "Ao final do ciclo, a análise consolidada deverá responder com precisão técnica:", "corpo"
    ))
    elems.append(Spacer(1, 0.2*cm))
    for q in perguntas:
        elems.append(_p(f"→  {q}", "corpo"))
    return elems
