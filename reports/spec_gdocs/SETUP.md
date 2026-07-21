# SETUP – Service Account (sem OAuth, sem tela de consentimento)

## 1. Acesse o projeto no Google Cloud Console
https://console.cloud.google.com/

## 2. Ative as APIs
APIs e Serviços → Biblioteca → ative:
- Google Docs API
- Google Drive API

## 3. Crie a Service Account
1. APIs e Serviços → Credenciais → "+ Criar Credenciais" → "Conta de serviço"
2. Nome: `scanner-cnpj`
3. Clique em "Criar e continuar" → "Concluído"

## 4. Baixe a chave JSON
1. Na lista de credenciais, clique na service account criada
2. Aba "Chaves" → "Adicionar chave" → "Criar nova chave" → JSON
3. Salve como `credentials.json` em:
   `c:\dev\scanner\spec_gdocs\credentials.json`

## 5. Rode
```bash
python spec_gdocs/generate_gdoc.py
```

O script vai criar o documento e imprimir o link.
O doc será criado no Drive da service account — o link gerado
já estará com permissão de edição para qualquer pessoa com o link.
