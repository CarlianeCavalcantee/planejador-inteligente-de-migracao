# CNPJ Impact Scanner

Ferramenta de análise estática que varre repositórios GitHub de uma organização em busca de código impactado pela mudança do CNPJ para o formato alfanumérico (Receita Federal). Gera relatórios em JSON e Markdown com matriz de impacto, ordem de migração, checklist de rollback e mapeamento de parceiros externos.

## Pré-requisitos

- Python 3.11+
- GitHub Personal Access Token com permissão `repo` (leitura)

## Instalação

```bash
pip install -r requirements.txt
```

```bash
# Linux/macOS
cp .env.example .env

# Windows
copy .env.example .env
```

```bash
# edite .env e preencha GITHUB_TOKEN
```

## Uso

```bash
# Scan completo da org configurada
python scanner.py

# Repos específicos — gera arquivos com nome derivado do(s) repo(s)
python scanner.py -r repo1 repo2 repo3
# saída: scan_repo1_repo2_+1.json / .md / .docx

# Repo único
python scanner.py -r backoffice
# saída: scan_backoffice.json / .md / .docx

# Lista de repos a partir de arquivo (um por linha)
python scanner.py --repos-file repos.txt

# Excluir repos a partir de arquivo
python scanner.py --exclude-repos-file ignore.txt

# Sobrescrever org
python scanner.py -o minha-org

# Usar config alternativa
python scanner.py -c outro-config.json

# Apenas JSON ou apenas Markdown
python scanner.py --json-only
python scanner.py --md-only

# Retomar execução interrompida
python scanner.py --resume

# Limpar cache e reiniciar
python scanner.py --clear-cache

# Incluir busca por aliases de campo (taxId, cpfCnpj, etc.) em todos os repos
python scanner.py --scan-aliases

# Auditar aliases em repos sem impacto (usa Search API — mais lento)
python scanner.py --audit-aliases

# Baixar arquivos > 500KB via Blob API
python scanner.py --include-large-files

# Repos processados em paralelo (padrão: 2; recomendado 8+ com --local)
python scanner.py --concurrency 8

# Usar repos clonados localmente em vez da GitHub API
python scanner.py --local /caminho/para/repos

# Desativar TUI e usar saída de texto simples
python scanner.py --no-ui

# Nível de log
python scanner.py --log-level DEBUG
```

## Configuração (`scanner-config.json`)

| Campo | Descrição |
|-------|-----------|
| `github_org` | Organização GitHub a escanear |
| `repositorios` | Lista de repos específicos (vazio = todos da org) |
| `ignore_paths` | Caminhos/extensões ignorados (node_modules, dist, etc.) |
| `prioridade_area` | Ordem de prioridade das áreas para deduplicação e migração |
| `regras` | Lista de regras com padrões regex por área e extensão de arquivo |
| `output_file` | Caminho do JSON de saída (padrão: `impacto_cnpj.json`) |
| `output_markdown` | Caminho do Markdown de saída (padrão: `impacto_cnpj.md`) |

## Áreas cobertas pelas regras

| ID | Área | Exemplos detectados |
|----|------|---------------------|
| SEC-001 | Segurança/LGPD | CNPJ real hardcoded no código |
| CFG-001 | Configuração | `application.yml`, `.env` com CNPJ fixo |
| INFRA-001 | Infraestrutura/CI | Dockerfile, Jenkinsfile com CNPJ em variável |
| JPA-001 | Banco de Dados | `@Column(length=14)` em entidades JPA |
| DB-001 | Banco de Dados | `VARCHAR(14)`, `NUMBER(14)`, índices e constraints |
| MIGRATION-001 | Banco de Dados | Scripts Flyway/Liquibase com tipo incompatível |
| API-001 | API/Contrato | OpenAPI/Swagger/Protobuf com pattern numérico |
| INT-001 | Integrações | Kafka, SQS, SOAP, REST clients com CNPJ |
| XSD-001 | Integrações | Schemas XSD/WSDL com pattern numérico |
| BE-001 | Backend | Validadores, formatadores, regex `\d{14}` |
| STR-001 | Backend | `substring(0,8)`, `slice`, índice posicional |
| BATCH-001 | Processamento/Batch | Jobs, ETL, SPED, NFS-e |
| JASPER-001 | Processamento/Batch | Templates `.jrxml` com máscara numérica |
| TEMPLATE-001 | Processamento/Batch | Templates Freemarker/Velocity |
| TEST-001 | Testes/Qualidade | Fixtures, mocks, seeds com CNPJ hardcoded |
| FE-001 | Frontend | Máscaras, validações, `inputMode="numeric"` |
| DOC-001 | Documentação | README/docs com CNPJ exclusivamente numérico |

