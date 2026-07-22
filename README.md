# Impact Scanner

Ferramenta de análise estática configurável que varre repositórios GitHub de uma organização em busca de código impactado por uma mudança de domínio definida em `scanner-config.yaml`. Originalmente criada para o CNPJ alfanumérico (Receita Federal), mas o motor de scan é 100% genérico — basta trocar as regras e os textos de relatório no arquivo de configuração.

Gera relatórios em JSON, Markdown, HTML, PDF, Word e Azure DevOps com matriz de impacto, plano de migração inteligente, trilhas paralelas, risk score, heatmap de risco, checklist de rollback, critérios de aceite e mapeamento de parceiros externos.

## Pré-requisitos

- Python 3.11+
- GitHub Personal Access Token com permissão `repo` (leitura)
- `git` instalado no PATH (necessário para `scripts/clone_repos.py`)

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

Edite `.env` e preencha ao menos `GITHUB_TOKEN`. Para aumentar o rate limit da Search API, adicione tokens extras — cada um tem cota independente:

```env
GITHUB_TOKEN=ghp_token_principal
GITHUB_TOKEN_2=ghp_token_secundario
GITHUB_TOKEN_3=ghp_token_terciario
```

## Uso

```bash
# Scan completo da org configurada
python scanner.py

# Repos específicos
python scanner.py -r repo1 repo2 repo3

# Repo único
python scanner.py -r backoffice

# Lista de repos a partir de arquivo (um por linha, # para comentários)
python scanner.py --repos-file repos.txt

# Excluir repos a partir de arquivo
python scanner.py --exclude-repos-file ignore.txt

# Sobrescrever org
python scanner.py -o minha-org

# Usar config alternativa (.json ou .yaml/.yml)
python scanner.py -c outro-config.yaml

# Apenas JSON ou apenas Markdown
python scanner.py --json-only
python scanner.py --md-only

# Retomar execução interrompida
python scanner.py --resume

# Limpar cache e checkpoint antes de rodar
python scanner.py --clear-cache

# Incluir busca por aliases de campo em todos os repos
python scanner.py --scan-aliases

# Auditar aliases em repos sem impacto (usa Search API — mais lento)
python scanner.py --audit-aliases

# Baixar arquivos > 500KB via Blob API
python scanner.py --include-large-files

# Repos processados em paralelo (padrão: 2 para API, 8 para --local)
python scanner.py --concurrency 8

# Usar repos clonados localmente em vez da GitHub API
python scanner.py --local /caminho/para/repos

# Desativar TUI e usar saída de texto simples
python scanner.py --no-ui

# Nível de log
python scanner.py --log-level DEBUG
```

### Interface TUI (padrão)

Quando `textual` está instalado, o scanner exibe uma interface interativa com:

- Painel lateral com status de cada repo em tempo real (⏳ pendente → 🔄 processando → ✅ ok / ❌ erro)
- Tabela de impactos detectados com área e complexidade coloridas
- Painel de log com timestamps
- Contador de impactos por complexidade (Alta / Média / Baixa) e tempo decorrido
- Tecla `q` para sair

Use `--no-ui` para desativar (útil em CI/CD ou quando `textual` não está instalado).

### Clonar repos para scan local

O modo `--local` é significativamente mais rápido que a GitHub API e não consome rate limit.

```bash
# Clonar todos os repos da org (shallow clone, paralelo)
python scripts/clone_repos.py

# Repos específicos
python scripts/clone_repos.py -r repo1 repo2

# Atualizar repos já clonados (git pull)
python scripts/clone_repos.py --update

# Diretório de destino alternativo (padrão: repos/)
python scripts/clone_repos.py -d /outro/caminho

# Controlar paralelismo (padrão: 8)
python scripts/clone_repos.py --concurrency 4
```

Após clonar:

```bash
python scanner.py --local repos/ --concurrency 8
```

## Configuração (`scanner-config.yaml`)

O arquivo de configuração controla tanto o comportamento do scan quanto todos os textos dos relatórios gerados. Campos marcados como opcionais têm fallback para valores padrão — configs existentes continuam funcionando sem modificação.

