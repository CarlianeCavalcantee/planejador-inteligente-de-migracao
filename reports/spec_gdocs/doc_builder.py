"""
Constrói os batchUpdate requests para a Google Docs API.
Cada função retorna uma lista de requests e avança o índice de inserção.
"""

# ── helpers de request ───────────────────────────────────────────────────────

def _insert(text: str, index: int) -> dict:
    return {"insertText": {"location": {"index": index}, "text": text}}


def _style_range(start: int, end: int, style: dict) -> dict:
    return {
        "updateTextStyle": {
            "range": {"startIndex": start, "endIndex": end},
            "textStyle": style,
            "fields": ",".join(style.keys()),
        }
    }


def _paragraph_style(start: int, end: int, named_style: str, alignment: str = "START") -> dict:
    return {
        "updateParagraphStyle": {
            "range": {"startIndex": start, "endIndex": end},
            "paragraphStyle": {
                "namedStyleType": named_style,
                "alignment": alignment,
            },
            "fields": "namedStyleType,alignment",
        }
    }


def _bg_color(start: int, end: int, r: float, g: float, b: float) -> dict:
    return _style_range(start, end, {
        "backgroundColor": {"color": {"rgbColor": {"red": r, "green": g, "blue": b}}}
    })


def _bold(start: int, end: int, bold: bool = True) -> dict:
    return _style_range(start, end, {"bold": bold})


def _font_size(start: int, end: int, pt: float) -> dict:
    return _style_range(start, end, {"fontSize": {"magnitude": pt, "unit": "PT"}})


def _fg_color(start: int, end: int, r: float, g: float, b: float) -> dict:
    return _style_range(start, end, {
        "foregroundColor": {"color": {"rgbColor": {"red": r, "green": g, "blue": b}}}
    })


# ── cores ────────────────────────────────────────────────────────────────────
AZUL  = (0.106, 0.227, 0.420)   # #1B3A6B
BRANCO = (1, 1, 1)
CINZA  = (0.945, 0.961, 0.976)  # #F1F5F9

def _complexidade_cor(val: str):
    v = val.upper()
    if v == "ALTA":   return (0.996, 0.886, 0.886)
    if v in ("MÉDIA", "MEDIA"): return (0.996, 0.976, 0.765)
    return (0.863, 0.988, 0.894)


# ── bloco de título de seção ─────────────────────────────────────────────────
def section_title(requests: list, idx: int, text: str) -> int:
    t = f"\n{text}\n"
    requests.append(_insert(t, idx))
    start = idx + 1
    end   = start + len(text)
    requests.append(_paragraph_style(start, end + 1, "HEADING_1"))
    requests.append(_bold(start, end))
    requests.append(_fg_color(start, end, *AZUL))
    requests.append(_font_size(start, end, 14))
    return idx + len(t)


# ── parágrafo simples ────────────────────────────────────────────────────────
def paragraph(requests: list, idx: int, text: str, bold: bool = False, size: float = 10) -> int:
    t = text + "\n"
    requests.append(_insert(t, idx))
    end = idx + len(t)
    requests.append(_font_size(idx, end, size))
    if bold:
        requests.append(_bold(idx, end))
    return end


# ── tabela genérica ──────────────────────────────────────────────────────────
def insert_table(service, doc_id: str, rows: int, cols: int, index: int):
    """Insere uma tabela vazia via API e retorna o doc atualizado."""
    service.documents().batchUpdate(
        documentId=doc_id,
        body={"requests": [{
            "insertTable": {
                "rows": rows,
                "columns": cols,
                "location": {"index": index},
            }
        }]}
    ).execute()


def fill_table_cell(requests: list, table_start_index: int,
                    row: int, col: int, text: str,
                    bold: bool = False, bg: tuple = None):
    """
    Calcula o índice da célula e insere texto + estilos.
    ATENÇÃO: funciona para tabelas simples onde todas as células têm 1 parágrafo.
    O índice real é obtido do doc após inserção — use get_table_cell_index().
    """
    pass  # preenchido via get_doc_and_fill abaixo


