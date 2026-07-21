@echo off
set ADO_ORG=https://dev.azure.com/bscash
set ADO_PROJECT=Novos Produtos e Melhorias
set ADO_PAT=<seu_ado_pat>
set ADO_EPIC_ID=13049

python reports/azuredevops_export.py --create-skip