### Campos principais

| Campo | Descrição |
|-------|-----------|
| `titulo_analise` | Título exibido no banner e nos relatórios (opcional) |
| `nome_campo` | Nome do campo analisado, ex: `CNPJ` (opcional) |
| `checkpoint_file` | Caminho do arquivo de checkpoint (opcional) |
| `github_org` | Organização GitHub a escanear |
| `repositorios` | Lista de repos específicos (vazio = todos da org) |
| `ignore_paths` | Caminhos/extensões ignorados (node_modules, dist, etc.) |
| `prioridade_area` | Ordem de prioridade das áreas para deduplicação e migração |
| `regras` | Lista de regras com padrões regex por área e extensão de arquivo |
| `output_file` | Caminho do JSON de saída |
| `output_markdown` | Caminho do Markdown de saída |

### Campos opcionais de relatório

Todos os textos dos relatórios são configuráveis. Se ausentes, o scanner usa os defaults embutidos:

| Campo | Descrição |
|-------|-----------|
| `sql_alias_columns` | Aliases de coluna SQL a detectar estruturalmente |
| `pontos_cegos` | Lista de pontos cegos conhecidos para o relatório |
| `parceiros_conhecidos` | Parceiros externos mapeados |
| `rollback_base` | Itens base do checklist de rollback |
| `rollback_area` | Itens de rollback por área técnica |
| `riscos_area` | Riscos mapeados por área |
| `criterios_area` | Critérios de aceite por área |
| `criterios_encerramento` | Critérios de encerramento da migração |
| `tela_keywords` | Mapeamento de keywords → nome de tela para QA |
| `secoes_extras` | Seções adicionais no relatório Markdown (tabelas genéricas) |

## Áreas cobertas pelas regras (configuração padrão CNPJ)

| ID | Área | Exemplos detectados |
|----|------|---------------------|
| SEC-001 | Segurança/LGPD | CNPJ real hardcoded no código |
| CFG-001 | Configuração | `application.yml`, `.env` com CNPJ fixo |
| INFRA-001 | Infraestrutura/CI | Dockerfile, Jenkinsfile com CNPJ em variável |
| JPA-001 | Banco de Dados | `@Column(length=14)` em entidades JPA |
| DB-001 | Banco de Dados | `VARCHAR(14)`, `NUMBER(14)`, índices e constraints |
| MIGRATION-001 | Banco de Dados | Scripts Flyway/Liquibase com tipo incompatível |
| API-001 | API/Contrato | OpenAPI/Swagger/Protobuf com pattern numérico |
| INT-001 | Integrações | Kafka, SQS, SOAP, REST clients |
| XSD-001 | Integrações | Schemas XSD/WSDL com pattern numérico |
| BE-001 | Backend | Validadores, formatadores, regex `\d{14}` |
| STR-001 | Backend | `substring(0,8)`, `slice`, índice posicional |
| BATCH-001 | Processamento/Batch | Jobs, ETL, SPED, NFS-e |
| JASPER-001 | Processamento/Batch | Templates `.jrxml` com máscara numérica |
| TEMPLATE-001 | Processamento/Batch | Templates Freemarker/Velocity |
| TEST-001 | Testes/Qualidade | Fixtures, mocks, seeds hardcoded |
| FE-001 | Frontend | Máscaras, validações, `inputMode="numeric"` |
| DOC-001 | Documentação | README/docs com formato exclusivamente numérico |

## Saídas geradas

| Arquivo | Conteúdo |
|---------|----------|
| `impacto_cnpj.json` | Relatório completo com matriz de impacto, estatísticas, ordem de migração, checklist de rollback, riscos, parceiros externos e telas para QA |
| `impacto_cnpj.md` | Versão Markdown para visualização no GitHub/Confluence |
| `impacto_cnpj.html` | Dashboard HTML interativo com gráficos, filtros e navegação por repositório |
| `impacto_cnpj.pdf` | Relatório em PDF formatado (ReportLab) |
| `impacto_cnpj.docx` | Documento Word com todas as seções da SPEC |
| `ado_workitems.csv` | Hierarquia Feature > PBI > Task para importação no Azure DevOps |

