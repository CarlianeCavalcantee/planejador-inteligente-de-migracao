"""
Faz upload do PDF e converte para Google Doc editável.
Uso: python spec_gdocs/upload_pdf.py [impacto_cnpj.pdf]
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.oauth2 import service_account

_DIR   = os.path.dirname(os.path.abspath(__file__))
_CREDS = os.path.join(_DIR, "credentials.json")
_ROOT  = os.path.dirname(_DIR)

SCOPES = ["https://www.googleapis.com/auth/drive"]
EMAIL  = "carlianecavalcantebscash@gmail.com"


def main():
    _arg    = sys.argv[1] if len(sys.argv) > 1 else None
    pdf_in  = (os.path.join(os.getcwd(), _arg) if _arg and not os.path.isabs(_arg) else _arg) \
              or os.path.join(_ROOT, "impacto_cnpj.pdf")

    if not os.path.exists(pdf_in):
        raise FileNotFoundError(f"PDF não encontrado: {pdf_in}\nGere primeiro com: python spec_pdf/generate_pdf.py")

    creds = service_account.Credentials.from_service_account_file(_CREDS, scopes=SCOPES)
    drive = build("drive", "v3", credentials=creds)

    print(f"Fazendo upload de: {pdf_in}")

    # upload do PDF convertendo para Google Docs
    meta = {
        "name": "SPEC – Análise de Impacto do CNPJ Alfanumérico",
        "mimeType": "application/vnd.google-apps.document",
    }
    media = MediaFileUpload(pdf_in, mimetype="application/pdf", resumable=True)
    doc = drive.files().create(
        body=meta,
        media_body=media,
        fields="id,name",
    ).execute()

    doc_id = doc["id"]
    print(f"Documento criado: {doc['name']} (id: {doc_id})")

    # compartilha com o e-mail pessoal como editor
    drive.permissions().create(
        fileId=doc_id,
        body={"type": "user", "role": "writer", "emailAddress": EMAIL},
        sendNotificationEmail=False,
    ).execute()

    # compartilha com qualquer pessoa com o link
    drive.permissions().create(
        fileId=doc_id,
        body={"type": "anyone", "role": "writer"},
    ).execute()

    print(f"\nPronto! Abra e edite em:")
    print(f"  https://docs.google.com/document/d/{doc_id}/edit")


if __name__ == "__main__":
    main()
