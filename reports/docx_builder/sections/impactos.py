"""Seção genérica de impactos por área — reutilizada por banco, api, frontend, etc."""
from ..styles import heading, para, table, PRETO, LARANJA, comp_color, COR_ALTA, page_break
from ..helpers import group_impacts, impacts_by_area

_HEADERS = ["REPOSITÓRIO", "COMPONENTE / ARQUIVO", "OCORR.", "LINHAS", "REGRA", "COMPLEXIDADE", "DESCRIÇÃO TÉCNICA"]
_WIDTHS   = [3.2, 3.5, 1.2, 1.5, 1.8, 2.3, 4.5]


def _impact_rows(grouped):
    rows = []
    for g in grouped:
        comp = g["componente"]
        # Abreviar componente longo
        if len(comp) > 55:
            parts = comp.split("/")
            comp = "/".join(parts[-2:]) if len(parts) >= 2 else comp[-55:]
        desc = g["descricao"]
        if len(desc) > 220:
            desc = desc[:217] + "…"
        rows.append([
            g["repositorio"],
            comp,
            str(g["ocorrencias"]),
            g["linhas"],
            g["regra"],
            (g["complexidade"], comp_color(g["complexidade"])),
            desc,
        ])
    return rows


def build_area_section(doc, area_name, impacts, num_section, sub_num=None):
    """Gera uma seção completa para uma área específica."""
    num_label = f"{num_section}.{sub_num}" if sub_num else str(num_section)
    level = 2 if sub_num else 1

    heading(doc, area_name, level=level, numbered=num_label)

    if not impacts:
        para(doc, f"Nenhum impacto de {area_name} identificado.", italic=True)
        return

    total = len(impacts)
    alta  = sum(1 for i in impacts if "Alta" in i.get("complexidade", ""))
    media = sum(1 for i in impacts if "Média" in i.get("complexidade", "") or "Media" in i.get("complexidade", ""))
    dual  = sum(1 for i in impacts if i.get("requer_compatibilidade_dual"))

    para(doc,
         f"Total: {total} impactos  |  Alta: {alta}  |  Média: {media}  |  "
         f"Requerem compatibilidade dual: {dual}",
         italic=True, size=9.5, color=LARANJA)

    grouped = group_impacts(impacts, max_rows=60)
    rows = _impact_rows(grouped)
    table(doc, _HEADERS, rows, col_widths=_WIDTHS, font_size=8)


def build_all_areas(doc, data, start_num=7):
    """Gera seção principal de impactos com subseções por área."""
    heading(doc, "Análise de Impacto por Área", level=1, numbered=start_num)

    matriz = data.get("matriz_impacto", [])
    by_area = impacts_by_area(matriz)

    # Ordem de apresentação
    order = [
        "Segurança/LGPD",
        "Banco de Dados",
        "API/Contrato",
        "Integrações",
        "Backend",
        "Processamento/Batch",
        "Frontend",
        "Pessoa Jurídica/PJ",
        "Testes/Qualidade",
        "Documentação",
        "Configuração",
        "Infraestrutura/CI",
    ]
    # Adicionar áreas não previstas na ordem
    for a in by_area:
        if a not in order:
            order.append(a)

    sub = 1
    for area in order:
        impacts = by_area.get(area, [])
        if not impacts:
            continue
        build_area_section(doc, area, impacts, start_num, sub_num=sub)
        sub += 1

    page_break(doc)
