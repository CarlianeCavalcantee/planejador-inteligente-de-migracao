import os, json
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = [
    "https://www.googleapis.com/auth/documents",
    "https://www.googleapis.com/auth/drive.file",
]

_DIR   = os.path.dirname(os.path.abspath(__file__))
_CREDS = os.path.join(_DIR, "credentials.json")
_TOKEN = os.path.join(_DIR, "token.json")


def get_credentials():
    if not os.path.exists(_CREDS):
        raise FileNotFoundError(f"\nArquivo não encontrado: {_CREDS}\nSiga o SETUP.md.")

    # verifica se é service account — não serve para este fluxo
    with open(_CREDS) as f:
        info = json.load(f)
    if info.get("type") == "service_account":
        raise ValueError(
            "\nO credentials.json é de uma Service Account.\n"
            "Crie um OAuth 2.0 Client ID (tipo: Aplicativo para computador) e baixe o JSON.\n"
            "Veja o SETUP.md para instruções."
        )

    creds = Credentials.from_authorized_user_file(_TOKEN, SCOPES) if os.path.exists(_TOKEN) else None
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(_CREDS, SCOPES)
            # tenta abrir browser; se falhar, mostra URL para copiar manualmente
            try:
                creds = flow.run_local_server(port=0, open_browser=True)
            except Exception:
                creds = flow.run_local_server(port=0, open_browser=False)
        open(_TOKEN, "w").write(creds.to_json())
    return creds
