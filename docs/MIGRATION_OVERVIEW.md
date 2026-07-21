# Migração CNPJ Alfanumérico — Visão Geral

**Sistema:** BScash | **Scan ID:** `20260716_124220` | **Data:** 2026-07-16

---

## Visão Macro

### O que muda

A Receita Federal passa a emitir CNPJs com caracteres alfanuméricos nas posições 1–8 (raiz). O formato visual muda de `XX.XXX.XXX/XXXX-XX` (14 dígitos) para `XX.XXX.XXX/XXXX-XX` onde os primeiros 8 caracteres podem conter letras maiúsculas `[A-Z0-9]`. O algoritmo de dígito verificador também muda.

> CNPJs emitidos antes da mudança continuam válidos no formato numérico. O sistema precisa aceitar **ambos** durante o período de convivência.

### Escopo do impacto

| Dimensão | Valor |
|----------|-------|
| Repositórios analisados | 107 |
| Repositórios impactados | 53 |
| Total de impactos | 1.609 |
| Impactos de alta complexidade | 422 (26%) |
| Requerem compatibilidade dual | 94 |
| Parceiros externos a alinhar | 12 |

### Distribuição por área

| Área | Impactos | Alta | Dual | Prioridade |
|------|----------|------|------|------------|
| Pessoa Jurídica/PJ | 1.039 | 0 | — | Média |
| Backend | 168 | ~120 | 14+ | Alta |
| Segurança/LGPD | 160 | 160 | 0 | **Imediata** |
| Integrações | 71 | 50+ | 71 | Alta |
| Processamento/Batch | 66 | 0 | 0 | Alta |
| Frontend | 47 | 12 | 0 | Média |
| Banco de Dados | 47 | 10 | 0 | **Imediata** |
| Documentação | 8 | 0 | 0 | Baixa |
| Configuração | 3 | 0 | 0 | Média |

### Ordem de migração dos módulos (top 10 por criticidade)

| Sprint | Módulo | Impactos | Alta | Dual | Foco principal |
|--------|--------|----------|------|------|----------------|
| 1 | `atualizabanco` | 178 | 104 | 0 | Schema BD + LGPD (CNPJs hardcoded) |
| 1 | `backoffice` | 293 | 58 | 26 | BD + Integrações bancárias + Backend |
| 2 | `sped-efinanceira-client-bscash` | 88 | 34 | 31 | Integrações fiscais (e-Financeira) |
| 2 | `bopepo` | 27 | 26 | 14 | Lib de boleto — alta criticidade |
| 3 | `ms-negociacao` | 45 | 21 | 0 | LGPD + BD + PJ |
| 3 | `portal-cliente` | 39 | 17 | 6 | BD + Integrações + Frontend |
| 3 | `ms-pix-indireto` | 35 | 16 | 0 | BD + Backend |
| 4 | `pix-rotinas-indireto` | 42 | 13 | 0 | BD + Backend + Batch |
| 4 | `domkee` | 40 | 12 | 0 | Lib de validação CNPJ — efeito cascata |
| 4 | `ms-cartao` | 79 | 11 | 3 | Integrações + Batch |

