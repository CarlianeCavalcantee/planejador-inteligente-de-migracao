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

## Validação de fluxo (`validate-flow`)

Verifica se um repositório ou fluxo completo está compatível com CNPJ alfanumérico. Complementa o scan de impacto respondendo: *"as alterações já feitas são suficientes para suportar o novo formato?"*

### Modo repositório — uso durante o desenvolvimento

Escaneia um repo clonado localmente e executa os checks de compatibilidade:

```bash
# Pelo nome do repo — encontra o clone local automaticamente
python scanner.py validate-flow -r authorizing-lib --flow boleto
python scanner.py validate-flow -r api-adesao --flow onboarding

# Na branch da sua demanda — faz checkout antes de escanear
python scanner.py validate-flow -r api-cobrancaterceiro --branch feature/AD-14230 --flow boleto

# Pelo path local (repo clonado fora das raízes conhecidas)
python scanner.py validate-flow -r C:\projetos\authorizing-lib --flow boleto

# Raiz adicional de busca, sem precisar do path completo
python scanner.py validate-flow -r ms-boleto --repos-root D:\clones --flow boleto

# Sem filtro de fluxo — valida o repo inteiro
python scanner.py validate-flow -r authorizing-lib
```

#### Como o caminho do repo é resolvido

`-r` aceita tanto um path quanto só o nome do projeto. Na busca por nome, as raízes são consultadas nesta ordem:

1. `--repos-root DIR` (pode repetir)
2. Env `LOCAL_REPOS_DIRS` (lista separada por `;` ou `,`)
3. `local_repos_dirs:` no `scanner-config.yaml`
4. `repos/` dentro do próprio scanner
5. O diretório que contém o scanner — ou seja, os projetos clonados lado a lado no mesmo workspace

Se nada for encontrado, o scanner lista onde procurou e sugere nomes parecidos antes de tentar clonar da org. Use `--no-clone` para falhar em vez de clonar.

#### Comportamento do `--branch`

O checkout nunca descarta trabalho: se já estiver na branch pedida, o scanner segue direto; se houver alterações não commitadas em outra branch, ele aborta pedindo commit ou stash; e se a branch só existir em `origin`, ele cria a branch de rastreio local. Sem `--branch`, valida a branch que estiver ativa.

O filtro `--flow` usa o mapeamento `tela_keywords` do config para resolver o nome do fluxo em keywords de caminho (ex: `boleto` → `boleto, cobranca, cobrancaterceiro`). Se o fluxo não tiver mapeamento, usa o próprio nome como filtro. Quando nenhum arquivo casa com as keywords, o scanner avisa em vez de reportar um resultado vazio como aprovado.

### Modo fluxo completo — uso antes da homologação

Valida todos os repositórios de um fluxo definido em `flows:` no config:

```bash
# A partir do JSON de scan já gerado (rápido)
python scanner.py validate-flow --flow onboarding

# Re-escaneia os repos clonados (mais preciso, não consome rate limit)
python scanner.py validate-flow --flow onboarding --local repos/

# JSON de scan alternativo
python scanner.py validate-flow --flow pix --scan-json docs/scans/scan_pix.json
```

Para usar o modo fluxo, defina os repos em `scanner-config.yaml`:

```yaml
flows:
  onboarding:
    name: "Onboarding PJ"
    repos:
      - api-adesao
      - backoffice
  boleto:
    name: "Boleto / Cobrança"
    repos:
      - authorizing-lib
      - ms-cobranca
```

### Checks executados

| ID | Severidade | Verifica |
|----|------------|----------|
| CHK-001 | Crítico | Nenhuma conversão numérica (`parseLong`, `parseInt`) sobre CNPJ |
| CHK-002 | Crítico | Nenhuma regex exclusivamente numérica (`\d{14}`, `[0-9]{14}`) |
| CHK-003 | Crítico | Nenhuma remoção de não-dígitos (`replaceAll([^0-9])`, `/\D/g`) |
| CHK-004 | Revisão | Nenhuma máscara numérica antiga (`99.999.999/9999-99`) |
| CHK-005 | Crítico | Nenhum padding numérico (`padStart`, `lpad` com `'0'`) |
| CHK-006 | Revisão | Nenhuma comparação de tamanho fixo (`length == 14`) |
| CHK-007 | Revisão | Validação compatível presente (`DocumentoUtils` ou `[A-Z0-9]{14}`) |
| CHK-008 | Crítico | Nenhuma referência à `CnpjUtils` — classe renomeada para `DocumentoUtils` |

