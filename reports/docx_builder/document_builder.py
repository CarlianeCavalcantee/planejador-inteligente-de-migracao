"""
Orquestrador do gerador de DOCX corporativo.
Uso: python -m reports.docx_builder.document_builder [impacto_cnpj.json] [saida.docx]
     ou via generate_docx.py (compatibilidade retroativa)
"""
import sys, os, json
from docx import Document

from .styles import set_margins
from .sections import (
    capa, resumo, dashboard, arquitetura, estrategia,
    impactos, repositorios, riscos, rollback, cronograma,
    parceiros, testes, conclusao,
)


class DocumentBuilder:
    def __init__(self, data: dict):
        self.data = data
        self.doc = Document()
        set_margins(self.doc)

    def build(self) -> Document:
        d, doc = self.data, self.doc

        capa.build(doc, d)
        resumo.build(doc, d, num=1)
        dashboard.build(doc, d, num=2)
        arquitetura.build_atual(doc, d, num=3)
        arquitetura.build_proposta(doc, d, num=4)
        estrategia.build_camadas(doc, d, num=5)
        estrategia.build_estrategia(doc, d, num=6)
        impactos.build_all_areas(doc, d, start_num=7)
        repositorios.build(doc, d, num=8)
        cronograma.build(doc, d, num=9)
        cronograma._build_trilhas_section(doc, d, num=10)
        parceiros.build(doc, d, num=11)
        testes.build_testes(doc, d, num=12)
        testes.build_criterios(doc, d, num=13)
        riscos.build(doc, d, num=14)
        rollback.build(doc, d, num=15)
        conclusao.build_pendencias(doc, d, num=16)
        conclusao.build_conclusao(doc, d, num=17)

        return doc

    def save(self, path: str):
        self.build().save(path)
        print(f"DOCX gerado: {path}")


def _resolve_paths(arg1: str | None, arg2: str | None) -> tuple[str, str]:
    """Resolve json_in e docx_out: se arg1 for um JSON existente usa ele,
    caso contrário tenta inferir o .docx a partir do nome do JSON."""
    cwd = os.getcwd()

    if arg1 and not os.path.isabs(arg1):
        arg1 = os.path.join(cwd, arg1)

    _default = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "docs", "output", "impacto_cnpj.json",
    )
    json_in = arg1 or _default

    if arg2:
        docx_out = os.path.join(cwd, arg2) if not os.path.isabs(arg2) else arg2
    else:
        # Deriva o .docx do mesmo prefixo do JSON
        # scan_backoffice.json  →  scan_backoffice.docx
        # impacto_cnpj.json     →  impacto_cnpj.docx
        docx_out = os.path.splitext(json_in)[0] + ".docx"

    return json_in, docx_out


def main():
    arg1 = sys.argv[1] if len(sys.argv) > 1 else None
    arg2 = sys.argv[2] if len(sys.argv) > 2 else None

    json_in, docx_out = _resolve_paths(arg1, arg2)

    data = {}
    if os.path.exists(json_in):
        with open(json_in, encoding="utf-8") as f:
            data = json.load(f)
    else:
        print(f"Aviso: {json_in} não encontrado. Gerando documento com dados vazios.")

    DocumentBuilder(data).save(docx_out)


if __name__ == "__main__":
    main()