Cada JSON inclui `scan_id` (ex: `20250115_143022`) e `data_execucao` (ISO 8601 BRT) para rastreabilidade entre execuções.

## Comparação entre scans (`scan_diff`)

```bash
# Compara dois JSONs e exibe resumo no terminal
python reports/scan_diff.py scan_anterior.json scan_atual.json

# Salva o diff em arquivo
python reports/scan_diff.py scan_anterior.json scan_atual.json --out diff.json

# Embute o diff no JSON atual e regenera o dashboard HTML
python reports/scan_diff.py scan_anterior.json scan_atual.json --embed
```

O diff classifica cada impacto como: 🔴 novo / 🟢 resolvido / 🟡 alterado / ⚪ mantido.

## Exportações e relatórios adicionais

### Dashboard HTML

```bash
python reports/dashboard.py
python reports/dashboard.py scan_backoffice.json
```

### PDF

```bash
python spec_pdf/generate_pdf.py
python spec_pdf/generate_pdf.py scan_backoffice.json scan_backoffice.pdf
```

Requer `reportlab`.

### Word (.docx)

```bash
python reports/generate_docx.py
python reports/generate_docx.py scan_backoffice.json
python reports/generate_docx.py scan_backoffice.json relatorio_backoffice.docx
```

Requer `python-docx`.

### Azure DevOps

Hierarquia: **Épico → Feature (fluxo) → PBI ([Fluxo] repo) → Task**

```bash
python reports/azuredevops_export.py          # dry-run
python reports/azuredevops_export.py --csv    # exporta CSV
python reports/azuredevops_export.py --create # cria via API REST
```

Variáveis necessárias para `--create`:

```env
ADO_ORG=https://dev.azure.com/<org>
ADO_PROJECT=<projeto>
ADO_PAT=<personal-access-token>
ADO_EPIC_ID=<id-numerico-do-epico>
```

### Google Docs

Requer service account do Google Cloud. Veja `reports/spec_gdocs/SETUP.md`.

```bash
python reports/spec_gdocs/generate_gdoc.py
```

## Testes

O projeto usa `pytest` com cobertura mínima de 60% em `core/`.

```bash
# Instalar dependências de dev
pip install -r requirements-dev.txt

# Rodar testes
pytest tests/

# Com cobertura
pytest tests/ --cov=core --cov-report=term-missing
```

Ou via Makefile:

```bash
make test
make test-cov
```

### O que está coberto

| Módulo | Arquivo de teste | O que testa |
|--------|-----------------|-------------|
| `core/cache.py` | `tests/test_cache.py` | put/get, roundtrip, SHA errado, save/load, arquivo corrompido |
| `core/config.py` | `tests/test_config.py` | compilação de regras, regex inválido ignorado, prioridade de área, load_config |
| `core/engine.py` | `tests/test_engine.py` | false positives, scan_file, scan_sql_structural, deduplicate, process_repo |
| `core/output.py` | `tests/test_output.py` | _calc_prioridade, build_output (estrutura, contagem, IDs, rollback), generate_markdown |

## Makefile

```bash
make install    # pip install requirements + requirements-dev
make lint       # ruff check + mypy
make fmt        # ruff format + ruff check --fix
make test       # pytest tests/
make test-cov   # pytest com cobertura
make scan       # python scanner.py
make clean      # remove __pycache__, *.pyc, checkpoint
```

## Ferramentas de análise (`tools/`)

| Script | Descrição |
|--------|-----------|
| `analyze.py` | Distribuição de padrões que geraram impactos, top 30 regras |
| `analyze_telas.py` | Análise das telas inferidas para QA |
| `check_coverage.py` | Verifica cobertura de repos e aliases suspeitos |
| `check_exts.py` | Lista extensões de arquivo encontradas nos impactos |
| `blind_spots.py` | Identifica pontos cegos no scan |
| `update_telas.py` | Atualiza mapeamento de telas no JSON de saída |

