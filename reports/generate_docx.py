"""
Ponto de entrada retrocompatível.
Uso: python reports/generate_docx.py [impacto_cnpj.json] [saida.docx]
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from reports.docx_builder.document_builder import main

if __name__ == "__main__":
    main()
