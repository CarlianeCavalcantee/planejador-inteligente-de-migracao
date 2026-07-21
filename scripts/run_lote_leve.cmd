@echo off
REM Lote LEVE — todos os repos exceto os pesados, token(s) padrão do .env
python scanner.py --exclude-repos-file docs/analises/repos_pesados.txt