Checks extras podem ser adicionados em `flow_checks:` no config.

### Status de saída

| Status | Condição |
|--------|----------|
| `APROVADO` | 0 pendentes, 0 falhas |
| `QUASE PRONTO` | 0 críticos, score ≥ 90% |
| `REQUER REVISÃO` | 0 críticos, score < 90% |
| `REPROVADO` | 1 ou mais checks críticos falharam |

Exit code `0` = APROVADO, `1` = qualquer outro status — permite uso como gate em CI/CD:

```bash
# Bloqueia o pipeline se o fluxo não estiver aprovado
python scanner.py validate-flow --repo . --flow onboarding || exit 1
```

### Fluxo de trabalho típico

```bash
# 1. Descobrir impactos no repo
python scanner.py --local repos/ -r api-adesao

# 2. Corrigir o código

# 3. Validar incrementalmente durante o desenvolvimento
python scanner.py validate-flow --repo repos/api-adesao --flow onboarding

# 4. Antes da homologação, validar o fluxo completo
python scanner.py validate-flow --flow onboarding --local repos/
```

## Migração automática (`migrate`)

Aplica transformações automáticas no código dos repos clonados, alinhando-os à `DocumentoUtils` oficial (`br.com.bscash.utils.DocumentoUtils` — antiga `br.com.bscash.documento.CnpjUtils`). Complementa o scan respondendo: *"o que posso corrigir automaticamente agora?"*

### Comandos

```bash
# Detectar ocorrências sem alterar arquivos
python -m migrate scan repos/
python -m migrate scan --flow onboarding
python -m migrate scan --flow onboarding --json

# Aplicar transformações (--dry-run simula sem escrever)
python -m migrate fix repos/ --dry-run
python -m migrate fix repos/
python -m migrate fix --flow onboarding --dry-run
python -m migrate fix --flow onboarding

# Gerar relatório Markdown + HTML
python -m migrate report repos/ --html
python -m migrate report --flow onboarding --html

# Modo CI: exit 1 se houver ocorrências não migradas
python -m migrate check repos/
python -m migrate check --flow onboarding

# Rodar testes dos repos após o fix
python -m migrate validate repos/

# Histórico de execuções
python -m migrate history
```

O `--flow` usa os fluxos definidos em `flows:` no `scanner-config.yaml` — os mesmos usados pelo `validate-flow`.

### Regras implementadas (`migrate/rules.yaml`)

