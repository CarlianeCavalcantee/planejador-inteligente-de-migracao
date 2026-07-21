from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.units import cm

# ── Paleta ──────────────────────────────────────────────────────────────────
AZUL_ESCURO  = colors.HexColor("#1B3A6B")
AZUL_MEDIO   = colors.HexColor("#2563EB")
AZUL_CLARO   = colors.HexColor("#DBEAFE")
CINZA_LINHA  = colors.HexColor("#F1F5F9")
CINZA_BORDA  = colors.HexColor("#CBD5E1")
BRANCO       = colors.white
PRETO        = colors.HexColor("#1E293B")

ALTA_COR     = colors.HexColor("#FEE2E2")
ALTA_TEXTO   = colors.HexColor("#991B1B")
MEDIA_COR    = colors.HexColor("#FEF9C3")
MEDIA_TEXTO  = colors.HexColor("#854D0E")
BAIXA_COR    = colors.HexColor("#DCFCE7")
BAIXA_TEXTO  = colors.HexColor("#166534")

# ── Estilos de parágrafo ─────────────────────────────────────────────────────
def build_styles():
    base = getSampleStyleSheet()

    titulo_doc = ParagraphStyle(
        "TituloDoc",
        parent=base["Title"],
        fontSize=22,
        textColor=BRANCO,
        alignment=TA_CENTER,
        spaceAfter=4,
        fontName="Helvetica-Bold",
    )
    subtitulo_doc = ParagraphStyle(
        "SubtituloDoc",
        parent=base["Normal"],
        fontSize=11,
        textColor=AZUL_CLARO,
        alignment=TA_CENTER,
        spaceAfter=2,
        fontName="Helvetica",
    )
    secao = ParagraphStyle(
        "Secao",
        parent=base["Heading1"],
        fontSize=13,
        textColor=BRANCO,
        fontName="Helvetica-Bold",
        spaceBefore=14,
        spaceAfter=6,
        leftIndent=0,
    )
    subsecao = ParagraphStyle(
        "Subsecao",
        parent=base["Heading2"],
        fontSize=10,
        textColor=AZUL_ESCURO,
        fontName="Helvetica-Bold",
        spaceBefore=8,
        spaceAfter=4,
    )
    corpo = ParagraphStyle(
        "Corpo",
        parent=base["Normal"],
        fontSize=8.5,
        textColor=PRETO,
        fontName="Helvetica",
        spaceAfter=3,
        leading=13,
    )
    celula = ParagraphStyle(
        "Celula",
        parent=base["Normal"],
        fontSize=7.5,
        textColor=PRETO,
        fontName="Helvetica",
        leading=11,
        wordWrap="CJK",
    )
    celula_bold = ParagraphStyle(
        "CelulaBold",
        parent=celula,
        fontName="Helvetica-Bold",
    )
    rodape = ParagraphStyle(
        "Rodape",
        parent=base["Normal"],
        fontSize=7,
        textColor=colors.HexColor("#94A3B8"),
        alignment=TA_CENTER,
        fontName="Helvetica",
    )

    return {
        "titulo_doc": titulo_doc,
        "subtitulo_doc": subtitulo_doc,
        "secao": secao,
        "subsecao": subsecao,
        "corpo": corpo,
        "celula": celula,
        "celula_bold": celula_bold,
        "rodape": rodape,
    }

# ── Helpers de cor por complexidade ─────────────────────────────────────────
def cor_complexidade(valor: str):
    v = valor.upper()
    if v == "ALTA":
        return ALTA_COR, ALTA_TEXTO
    if v == "MÉDIA" or v == "MEDIA":
        return MEDIA_COR, MEDIA_TEXTO
    return BAIXA_COR, BAIXA_TEXTO

def cor_prioridade(valor: str):
    v = (valor or "").upper()
    if v == "P1":
        return ALTA_COR, ALTA_TEXTO
    if v == "P2":
        return MEDIA_COR, MEDIA_TEXTO
    return BAIXA_COR, BAIXA_TEXTO