## Saídas geradas

| Arquivo | Conteúdo |
|---------|----------|
| `impacto_cnpj.json` | Relatório completo com matriz de impacto, estatísticas, ordem de migração por módulo, checklist de rollback, riscos, parceiros externos e telas para QA |
| `impacto_cnpj.md` | Versão Markdown do relatório para visualização no GitHub/Confluence |
| `impacto_cnpj.html` | Dashboard HTML interativo com gráficos, filtros e navegação por repositório |
| `impacto_cnpj.pdf` | Relatório em PDF formatado (ReportLab) |
| `impacto_cnpj.docx` | Documento Word com todas as seções da SPEC |
| `ado_workitems.csv` | Hierarquia Feature (fluxo) > PBI ([Fluxo] repo) > Task para importação no Azure DevOps |

> Cada JSON gerado inclui os campos `scan_id` (ex: `20250115_143022`) e `data_execucao` (ISO 8601 com fuso horário BRT) para identificação e comparação entre execuções.

## Exportações e relatórios adicionais

### Dashboard HTML

```bash
# A partir do JSON padrão
python reports/dashboard.py

# A partir de um JSON específico (ex: scan de repo único)
python reports/dashboard.py scan_backoffice.json
```

Gera `impacto_cnpj.html` (ou `scan_backoffice.html`) com:
- KPIs, gráficos de área/complexidade/repositório
- Tabela de impactos por repositório com filtros por área, complexidade e busca livre
- Arquivos críticos, ordem de migração, parceiros externos e pontos cegos
- `scan_id` e data de geração exibidos na topbar para rastreabilidade

### PDF

```bash
# A partir do JSON padrão
python spec_pdf/generate_pdf.py

# Especificando JSON e arquivo de saída
python spec_pdf/generate_pdf.py scan_backoffice.json scan_backoffice.pdf
```

Requer `reportlab`. Gera relatório paginado com cabeçalho/rodapé, capa, sumário, matriz, riscos, parceiros e critérios de aceite.

### Word (.docx)

```bash
# A partir do JSON padrão → impacto_cnpj.docx
python reports/generate_docx.py

# A partir de um JSON específico → mesmo nome com extensão .docx
python reports/generate_docx.py scan_backoffice.json

# Especificando JSON e arquivo de saída
python reports/generate_docx.py scan_backoffice.json relatorio_backoffice.docx
```

Requer `python-docx`. Gera a SPEC completa em formato Word com tabelas coloridas por complexidade. O `scan_id` aparece na capa do documento.

### Azure DevOps

Cria work items na hierarquia **Épico → Feature (fluxo de negócio) → PBI ([Fluxo] repo) → Task**.

```
Épico
└── Migração CNPJ Alfanumérico

    Feature
    ├── PIX
    ├── Conta Digital
    └── ...

        PBI
        ├── [PIX] pix-api
        ├── [PIX] pix-mobile
        └── [Conta Digital] pix-api   ← mesmo repo, escopo diferente

            Tasks (impactos detectados)
            ├── [IMP-0001] PixRequest.java:42 — Backend Alta
            ├── [IMP-0002] PixKey.java:18 — Banco de Dados Alta
            └── ...

            Tasks fixas de encerramento (geradas automaticamente)
            ├── Code Review — Revisão técnica e aprovação Tech Lead
            ├── Testes — Unitários, Integração e Regressão
            ├── Deploy — DEV / QA / HML
            ├── Homologação — Validar migração do repositório
            └── Validação Scanner — Executar scanner e confirmar ausência de ocorrências
```

> Um repositório que participa de múltiplos fluxos gera um PBI por fluxo (`[PIX] pix-api`, `[Conta Digital] pix-api`), cada um com o escopo específico daquele fluxo. Links de dependência entre PBIs são criados automaticamente com base na ordem de migração inferida pelo scanner.