| ID | Linguagem | O que transforma | Confiança |
|----|-----------|------------------|-----------|
| RN-001 | Java | `CnpjUtils.x()` → `DocumentoUtils.x()` + troca do import (classe renomeada) | auto |
| RM-001 | Java | `replaceAll("[^0-9]","")` / `replaceAll("[^A-Z0-9]","")` → `DocumentoUtils.removeMascara()` | auto |
| RM-002 | TS/JS | `.replace(/\D/g,'')` → `DocumentoUtils.removeMascara()` | review |
| RM-003 | Java | `.replace(".","").replace("/","").replace("-","")` → `DocumentoUtils.removeMascara()` | auto |
| RM-004 | Java | `replaceAll("[^A-Z0-9]","")` em qualquer variável | review |
| RX-003 | Java | `"[0-9]{14}"` → `"[A-Z0-9]{14}"` | auto |
| RX-004 | Java | `"\d{14}"` → `"[A-Z0-9]{14}"` | auto |
| RX-005 | TS/JS | `/[0-9]{14}/` → `/[A-Z0-9]{14}/` | auto |
| RX-006 | TS/JS | `/\d{14}/` → `/[A-Z0-9]{14}/` | auto |
| FMT-001 | Java | `CNPJ_FORMATADOR.matcher().replaceAll()` → `DocumentoUtils.formataCnpj()` | review |
| FMT-002 | Java | `formataCNPJ()` / `maskCNPJ()` → `DocumentoUtils.formataCnpj()` | auto |
| VAL-001a/b | Java | `CNPJ_*_MASCARA.matcher().matches()` → `DocumentoUtils.estaFormatado()` | review |
| VAL-002 | Java | `unmaskCnpj()` → `DocumentoUtils.removeMascara()` | auto |
| VAL-003 | Java | `@Pattern(regexp="\d{14}")` → `[A-Z0-9]{14}` | review |
| VAL-004 | Java | `@CNPJ` (Hibernate Validator numérico) | review |
| SQL-001 | SQL | `VARCHAR(14)` / `CHAR(14)` → `VARCHAR(20)` | review |
| SQL-002 | SQL | `NUMBER(14)` / `BIGINT(14)` → `VARCHAR(20)` | review |
| JPA-001 | Java | `@Column(length=1x)` em campo CNPJ/documento | review |
| JPA-002 | Java | `@Size(max=14)` → `@Size(max=20)` | review |
| OAS-001 | any | OpenAPI `pattern: \d{14}` → `[A-Z0-9]{14}` | review |
| OAS-002 | any | OpenAPI `maxLength: 14` → `20` | review |
| LEN-001 | Java | `.length() == 14` em variável CNPJ-like | review |
| LEN-002 | TS/JS | `.length === 14` em variável CNPJ-like | review |
| SUB-001 | Java | `cnpj.substring(x, y)` posicional | review |
| SUB-002 | TS/JS | `cnpj.substring()`/`slice()` posicional | review |
| MASK-001 | any | Máscara literal `"00.000.000/0000-00"` | review |

Regras `auto` são aplicadas diretamente. Regras `review` aparecem no relatório mas não alteram o arquivo — requerem confirmação humana.

### Falsos positivos

O migrador descarta automaticamente linhas que não representam risco real:

- Comentários e imports
- Propagação pura: `return cnpj;`, `this.cnpj = cnpj;`, `dto.setCnpj(cnpj);`, declarações de campo
- Campos CNPJ-like sem operação incompatível (ex: `log.info("cnpj={}", cnpj)`)

### Fluxo de trabalho típico

```bash
# 1. Descobrir impactos
python scanner.py --local repos/ -r api-adesao

# 2. Ver o que o migrate consegue corrigir automaticamente
python -m migrate scan --flow onboarding

# 3. Simular as correções
python -m migrate fix --flow onboarding --dry-run

# 4. Aplicar
python -m migrate fix --flow onboarding

# 5. Rodar testes
python -m migrate validate repos/

# 6. Validar compatibilidade
python scanner.py validate-flow --flow onboarding --local repos/
```



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
| `migrate/` | `tests/test_migrate_rules.py` | regras auto/review, falsos positivos, detecção de true positives, sanidade de patterns |

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
│   ├── flow.py                 # Análise de maturidade por fluxo de negócio
│   ├── flow_validator.py       # Gate de qualidade: validate-flow
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
├── migrate/
│   ├── cli.py              # Entry point: scan, fix, report, check, validate, history
│   ├── transformer.py      # Motor de transformação + filtro de falsos positivos
│   ├── rules.yaml          # Regras declarativas alinhadas à DocumentoUtils
│   ├── scanner_bridge.py   # Integração com JSON do scanner + suporte a flows
│   ├── git_guard.py        # Verifica working tree limpa antes do fix
│   ├── validator.py        # Executa testes dos repos após o fix
│   ├── history.py          # Histórico de execuções (JSONL)
│   ├── report_html.py      # Relatório HTML do migrate
│   └── transformers/       # Plugins por linguagem (Java, SQL, TypeScript)
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
│   ├── test_migrate_rules.py
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