## Estrutura do projeto

```
scanner/
├── scanner.py                  # Entry point e orquestrador CLI
├── scanner-config.yaml         # Configuração principal (regras, org, textos de relatório)
├── scanner-config.json         # Config alternativa em JSON
├── core/
│   ├── config.py               # Carregamento de config, compilação de regras, getters opcionais
│   ├── engine.py               # Scan por arquivo, deduplicação, contagem de chamadores
│   ├── github_client.py        # Client async para GitHub API (Search + Tree + Blob)
│   ├── local_client.py         # Client para repos clonados localmente
│   ├── cache.py                # Cache em disco de conteúdo de arquivos
│   ├── output.py               # Consolidação de impactos e geração de relatórios
│   ├── ui.py                   # Interface TUI (Textual)
│   └── planner/                # Motor de planejamento de migração
│       ├── planner.py
│       ├── strategies.py
│       ├── trails.py
│       ├── risk.py
│       ├── simulation.py
│       ├── dependencies.py
│       ├── metrics.py
│       └── models.py
├── reports/
│   ├── dashboard.py            # Dashboard HTML interativo
│   ├── generate_docx.py        # Exportação para Word (.docx)
│   ├── scan_diff.py            # Comparação entre dois scans
│   ├── azuredevops_export.py   # Criação de work items no Azure DevOps
│   ├── docx_builder/           # Módulos internos do gerador DOCX
│   └── spec_gdocs/             # Exportação para Google Docs
├── spec_pdf/                   # Geração de relatório em PDF
├── scripts/                    # clone_repos.py, run_ado.cmd, run_lote_*.cmd
├── tests/                      # Testes automatizados (pytest)
│   ├── conftest.py
│   ├── test_cache.py
│   ├── test_config.py
│   ├── test_engine.py
│   └── test_output.py
└── tools/                      # Utilitários de análise e cobertura
```

## Sprints atribuídas automaticamente por módulo

Cada módulo recebe uma sprint baseada na sua posição na ordem de migração (número de impactos Alta decrescente). Dentro de cada módulo, as áreas seguem a sequência técnica:

| Sequência | Área |
|-----------|------|
| 1º | Segurança/LGPD |
| 2º | Banco de Dados |
| 3º | API/Contrato |
| 4º | Infraestrutura/CI + Configuração |
| 5º | Integrações |
| 6º | Processamento/Batch |
| 7º | Backend |
| 8º | Testes/Qualidade + Documentação |
| 9º | Frontend |

## Dependências

| Módulo | Pacotes |
|--------|---------|
| Scanner principal | `aiohttp`, `python-dotenv`, `tqdm`, `pyyaml` |
| TUI | `textual>=0.80.0` |
| PDF | `reportlab` |
| Word | `python-docx` |
| Google Docs | `google-api-python-client`, `google-auth` |
| Dev/testes | `pytest`, `pytest-asyncio`, `pytest-cov`, `ruff`, `mypy`, `pre-commit` |

## Variáveis de ambiente

```env
# Obrigatório
GITHUB_TOKEN=<seu_github_pat>

# Opcionais — tokens extras aumentam o rate limit da Search API
GITHUB_TOKEN_2=<segundo_pat>
GITHUB_TOKEN_3=<terceiro_pat>
# ... até GITHUB_TOKEN_9

# Azure DevOps (necessário para --create)
ADO_ORG=https://dev.azure.com/<org>
ADO_PROJECT=<projeto>
ADO_PAT=<personal-access-token>
ADO_EPIC_ID=<id-numerico-do-epico>
```

## Limitações conhecidas

- A Search API do GitHub retorna no máximo 1000 resultados por repositório (o scanner faz fallback via tree completa automaticamente).
- Arquivos > 500KB são ignorados por padrão (use `--include-large-files` para incluí-los).
- Campos que não usam o nome do campo no identificador podem não ser detectados sem `--scan-aliases`.
- Linhas de comentário são descartadas como falso positivo.