> Ordem completa com 53 módulos disponível em [`docs/output/impacto_cnpj.md`](output/impacto_cnpj.md#-ordem-de-migração-por-módulo).

### Arquivos críticos (maior efeito cascata)

| Arquivo | Repo | Chamadores | Área |
|---------|------|------------|------|
| `01-controle_acesso.sql` | `atualizabanco` | 3.809 | LGPD |
| `01-controle_acesso_conta.sql` | `atualizabanco` | 3.809 | LGPD |
| `LayoutFebraban.java` | `backoffice` | 949 | Integrações |
| `IntegracaoBancariaBradesco.java` | `backoffice` | 637 | Integrações |
| `AntifraudePjVo.java` | `backoffice` | 1.025 | BD/JPA |
| `CNPJ.java` | `domkee` | 52 | Backend |
| `BoletoCampo.java` | `bopepo` | 59 | Integrações |

### Parceiros externos — alinhamento obrigatório antes do go-live

| Parceiro | Risco | Repos afetados |
|----------|-------|----------------|
| Bradesco | Layout CNAB/Febraban | `backoffice`, `bopepo`, `ms-pix`, `pix-rotinas` |
| Itaú | Layout CNAB240 | `api-cobrancaterceiro`, `bopepo`, `ms-boleto` |
| SERPRO | Consulta CNPJ Receita | `api-adesao`, `bscash-service-client` |
| Receita Federal | Validação numérica | `backoffice`, `sped-efinanceira-client-bscash` |
| QiTech | CCB/crédito | `atualizabanco` |
| Odontoprev | Contrato saúde dental | `ms-relatorio`, `backoffice-rotinas` |
| CAF | KYC/background check | `caf-rotinas` |
| Celcoin | PIX/pagamentos | `ms-celcoin` |
| Sunne | Constraint de BD | `atualizabanco` |
| BB | Remessa bancária | `backoffice` |
| Santander | Layout CNAB240 | `backoffice` |
| NFS-e | Schema XML fiscal | `atualizabanco` |

---

## Visão Micro — O que fazer em cada área

### 1. Segurança/LGPD — Ação imediata (160 impactos, todos Alta)

**Problema:** CNPJs reais de clientes/parceiros hardcoded em scripts SQL, seeds e fixtures.

**Ação:**
- Substituir por massa sintética ou variável de ambiente
- Auditar histórico do git: `git filter-repo --path-glob '*.sql' --invert-paths` ou `git log -S "XX.XXX.XXX"`
- Rotacionar secrets após remoção

**Repos críticos:** `atualizabanco` (103 ocorrências), `bopepo` (11), `ms-negociacao` (19)

---

### 2. Banco de Dados — Migrar primeiro (47 impactos)

**Problema:** Colunas `VARCHAR(14)`, `NUMBER(14)`, `CHAR(14)` e constraints de tamanho fixo não aceitam CNPJ alfanumérico.

**Ação:**
```sql
-- Ampliar coluna (mínimo 20 para comportar máscara XX.XXX.XXX/XXXX-XX)
ALTER TABLE <tabela> ALTER COLUMN <coluna_cnpj> TYPE VARCHAR(20);

-- Verificar colunas insuficientes
SELECT table_name, column_name, character_maximum_length
FROM information_schema.columns
WHERE column_name ILIKE '%cnpj%'
  AND character_maximum_length < 20;
```

**Repos críticos:** `atualizabanco` (29 ocorrências), `backoffice` (5 entidades JPA com `@Column(length=14)`)

**Atenção:** Manter colunas antigas como nullable durante período de convivência. Testar script de rollback em homologação antes de produção.

---

### 3. Backend — Validadores e manipulação posicional (168 impactos)

**Problema principal — regex numérica:**
```java
// ❌ Antes
String CNPJ_REGEX = "^\\d{2}\\.\\d{3}\\.\\d{3}\\/\\d{4}\\-\\d{2}$";

// ✅ Depois
String CNPJ_REGEX = "^[A-Z0-9]{2}\\.[A-Z0-9]{3}\\.[A-Z0-9]{3}\\/[A-Z0-9]{4}\\-[0-9]{2}$";
```

**Problema principal — manipulação posicional:**
```java
// ❌ Antes — assume raiz numérica
String raiz = cnpj.substring(0, 8); // só funciona com dígitos

// ✅ Depois — raiz pode ter letras, lógica de DV muda
// Usar biblioteca atualizada ou implementar novo algoritmo da Receita
```

**Repos críticos:** `domkee/CNPJ.java` (52 chamadores), `authorizing-lib/DocumentUtils.java`, `BScash-AdesaoPJ-Web/formatters.js`

---

### 4. Integrações — Compatibilidade dual (71 impactos, todos Alta)

**Problema:** Layouts CNAB, payloads SOAP/REST e schemas XSD com pattern `[0-9]{14}` rejeitam alfanumérico.

**Ação:**
- Implementar adapter de conversão numérico↔alfanumérico para parceiros que ainda não suportam o novo formato
- Atualizar schemas XSD: `<xs:pattern value="[A-Z0-9]{2}\.[A-Z0-9]{3}\.[A-Z0-9]{3}/[A-Z0-9]{4}-[0-9]{2}"/>`
- Confirmar suporte de cada parceiro antes do go-live (ver tabela de parceiros acima)

**Repos críticos:** `backoffice/LayoutFebraban.java` (949 chamadores), `bopepo/BoletoCampo.java` (59 chamadores), `ms-restsoap/InclusaoExclusaoSpcBrasil.xsd`

---

### 5. Frontend — Máscaras e validações (47 impactos)

**Problema:** Máscaras numéricas (`999.999.999/9999-99`) bloqueiam digitação de letras.

**Ação:**
```tsx
// ❌ Antes
<InputMask mask="99.999.999/9999-99" />

// ✅ Depois — aceitar [A-Z0-9] nas posições da raiz
// Usar máscara dinâmica ou campo livre com validação por regex alfanumérica
const CNPJ_REGEX = /^[A-Z0-9]{2}\.[A-Z0-9]{3}\.[A-Z0-9]{3}\/[A-Z0-9]{4}-[0-9]{2}$/;
```

**Repos críticos:** `BSadmin-web` (9 impactos, 7 Alta), `BScash-AdesaoPJ-Web`, `central-de-atendimento/inputmask.js`, `monorepo-mobile-app`

---

### 6. Processamento/Batch — Layouts e ETL (66 impactos)

**Problema:** Jobs que leem/gravam CNPJ em posição fixa de arquivo (CNAB, SPED, NFS-e) falham com letras.

**Ação:**
- Atualizar parsers de layout posicional para aceitar `[A-Z0-9]` nas posições da raiz
- Adicionar validação e alertas para registros descartados por falha de validação
- Testar com arquivo de entrada contendo CNPJ alfanumérico

**Repos críticos:** `sped-efinanceira-client-bscash` (28 ocorrências), `backoffice/LayoutFebraban.java`, `ms-relatorio` (templates Jasper)

---

### 7. Pessoa Jurídica/PJ — Entidades e fluxos (1.039 impactos)

**Problema:** Entidades, DTOs, repositórios e fluxos de onboarding PJ assumem CNPJ exclusivamente numérico.

**Ação por tipo:**

| Tipo | Ação |
|------|------|
| Entidade JPA com campo `cnpj: String` | Verificar se há `@Column(length=14)` → ampliar para 20 |
| DTO com validação `@Pattern(regexp="\\d{14}")` | Atualizar regex |
| Repository com query `WHERE cnpj = ?` | Sem mudança necessária se coluna já for VARCHAR |
| Template de documento (PDF/DOCX) | Atualizar máscara de exibição |
| Fluxo de onboarding | Testar com CNPJ alfanumérico em todas as etapas |

> A maioria dos 1.039 impactos PJ é de complexidade média/baixa — são referências a entidades que precisam de revisão pontual, não refatoração profunda.

---

## Checklist de go-live

### Pré-deploy
- [ ] CNPJs hardcoded removidos do código e histórico git auditado
- [ ] Colunas de BD ampliadas para `VARCHAR(20)` em todos os ambientes
- [ ] Novo algoritmo de DV alfanumérico implementado e coberto por testes unitários
- [ ] Regex `\d{14}` substituída em validadores críticos
- [ ] Manipulações posicionais (`substring(0,8)`) revisadas
- [ ] Máscaras de frontend atualizadas para aceitar `[A-Z0-9]`
- [ ] Todos os 12 parceiros externos confirmaram suporte ao novo formato
- [ ] Adapter de conversão numérico↔alfanumérico implementado para parceiros legados
- [ ] Feature flags configuradas para rollback sem novo deploy
- [ ] Scripts de rollback de BD testados em homologação

### Testes obrigatórios (P1)
- [ ] CNPJ alfanumérico válido aceito em todos os campos de entrada
- [ ] CNPJ numérico antigo continua funcionando (compatibilidade dual)
- [ ] Fluxo completo de Abertura de Conta PJ com CNPJ alfanumérico
- [ ] Geração de boleto com CNPJ alfanumérico (bopepo + backoffice)
- [ ] PIX com chave CNPJ alfanumérico
- [ ] Remessa bancária CNAB gerada e aceita pelo banco
- [ ] Relatórios Jasper exibindo CNPJ alfanumérico corretamente
- [ ] e-Financeira/SPED com CNPJ alfanumérico no XML

### Pós-deploy
- [ ] Monitoramento de erros (Sentry/Datadog) com alerta em < 5 min
- [ ] Logs de integração monitorados para detectar rejeições de parceiros
- [ ] Alertas para registros batch descartados por falha de validação

---

## Referências

| Documento | Descrição |
|-----------|-----------|
| [`docs/output/impacto_cnpj.md`](output/impacto_cnpj.md) | Relatório completo com todos os 1.609 impactos |
| [`docs/output/impacto_cnpj.html`](output/impacto_cnpj.html) | Dashboard interativo com filtros |
| [`docs/output/impacto_cnpj.json`](output/impacto_cnpj.json) | Dados brutos do scan (scan_id: `20260716_124220`) |
| [`docs/spec/`](spec/) | SPEC completa em DOCX |
| [Instrução Normativa RFB](https://www.gov.br/receitafederal) | Regulamentação oficial do CNPJ alfanumérico |