```bash
# Dry-run (visualiza sem criar)
python reports/azuredevops_export.py

# Exportar CSV
python reports/azuredevops_export.py --csv

# Criar via API REST
python reports/azuredevops_export.py --create
```

Variáveis de ambiente necessárias para `--create`:

```env
ADO_ORG=https://dev.azure.com/<org>
ADO_PROJECT=<projeto>
ADO_PAT=<personal-access-token>
ADO_EPIC_ID=<id-numerico-do-epico>
```

Ou use o `run_ado.cmd` (Windows) preenchendo as variáveis no arquivo.

### Google Docs

Requer service account do Google Cloud. Veja `spec_gdocs/SETUP.md` para configuração completa.

```bash
python spec_gdocs/generate_gdoc.py
```

## Sprints atribuídas automaticamente por módulo

Cada módulo (repositório) recebe uma sprint baseada na sua posição na ordem de migração. A ordem é determinada pelo número de impactos de alta complexidade (decrescente) e total de impactos. Dentro de cada módulo, as áreas seguem a sequência técnica:

| Sequência interna | Área |
|-------------------|------|
| 1º | Segurança/LGPD |
| 2º | Banco de Dados |
| 3º | API/Contrato |
| 4º | Infraestrutura/CI + Configuração |
| 5º | Integrações |
| 6º | Processamento/Batch |
| 7º | Backend |
| 8º | Testes/Qualidade + Documentação |
| 9º | Frontend |

## Dependências por módulo

| Módulo | Dependências extras |
|--------|---------------------|
| Scanner principal | `aiohttp`, `python-dotenv`, `tqdm`|
| PDF | `reportlab` |
| Word | `python-docx` |
| Azure DevOps | `requests` (já incluso) |
| Google Docs | `google-api-python-client`, `google-auth` |

## Ferramentas de análise (`tools/`)

Scripts utilitários para inspecionar o resultado do scan:

| Script | Descrição |
|--------|-----------|
| `analyze.py` | Distribuição de padrões que geraram impactos, top 30 regras |
| `analyze_telas.py` | Análise das telas inferidas para QA |
| `check_coverage.py` | Verifica cobertura de repos e aliases suspeitos |
| `check_exts.py` | Lista extensões de arquivo encontradas nos impactos |
| `update_telas.py` | Atualiza mapeamento de telas no JSON de saída |

```bash
python tools/analyze.py
python tools/analyze_telas.py
python tools/check_coverage.py
python tools/check_exts.py
python tools/update_telas.py
```

## Estrutura do projeto

```
scanner/
├── scanner.py              # Entry point e orquestrador CLI
├── scanner-config.json     # Configuração de regras e org
├── core/
│   ├── config.py           # Carregamento de config e compilação de regras
│   ├── engine.py           # Scan por arquivo, deduplicação, contagem de chamadores
│   ├── github_client.py    # Client async para GitHub API (Search + Tree + Blob)
│   ├── cache.py            # Cache em disco de conteúdo de arquivos
│   └── output.py           # Consolidação de impactos e geração de relatórios
├── reports/
│   ├── dashboard.py        # Dashboard HTML interativo
│   ├── generate_docx.py    # Exportação para Word (.docx)
│   ├── docx_builder/       # Módulos internos do gerador DOCX
│   └── azuredevops_export.py # Criação de work items no Azure DevOps
├── spec_pdf/               # Geração de relatório em PDF
├── spec_gdocs/             # Exportação para Google Docs
└── tools/                  # Utilitários de análise e cobertura
```

## Variáveis de ambiente

```env
GITHUB_TOKEN=<seu_github_pat>
```

## Limitações conhecidas

- A Search API do GitHub retorna no máximo 1000 resultados por repositório (o scanner faz fallback via tree completa automaticamente).
- Arquivos > 500KB são ignorados por padrão (use `--include-large-files` para incluí-los).
- Campos que não usam a palavra `cnpj` no nome podem não ser detectados sem `--scan-aliases`.
- Linhas de comentário são descartadas como falso positivo.
" #   p l a n e j a d o r - i n t e l i g e n t e - d e - m i g r a c a o "      
 