# ── capa ─────────────────────────────────────────────────────────────────────
def build_capa(requests: list, idx: int, meta: dict) -> int:
    t = "SPEC – Análise de Impacto do CNPJ Alfanumérico\n"
    requests.append(_insert(t, idx))
    end = idx + len(t)
    requests.append(_paragraph_style(idx, end, "TITLE", "CENTER"))
    requests.append(_bold(idx, end))
    requests.append(_fg_color(idx, end, *AZUL))
    requests.append(_font_size(idx, end, 22))
    idx = end

    sub = f"Sistema: {meta['sistema']}  |  Versão: {meta['versao']}  |  Data: {meta['data_execucao']}\n"
    requests.append(_insert(sub, idx))
    end = idx + len(sub)
    requests.append(_paragraph_style(idx, end, "SUBTITLE", "CENTER"))
    requests.append(_fg_color(idx, end, 0.4, 0.4, 0.4))
    requests.append(_font_size(idx, end, 11))
    return end


# ── sumário executivo (texto) ────────────────────────────────────────────────
def build_sumario_text(requests: list, idx: int, stats: dict) -> int:
    idx = section_title(requests, idx, "1. Sumário Executivo")

    lines = [
        ("Repositórios Analisados",  str(stats["total_repos"])),
        ("Com Impacto",              str(stats["repos_com_impacto"])),
        ("Sem Impacto",              str(stats["repos_sem_impacto"])),
        ("Total de Impactos",        str(stats["total_impactos"])),
        ("Arquivos Críticos",        str(stats["arquivos_criticos"])),
        ("Requerem Compatibilidade Dual", str(stats["requerem_dual"])),
        ("Chamadores Críticos Total", f"{stats['chamadores_criticos']:,}"),
    ]
    for label, val in lines:
        idx = paragraph(requests, idx, f"  {label}: {val}", size=10)

    idx = section_title(requests, idx, "Impactos por Área")
    for area, qtd in sorted(stats["por_area"].items(), key=lambda x: -x[1]):
        idx = paragraph(requests, idx, f"  {area}: {qtd}", size=10)

    idx = section_title(requests, idx, "Impactos por Complexidade")
    for comp, qtd in stats["por_complexidade"].items():
        idx = paragraph(requests, idx, f"  {comp}: {qtd}", size=10)

    idx = section_title(requests, idx, "Progresso")
    for k, v in stats["progresso"].items():
        idx = paragraph(requests, idx, f"  {k.replace('_',' ').title()}: {v}", size=10)

    return idx


# ── impactos por repositório (texto) ─────────────────────────────────────────
def build_repos_text(requests: list, idx: int, stats: dict) -> int:
    idx = section_title(requests, idx, "2. Impactos por Repositório")
    for repo, info in sorted(stats["por_repositorio"].items(), key=lambda x: -x[1]["total"]):
        areas = ", ".join(info.get("areas", []))
        line  = f"  {repo}  —  Total: {info['total']}  |  Alta: {info.get('Alta',0)}  |  Média: {info.get('Média',0)}  |  Baixa: {info.get('Baixa',0)}  |  Áreas: {areas}"
        idx   = paragraph(requests, idx, line, size=9)
    return idx


