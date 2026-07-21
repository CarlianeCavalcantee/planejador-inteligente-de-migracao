@echo off
REM Lote PESADO — repos >1000KB, use tokens com cota cheia
REM Preencha os tokens antes de rodar

set GITHUB_TOKEN=ghp_token_principal
set GITHUB_TOKEN_2=ghp_token_extra

python scanner.py --repos-file docs/analises/repos_pesados.txt --concurrency 2
