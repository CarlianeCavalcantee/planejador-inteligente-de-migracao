"""
Gerador principal do PDF – SPEC Análise de Impacto CNPJ Alfanumérico
Uso: python generate_pdf.py [caminho_json] [caminho_saida_pdf]
"""
import sys
import os

# garante que os módulos locais sejam encontrados
sys.path.insert(0, os.path.dirname(__file__))

from reportlab.platypus import SimpleDocTemplate, Spacer
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.lib import colors

import data_loader as dl
import sections as sec
from styles import AZUL_ESCURO, CINZA_BORDA, build_styles

S = build_styles()

# ── Cabeçalho / Rodapé ───────────────────────────────────────────────────────
def _on_page(canvas, doc, meta):
    from reportlab.platypus import Paragraph
    canvas.saveState()
    w, h = A4

    # cabeçalho
    canvas.setFillColor(AZUL_ESCURO)
    canvas.rect(0, h - 1.1*cm, w, 1.1*cm, fill=1, stroke=0)
    canvas.setFillColor(colors.white)
    canvas.setFont("Helvetica-Bold", 8)
    canvas.drawString(1*cm, h - 0.75*cm, f"SPEC – Impacto CNPJ Alfanumérico  |  {meta['sistema']}")
    canvas.setFont("Helvetica", 8)
    canvas.drawRightString(w - 1*cm, h - 0.75*cm, f"Versão {meta['versao']}  |  {meta['data_execucao']}")

    # rodapé
    canvas.setStrokeColor(CINZA_BORDA)
    canvas.setLineWidth(0.5)
    canvas.line(1*cm, 0.9*cm, w - 1*cm, 0.9*cm)
    canvas.setFillColor(colors.HexColor("#94A3B8"))
    canvas.setFont("Helvetica", 7)
    canvas.drawCentredString(w / 2, 0.5*cm, f"Página {doc.page}  —  Documento gerado automaticamente pelo scanner BScash")

    canvas.restoreState()


def generate(json_path: str, output_path: str):
    data = dl.load(json_path)
    meta = dl.get_meta(data)
    stats = dl.get_stats(data)
    matriz = dl.get_matriz(data)
    riscos = dl.get_riscos(data)
    parceiros = dl.get_parceiros(data)
    pendencias = dl.get_pendencias(data)
    pontos = dl.get_pontos_cegos(data)

    doc = SimpleDocTemplate(
        output_path,
        pagesize=A4,
        leftMargin=1.5*cm,
        rightMargin=1.5*cm,
        topMargin=1.8*cm,
        bottomMargin=1.5*cm,
        title=f"SPEC – Impacto CNPJ Alfanumérico – {meta['sistema']}",
        author="Scanner BScash",
    )

    story = []
    story += sec.build_capa(meta)
    story += sec.build_sumario(stats)
    story += sec.build_por_repositorio(stats)
    story += sec.build_matriz(matriz)
    story += sec.build_riscos(riscos)
    story += sec.build_parceiros(parceiros)
    story += sec.build_pendencias(pendencias)
    story += sec.build_pontos_cegos(pontos)
    story += sec.build_criterios()
    story += sec.build_resultado()

    doc.build(
        story,
        onFirstPage=lambda c, d: _on_page(c, d, meta),
        onLaterPages=lambda c, d: _on_page(c, d, meta),
    )
    print(f"PDF gerado: {output_path}")


if __name__ == "__main__":
    _root   = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    _default_json = os.path.join(_root, "docs", "output", "impacto_cnpj.json")
    _default_pdf  = os.path.join(_root, "docs", "output", "impacto_cnpj.pdf")
    _cwd    = os.getcwd()
    def _resolve(arg, default):
        if arg:
            return arg if os.path.isabs(arg) else os.path.join(_cwd, arg)
        return default
    json_in = _resolve(sys.argv[1] if len(sys.argv) > 1 else None, _default_json)
    pdf_out = _resolve(sys.argv[2] if len(sys.argv) > 2 else None, _default_pdf)
    generate(json_in, pdf_out)