# ── matriz de impacto (texto) ────────────────────────────────────────────────
def build_matriz_text(requests: list, idx: int, matriz: list) -> int:
    idx = section_title(requests, idx, "3. Matriz de Impacto")
    idx = paragraph(requests, idx, f"Total de itens: {len(matriz)}", bold=True, size=10)

    for item in matriz:
        header = f"[{item.get('id','')}] {item.get('area','')} — {item.get('repositorio','')} — {item.get('complexidade','')} / {item.get('prioridade','')}"
        idx = paragraph(requests, idx, header, bold=True, size=9)
        idx = paragraph(requests, idx, f"  Componente: {item.get('componente','')}", size=8)
        idx = paragraph(requests, idx, f"  Impacto: {item.get('descricao_impacto','')}", size=8)
        if item.get("requer_compatibilidade_dual"):
            idx = paragraph(requests, idx, f"  Dual-mode: {item.get('motivo_compatibilidade_dual','')}", size=8)
        ev = item.get("evidencia", {})
        if ev.get("arquivo"):
            idx = paragraph(requests, idx, f"  Evidência: {ev['arquivo']} : L{ev.get('linha','')}", size=8)
    return idx


# ── riscos ───────────────────────────────────────────────────────────────────
def build_riscos_text(requests: list, idx: int, riscos: list) -> int:
    idx = section_title(requests, idx, "4. Lista de Riscos")
    for r in riscos:
        idx = paragraph(requests, idx, f"Risco: {r.get('risco','')}", bold=True, size=9)
        idx = paragraph(requests, idx, f"  Impacto: {r.get('impacto','')}", size=9)
        idx = paragraph(requests, idx, f"  Mitigação: {r.get('mitigacao','')}", size=9)
    return idx


# ── parceiros ────────────────────────────────────────────────────────────────
def build_parceiros_text(requests: list, idx: int, parceiros: list) -> int:
    idx = section_title(requests, idx, "5. Parceiros Externos")
    for p in parceiros:
        repos = ", ".join(p.get("repositorios", []))
        idx = paragraph(requests, idx, f"{p.get('parceiro','').upper()} — {p.get('descricao','')}", bold=True, size=9)
        idx = paragraph(requests, idx, f"  Repositórios: {repos}  |  Status: {p.get('status_alinhamento','')}", size=9)
    return idx


# ── pendências ───────────────────────────────────────────────────────────────
def build_pendencias_text(requests: list, idx: int, pendencias: list) -> int:
    idx = section_title(requests, idx, "6. Pendências Identificadas")
    for p in pendencias:
        idx = paragraph(requests, idx, f"{p.get('id','')} — {p.get('descricao','')}", bold=True, size=9)
        idx = paragraph(requests, idx, f"  Responsável: {p.get('responsavel','')}  |  Prazo: {p.get('prazo_estimado','')}", size=9)
    return idx


# ── pontos cegos ─────────────────────────────────────────────────────────────
def build_pontos_cegos_text(requests: list, idx: int, pontos: list) -> int:
    idx = section_title(requests, idx, "7. Pontos Cegos da Análise")
    for pc in pontos:
        idx = paragraph(requests, idx, f"{pc.get('id','')} — {pc.get('descricao','')}", bold=True, size=9)
        idx = paragraph(requests, idx, f"  Recomendação: {pc.get('recomendacao','')}", size=9)
    return idx


# ── critérios de aceite ───────────────────────────────────────────────────────
def build_criterios_text(requests: list, idx: int) -> int:
    idx = section_title(requests, idx, "8. Critérios de Aceite")
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
    for c in criterios:
        idx = paragraph(requests, idx, f"☐  {c}", size=10)
    return idx


# ── resultado esperado ────────────────────────────────────────────────────────
def build_resultado_text(requests: list, idx: int) -> int:
    idx = section_title(requests, idx, "9. Resultado Esperado")
    perguntas = [
        "Onde o CNPJ é persistido?",
        "Onde ele é validado?",
        "Onde ele é exibido?",
        "Onde ele é enviado ou recebido por integrações?",
        "Quais componentes precisarão ser alterados?",
        "Quais riscos e dependências existem para a futura implementação?",
        "Qual a estimativa de complexidade (Baixa, Média ou Alta) de cada impacto identificado?",
    ]
    for q in perguntas:
        idx = paragraph(requests, idx, f"→  {q}", size=10)
    return idx
