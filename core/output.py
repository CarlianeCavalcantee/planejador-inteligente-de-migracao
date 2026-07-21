"""
Consolidação de impactos e geração de relatórios JSON + Markdown.
"""

from datetime import datetime, timezone, timedelta

from core.config import DUAL_COMPAT_RES

# ---------------------------------------------------------------------------
# Constantes de texto
# ---------------------------------------------------------------------------

_AREA_RATIONALE = {
    "Segurança/LGPD":      "Remover dados reais do código antes de qualquer outra mudança.",
    "Banco de Dados":      "Migrar schema primeiro — todas as camadas dependem do tipo da coluna.",
    "API/Contrato":        "Versionar contratos antes de alterar implementação para não quebrar consumidores.",
    "Infraestrutura/CI":   "Atualizar pipelines para que builds e testes usem o novo formato.",
    "Configuração":        "Externalizar CNPJs fixos antes de subir nova versão em produção.",
    "Integrações":         "Comunicar e alinhar parceiros externos antes de alterar payloads.",
    "Processamento/Batch": "Atualizar layouts de arquivo e validações de ETL após schema de BD.",
    "Backend":             "Refatorar validadores e lógica de negócio após BD e contratos estabilizados.",
    "Testes/Qualidade":    "Atualizar massa de dados e fixtures para cobrir o novo formato.",
    "Documentação":        "Atualizar docs e exemplos após implementação concluída.",
    "Frontend":            "Atualizar máscaras e validações de UI por último (menor risco de bloqueio).",
    "Pessoa Jurídica/PJ":  "Revisar entidades, DTOs e fluxos PJ após BD e contratos estabilizados — impacta onboarding e documentação de empresa.",
}

_ROLLBACK_BASE = [
    "Backup do banco de dados realizado antes da migration?",
    "Feature flag ativa para reverter sem novo deploy?",
    "Monitoramento de erros (Sentry/Datadog) configurado para alertar em < 5 min?",
    "Plano de comunicação com stakeholders em caso de rollback definido?",
]

_ROLLBACK_AREA = {
    "Banco de Dados": [
        "Script de rollback da migration testado em ambiente de homologação?",
        "Colunas antigas mantidas como nullable durante período de convivência?",
        "Índices antigos preservados até validação completa?",
    ],
    "API/Contrato": [
        "Rota /v1 mantida ativa durante período de convivência dual?",
        "Consumidores notificados com antecedência mínima de 30 dias?",
        "Testes de contrato (contract tests) passando para ambas as versões?",
    ],
    "Integrações": [
        "Parceiros externos confirmaram suporte ao novo formato?",
        "Adapter de conversão numérico↔alfanumérico implementado e testado?",
        "Logs de integração monitorados para detectar rejeições?",
    ],
    "Backend": [
        "Novo validador de DV alfanumérico coberto por testes unitários?",
        "Lógica de substring/slice revisada e testada com CNPJs alfanuméricos?",
    ],
    "Processamento/Batch": [
        "Job de rollback para reprocessar registros com formato antigo disponível?",
        "Alertas configurados para registros descartados por falha de validação?",
    ],
    "Segurança/LGPD": [
        "Git history auditado e CNPJs reais removidos (git filter-repo)?",
        "Secrets rotacionados após remoção de dados sensíveis?",
        "Documentos PJ (contrato social, procuração, ficha cadastral) com CNPJ hardcoded foram removidos de fixtures/seeds?",
    ],
    "Pessoa Jurídica/PJ": [
        "Entidades e DTOs de Empresa/PJ revertidos para tipo anterior em caso de falha?",
        "Fluxo de onboarding PJ testado com CNPJ alfanumérico e numérico?",
        "Templates de documentos PJ (contrato social, procuração, ficha cadastral) validados?",
    ],
    "Frontend": [
        "Máscara antiga disponível via feature flag para rollback imediato?",
        "Testes E2E cobrindo entrada de CNPJ alfanumérico?",
        "Fluxo de Abertura de Conta PJ testado com CNPJ alfanumérico (onboarding, upload de documentos)?",
        "Campos de Inscrição Estadual e Contrato Social aceitam CNPJ alfanumérico do representante legal?",
    ],
    "Infraestrutura/CI": [
        "Secrets de CI atualizados e pipeline testado com novo formato?",
        "Imagens Docker antigas tagueadas para rollback rápido?",
    ],
}

_SQL_QUERIES = {
    "Banco de Dados": [
        "-- Estimar volume de registros com CNPJ numérico puro (14 dígitos):\n"
        "SELECT COUNT(*) FROM <tabela> WHERE <coluna_cnpj> ~ '^[0-9]{14}$';",

        "-- Verificar CNPJs que já possuem letras (pós-migração parcial):\n"
        "SELECT COUNT(*) FROM <tabela> WHERE <coluna_cnpj> ~ '[A-Z]';",

        "-- Identificar colunas com tamanho insuficiente (< 20 chars):\n"
        "SELECT table_name, column_name, character_maximum_length\n"
        "FROM information_schema.columns\n"
        "WHERE column_name ILIKE '%cnpj%'\n"
        "  AND character_maximum_length < 20;",
    ],
    "Backend": [
        "-- Verificar se há CNPJs armazenados como número (sem zeros à esquerda):\n"
        "SELECT COUNT(*) FROM <tabela> WHERE LENGTH(<coluna_cnpj>) < 14;",
    ],
    "Integrações": [
        "-- Auditar registros de integração com CNPJ no payload:\n"
        "SELECT COUNT(*), MIN(created_at), MAX(created_at)\n"
        "FROM <tabela_integracao>\n"
        r"WHERE payload::text ~ '\"cnpj\":\s*\"[0-9]{14}\"';",
    ],
    "Processamento/Batch": [
        "-- Estimar volume de registros batch a reprocessar:\n"
        "SELECT COUNT(*) FROM <tabela_batch>\n"
        "WHERE status = 'PROCESSADO'\n"
        "  AND <coluna_cnpj> ~ '^[0-9]{14}$';",
    ],
}

_RISCOS_AREA = {
    "Segurança/LGPD": {
        "risco": "CNPJ real hardcoded no código (violação LGPD)",
        "impacto": "Dados de clientes expostos no repositório. Risco legal e de compliance.",
        "mitigacao": "Substituir por massa sintética ou variável de ambiente. Auditar histórico do git.",
    },
    "Banco de Dados": {
        "risco": "Truncamento ou erro de inserção em colunas numéricas",
        "impacto": "Colunas NUMBER/BIGINT ou VARCHAR(14) não aceitam caracteres alfabéticos.",
        "mitigacao": "Migrar colunas para VARCHAR com tamanho adequado (mínimo 20 para comportar máscara).",
    },
    "API/Contrato": {
        "risco": "Quebra de contratos em APIs expostas (Breaking Change)",
        "impacto": "Clientes integrados que enviarem letras receberão erro 400 ou crash interno.",
        "mitigacao": "Implementar versionamento de rota (/v2/) e período de convivência dual.",
    },
    "Infraestrutura/CI": {
        "risco": "CNPJ hardcoded em pipeline ou container",
        "impacto": "Dado sensível exposto em logs de CI/CD ou imagem Docker.",
        "mitigacao": "Usar secrets do CI (GitHub Secrets, Vault) e remover do Dockerfile/compose.",
    },
    "Configuração": {
        "risco": "Propriedade de configuração com CNPJ fixo",
        "impacto": "Ambientes de homologação e produção podem ter CNPJs numéricos fixos que não aceitarão o novo formato.",
        "mitigacao": "Revisar application.yml/properties e externalizar via variável de ambiente.",
    },
    "Integrações": {
        "risco": "Rejeição por parceiros/sistemas legados",
        "impacto": "Parceiros podem rejeitar payloads com letras no CNPJ.",
        "mitigacao": "Mapear e comunicar previamente todos os parceiros sobre o cronograma.",
    },
    "Backend": {
        "risco": "Falha em validadores de dígito verificador e manipulação posicional",
        "impacto": r"CNPJs alfanuméricos válidos serão rejeitados por regex \d{14} ou substring(0,8) retornará valor errado.",
        "mitigacao": "Substituir regex numérica e lógica posicional pela nova regra alfanumérica da Receita Federal.",
    },
    "Documentação PJ": {
        "risco": "Templates de documentos PJ com CNPJ em formato numérico fixo",
        "impacto": "Contratos sociais, procurações, fichas cadastrais e comprovantes de abertura de conta PJ gerados com máscara numérica serão inválidos para CNPJs alfanuméricos.",
        "mitigacao": "Atualizar templates de geração de documentos PJ (PDF, DOCX, HTML, JRXML) para aceitar e formatar CNPJ alfanumérico. Revisar validações de Inscrição Estadual e NIRE.",
    },
    "Processamento/Batch": {
        "risco": "Falha silenciosa em rotinas batch/ETL",
        "impacto": "Jobs podem descartar registros com CNPJ alfanumérico sem gerar alerta.",
        "mitigacao": "Adicionar validação e alertas em pipelines de processamento.",
    },
    "Pessoa Jurídica/PJ": {
        "risco": "Entidades e fluxos PJ assumem CNPJ exclusivamente numérico",
        "impacto": "Onboarding, cadastro e documentos de Pessoa Jurídica podem rejeitar ou truncar CNPJ alfanumérico.",
        "mitigacao": "Revisar entidades, DTOs, validadores e templates de documentos PJ para aceitar o novo formato.",
    },
    "Frontend": {
        "risco": "Bloqueio de digitação pelo usuário",
        "impacto": "Máscaras numéricas impedem entrada de letras no campo CNPJ.",
        "mitigacao": "Atualizar máscaras e validações de input para aceitar alfanumérico.",
    },
}


# Parceiros externos detectáveis por padrão de código
_PARCEIROS_CONHECIDOS = {
    "bradesco":   "Banco Bradesco — layout CNAB/Febraban pode rejeitar alfanumérico",
    "bb":         "Banco do Brasil — validação de CNPJ no layout de remessa",
    "itau":       "Banco Itaú — layout CNAB240",
    "santander":  "Banco Santander — layout CNAB240",
    "caixa":      "Caixa Econômica Federal — layout CNAB240",
    "serpro":     "SERPRO — consulta CNPJ na Receita Federal, pode ter validação numérica",
    "odontoprev": "Odontoprev — contrato de saúde dental, CNPJ hardcoded detectado",
    "qitech":     "QiTech — CCB/crédito, CNPJ hardcoded detectado",
    "celcoin":    "Celcoin — PIX/pagamentos",
    "caf":        "CAF — background check / KYC",
    "sunne":      "Sunne — parceiro com CNPJ em constraint de BD detectado",
    "nfse":       "NFS-e — nota fiscal de serviço, schema XML com CNPJ",
    "juntacomercial": "Junta Comercial — registro de empresa PJ, CNPJ no documento",
    "receita":    "Receita Federal — consulta CNPJ, pode ter validação numérica",
    "sped":       "SPED/EFD — obrigação fiscal, layout fixo numérico",
    "reinf":      "EFD-Reinf — obrigação fiscal, layout fixo numérico",
    "esocial":    "eSocial — obrigação trabalhista, layout fixo numérico",
}


def _build_parceiros_externos(matriz: list[dict]) -> list[dict]:
    """Detecta parceiros externos mencionados nos impactos e gera alerta de alinhamento."""
    encontrados = {}
    for m in matriz:
        trecho = (m["evidencia"]["trecho_codigo"] + m["componente"]).lower()
        for parceiro, descricao in _PARCEIROS_CONHECIDOS.items():
            if parceiro in trecho and parceiro not in encontrados:
                encontrados[parceiro] = {
                    "parceiro": parceiro,
                    "descricao": descricao,
                    "repositorios": set(),
                    "status_alinhamento": "pendente",
                }
            if parceiro in trecho and parceiro in encontrados:
                encontrados[parceiro]["repositorios"].add(m["repositorio"])
    result = []
    for p in sorted(encontrados.values(), key=lambda x: x["parceiro"]):
        result.append({**p, "repositorios": sorted(p["repositorios"])})
    return result


def _build_arquivos_criticos(matriz: list[dict]) -> list[dict]:
    """
    Top arquivos por chamadores_estimados.
    Esses são os pontos de entrada da migração — mudar um deles impacta
    dezenas ou centenas de outros componentes.
    """
    # Agrega por (repo, arquivo): pega o maior chamadores e lista todas as linhas
    agg: dict[tuple, dict] = {}
    for m in matriz:
        key = (m["repositorio"], m["componente"])
        callers = m["chamadores_estimados"]
        if key not in agg or callers > agg[key]["chamadores_estimados"]:
            agg[key] = {
                "repositorio": m["repositorio"],
                "arquivo": m["componente"],
                "area": m["area"],
                "chamadores_estimados": callers,
                "impactos_no_arquivo": 0,
                "linhas_afetadas": [],
                "requer_compatibilidade_dual": False,
            }
        agg[key]["impactos_no_arquivo"] += 1
        agg[key]["linhas_afetadas"].append(m["evidencia"]["linha"])
        if m["requer_compatibilidade_dual"]:
            agg[key]["requer_compatibilidade_dual"] = True

    # Ordena por chamadores desc, pega top 15
    ranked = sorted(agg.values(), key=lambda x: x["chamadores_estimados"], reverse=True)
    return ranked[:15]


def _build_trilhas(ordem_migracao: list[dict], cfg: dict, matriz: list[dict] | None = None) -> dict:
    """
    Agrupa repos por afinidade (áreas + fluxos compartilhados) e divide em N trilhas
    paralelas balanceadas por impactos Alta, mantendo fluxos completos na mesma trilha.
    N é configurável via cfg['trilhas'] (padrão: 2).
    """
    from collections import defaultdict
    n_trilhas = int(cfg.get("trilhas", 2))

    # Mapa repo → fluxos
    repo_fluxos: dict[str, frozenset] = {}
    fluxo_repos: dict[str, set] = defaultdict(set)
    if matriz:
        tmp: dict[str, set] = {}
        for m in matriz:
            f = m.get("fluxo")
            if f:
                tmp.setdefault(m["repositorio"], set()).add(f)
                fluxo_repos[f].add(m["repositorio"])
        repo_fluxos = {r: frozenset(fs) for r, fs in tmp.items()}

    def afinidade(a, b):
        """Score combinado: 40% Jaccard de áreas + 60% Jaccard de fluxos."""
        def jaccard(x, y):
            if not x and not y: return 1.0
            return len(x & y) / len(x | y)
        j_areas  = jaccard(a["areas"],  b["areas"])
        j_fluxos = jaccard(repo_fluxos.get(a["modulo"], frozenset()),
                           repo_fluxos.get(b["modulo"], frozenset()))
        return 0.4 * j_areas + 0.6 * j_fluxos

    repos = [
        {
            "modulo": m["modulo"],
            "passo":  m["passo"],
            "total":  m["total_impactos"],
            "alta":   m["impactos_alta_complexidade"],
            "dual":   m["requerem_compatibilidade_dual"],
            "areas":  frozenset(a["area"] for a in m["areas"]),
        }
        for m in ordem_migracao
    ]

    # Clustering por afinidade >= 0.4 (limiar menor para capturar fluxos compartilhados)
    clusters, used = [], set()
    for i, r in enumerate(repos):
        if i in used:
            continue
        cluster = [r]
        used.add(i)
        for j, s in enumerate(repos):
            if j not in used and afinidade(r, s) >= 0.4:
                cluster.append(s)
                used.add(j)
        clusters.append(cluster)
    clusters.sort(key=lambda c: sum(r["alta"] for r in c), reverse=True)

    # Divisão greedy em N trilhas — função objetivo: 40% carga + 60% fluxos partidos
    trilhas = [[] for _ in range(n_trilhas)]
    carga   = [0] * n_trilhas
    max_carga = sum(r["alta"] for r in repos) or 1

    def _custo(t_idx: int, cluster: list) -> float:
        """Custo de alocar cluster na trilha t_idx. Menor = melhor."""
        nova_carga = carga[t_idx] + sum(r["alta"] for r in cluster)
        carga_norm = nova_carga / max_carga

        # fluxos que o cluster traz
        fluxos_cluster = {f for r in cluster for f in repo_fluxos.get(r["modulo"], frozenset())}
        # repos já alocados nas outras trilhas
        repos_outras = {r["modulo"] for ti, repos_t in enumerate(trilhas) if ti != t_idx for r in repos_t}
        # um fluxo fica partido se algum repo dele já está em outra trilha
        partidos = sum(
            1 for f in fluxos_cluster
            if fluxo_repos.get(f, set()) & repos_outras
        )
        total_fluxos = len(fluxo_repos) or 1
        partidos_norm = partidos / total_fluxos

        return 0.4 * carga_norm + 0.6 * partidos_norm

    for cluster in clusters:
        t = min(range(n_trilhas), key=lambda i: _custo(i, cluster))
        trilhas[t].extend(cluster)
        carga[t] += sum(r["alta"] for r in cluster)

    # Mapa repo → trilha (para calcular fluxos completos vs partidos)
    repo_trilha = {r["modulo"]: t for t, repos_t in enumerate(trilhas) for r in repos_t}

    # Fluxos completos (todos os repos do fluxo na mesma trilha) vs partidos
    fluxos_completos: dict[int, list] = defaultdict(list)  # trilha → [fluxo]
    fluxos_partidos: list[dict] = []
    for fluxo, repos_do_fluxo in fluxo_repos.items():
        trilhas_do_fluxo = {repo_trilha[r] for r in repos_do_fluxo if r in repo_trilha}
        if len(trilhas_do_fluxo) == 1:
            fluxos_completos[list(trilhas_do_fluxo)[0]].append(fluxo)
        elif len(trilhas_do_fluxo) > 1:
            n_repos   = len(repos_do_fluxo)
            n_trilhas_fluxo = len(trilhas_do_fluxo)
            if   n_repos <= 2 or n_trilhas_fluxo == 2 and n_repos <= 3:
                gravidade = "Baixo"
            elif n_repos <= 5 and n_trilhas_fluxo <= 2:
                gravidade = "Médio"
            elif n_repos <= 10 and n_trilhas_fluxo <= 3:
                gravidade = "Alto"
            else:
                gravidade = "Crítico"
            fluxos_partidos.append({
                "fluxo": fluxo,
                "trilhas": sorted(t + 1 for t in trilhas_do_fluxo),
                "repositorios": sorted(repos_do_fluxo),
                "n_repositorios": n_repos,
                "n_trilhas_envolvidas": n_trilhas_fluxo,
                "gravidade": gravidade,
                "alerta": "Fluxo partido entre trilhas — coordenar entrega conjunta antes do go-live.",
            })
    _GRAVIDADE_ORDER = {"Crítico": 0, "Alto": 1, "Médio": 2, "Baixo": 3}
    fluxos_partidos.sort(key=lambda x: (_GRAVIDADE_ORDER.get(x["gravidade"], 9), x["fluxo"]))

    # Alerta de dependências cruzadas (BD e API)
    criticos = {"Banco de Dados", "API/Contrato"}
    cross: dict = defaultdict(list)
    for r in repos:
        for area in r["areas"] & criticos:
            cross[area].append(r["modulo"])
    dependencias = [
        {"area": area, "repositorios": mods}
        for area, mods in cross.items()
        if len(mods) > 1
    ]

    ABBREV = {
        "Banco de Dados": "BD", "Backend": "BE", "API/Contrato": "API",
        "Frontend": "FE", "Integrações": "INT", "Processamento/Batch": "BATCH",
        "Segurança/LGPD": "SEC", "Infraestrutura/CI": "INFRA",
        "Configuração": "CFG", "Testes/Qualidade": "TEST",
        "Documentação": "DOC", "Pessoa Jurídica/PJ": "PJ",
    }

    grupos = []
    for i, cluster in enumerate(clusters, 1):
        areas_union = frozenset().union(*(r["areas"] for r in cluster))
        cluster_fluxos = sorted({f for r in cluster for f in repo_fluxos.get(r["modulo"], frozenset())})
        grupos.append({
            "grupo": i,
            "perfil": " + ".join(ABBREV.get(a, a[:4]) for a in sorted(areas_union)),
            "total_alta": sum(r["alta"] for r in cluster),
            "total_impactos": sum(r["total"] for r in cluster),
            "fluxos": cluster_fluxos,
            "repositorios": [
                {"modulo": r["modulo"], "passo": r["passo"],
                 "alta": r["alta"], "total": r["total"], "dual": r["dual"],
                 "fluxos": sorted(repo_fluxos.get(r["modulo"], frozenset()))}
                for r in sorted(cluster, key=lambda x: -x["alta"])
            ],
        })

    # Grafo de dependências entre trilhas
    # Aresta (origem → destino): a trilha destino deve ser concluída antes da origem.
    # Fonte 1: fluxos partidos — trilha com menos repos do fluxo depende da que tem mais.
    # Fonte 2: dependências cruzadas de BD/API — trilha sem BD/API depende da que tem.
    arestas: dict[tuple[int,int], list[str]] = defaultdict(list)

    for fp in fluxos_partidos:
        trilhas_fluxo = fp["trilhas"]  # já são 1-based
        # conta repos por trilha neste fluxo
        repos_por_trilha = defaultdict(int)
        for r in fp["repositorios"]:
            t_idx = repo_trilha.get(r)
            if t_idx is not None:
                repos_por_trilha[t_idx + 1] += 1
        if len(repos_por_trilha) >= 2:
            # trilha com mais repos é a "provedora"; as demais dependem dela
            provedora = max(repos_por_trilha, key=lambda t: repos_por_trilha[t])
            for t in trilhas_fluxo:
                if t != provedora:
                    arestas[(provedora, t)].append(fp["fluxo"])

    for dep in dependencias:
        # repos com BD/API crítico: a trilha que os contém é provedora
        for repo in dep["repositorios"]:
            t_prov = repo_trilha.get(repo)
            if t_prov is None:
                continue
            for t_other in range(n_trilhas):
                if t_other != t_prov and trilhas[t_other]:
                    chave = (t_prov + 1, t_other + 1)
                    motivo = f"{dep['area']} em {repo}"
                    if motivo not in arestas[chave]:
                        arestas[chave].append(motivo)

    grafo_nos = [
        {"trilha": t + 1, "carga_alta": carga[t],
         "total_impactos": sum(r["total"] for r in trilhas[t])}
        for t in range(n_trilhas)
    ]
    grafo_arestas = [
        {"de": de, "para": para,
         "motivos": motivos,
         "descricao": f"Trilha {de} deve ser concluída antes da Trilha {para}"}
        for (de, para), motivos in sorted(arestas.items())
    ]

    delta = abs(carga[0] - carga[1]) if n_trilhas >= 2 else 0
    total_alta = sum(carga)
    return {
        "n_trilhas": n_trilhas,
        "desequilibrio_pct": round(delta / total_alta * 100) if total_alta else 0,
        "grupos": grupos,
        "trilhas": [
            {
                "trilha": t + 1,
                "carga_alta": carga[t],
                "total_impactos": sum(r["total"] for r in trilhas[t]),
                "fluxos_completos": sorted(fluxos_completos.get(t, [])),
                "fluxos": sorted({f for r in trilhas[t] for f in repo_fluxos.get(r["modulo"], frozenset())}),
                "repositorios": [
                    {"modulo": r["modulo"], "passo": r["passo"],
                     "alta": r["alta"], "total": r["total"],
                     "perfil": " + ".join(ABBREV.get(a, a[:4]) for a in sorted(r["areas"])),
                     "fluxos": sorted(repo_fluxos.get(r["modulo"], frozenset()))}
                    for r in sorted(trilhas[t], key=lambda x: x["passo"])
                ],
            }
            for t in range(n_trilhas)
        ],
        "fluxos_partidos": fluxos_partidos,
        "dependencias_cruzadas": dependencias,
        "grafo_dependencias": {"nos": grafo_nos, "arestas": grafo_arestas},
    }


# Áreas que bloqueiam outras — quem tem BD/API deve migrar antes de quem tem só BE/FE
_AREA_PESO_DEP = {
    "Banco de Dados":      0,
    "API/Contrato":        1,
    "Infraestrutura/CI":   2,
    "Configuração":        2,
    "Integrações":         3,
    "Processamento/Batch": 4,
    "Backend":             5,
    "Segurança/LGPD":      5,
    "Testes/Qualidade":    6,
    "Documentação":        6,
    "Frontend":            7,
    "Pessoa Jurídica/PJ":  7,
}


def _build_ordem_migracao(matriz: list[dict], cfg: dict) -> list[dict]:
    """
    Gera ordem de migração por módulo com topological sort baseado em
    dependências arquiteturais derivadas dos dados de impacto.

    Dependências inferidas:
    1. Sufixo *-lib / *-client / *-common → provedor deve migrar antes dos consumidores.
    2. Repos no mesmo fluxo com BD/API → migram antes dos que têm só BE/FE.
    3. Ciclos são quebrados mantendo o de maior carga primeiro.
    """
    from collections import defaultdict, deque
    from core.config import area_priority
    priority = area_priority(cfg)

    # Agrupa por repo
    repos: dict[str, list] = {}
    for m in matriz:
        repos.setdefault(m["repositorio"], []).append(m)

    repo_areas: dict[str, set] = {
        r: {m["area"] for m in itens} for r, itens in repos.items()
    }
    repo_alta: dict[str, int] = {
        r: sum(1 for m in itens if m["complexidade"] == "Alta")
        for r, itens in repos.items()
    }

    # --- Inferir dependências ---
    deps: dict[str, set] = defaultdict(set)  # deps[r] = {repos que r depende}

    # 1. Sufixo lib/client/common: consumidor depende do provedor
    _PROVIDER_SUFFIXES = ("-lib", "-client", "-common", "-sdk", "-core")
    providers = {r for r in repos if any(r.endswith(s) for s in _PROVIDER_SUFFIXES)}
    for consumer in repos:
        if consumer in providers:
            continue
        for prov in providers:
            # heurística: nome do provedor está contido no nome do consumidor
            base = prov.split("-")[0]  # ex: "pix" de "pix-lib"
            if base in consumer and prov != consumer:
                deps[consumer].add(prov)

    # 2. Fluxos compartilhados: repo com BD/API precede repo com só BE/FE
    fluxo_repos_map: dict[str, list] = defaultdict(list)
    for m in matriz:
        f = m.get("fluxo")
        if f:
            fluxo_repos_map[f].append(m["repositorio"])

    for fluxo, repos_fluxo in fluxo_repos_map.items():
        repos_fluxo_uniq = list(dict.fromkeys(repos_fluxo))
        # ordena por peso de área mínimo (quem tem BD vem antes)
        def _min_peso(r):
            return min((_AREA_PESO_DEP.get(a, 9) for a in repo_areas.get(r, set())), default=9)
        repos_fluxo_uniq.sort(key=_min_peso)
        for i, r_after in enumerate(repos_fluxo_uniq[1:], 1):
            r_before = repos_fluxo_uniq[i - 1]
            if r_before != r_after:
                deps[r_after].add(r_before)

    # --- Topological sort (Kahn) com desempate por carga Alta desc ---
    in_degree = {r: 0 for r in repos}
    adj: dict[str, set] = defaultdict(set)  # adj[r] = {quem depende de r}
    for r, predecessores in deps.items():
        for p in predecessores:
            if p in repos:  # ignora deps fora do escopo
                adj[p].add(r)
                in_degree[r] += 1

    # fila de prioridade: menor in_degree primeiro, desempate por -alta
    import heapq
    heap = [(-repo_alta.get(r, 0), r) for r, d in in_degree.items() if d == 0]
    heapq.heapify(heap)

    sorted_repos: list[str] = []
    while heap:
        _, r = heapq.heappop(heap)
        sorted_repos.append(r)
        for successor in sorted(adj.get(r, set())):
            in_degree[successor] -= 1
            if in_degree[successor] == 0:
                heapq.heappush(heap, (-repo_alta.get(successor, 0), successor))

    # repos em ciclo (não alcançados) — adiciona no final por carga desc
    remaining = sorted(
        [r for r in repos if r not in sorted_repos],
        key=lambda r: (-repo_alta.get(r, 0), -len(repos[r]))
    )
    sorted_repos.extend(remaining)

    # --- Monta resultado ---
    result = []
    for modulo_step, repo in enumerate(sorted_repos, start=1):
        itens = repos[repo]
        areas_no_repo = sorted(repo_areas[repo], key=lambda a: priority.get(a, 999))
        areas_detalhes = []
        for area in areas_no_repo:
            area_itens = [m for m in itens if m["area"] == area]
            areas_detalhes.append({
                "area": area,
                "total_impactos": len(area_itens),
                "impactos_alta_complexidade": sum(1 for m in area_itens if m["complexidade"] == "Alta"),
                "requerem_compatibilidade_dual": sum(1 for m in area_itens if m["requer_compatibilidade_dual"]),
                "rationale": _AREA_RATIONALE.get(area, ""),
            })
        predecessores_no_escopo = sorted(deps.get(repo, set()) & repos.keys())
        result.append({
            "passo": modulo_step,
            "modulo": repo,
            "total_impactos": len(itens),
            "impactos_alta_complexidade": repo_alta[repo],
            "requerem_compatibilidade_dual": sum(1 for m in itens if m["requer_compatibilidade_dual"]),
            "depende_de": predecessores_no_escopo,
            "areas": areas_detalhes,
        })
    return result


def _build_gargalos(matriz: list[dict], ordem_migracao: list[dict]) -> list[dict]:
    """
    Detecta repos que participam de muitos fluxos distintos.
    Um atraso nesses repos atrasa proporcionalmente a migração inteira.
    Limiar: participa em >= 3 fluxos distintos OU >= 30% do total de fluxos.
    """
    from collections import defaultdict
    repo_fluxos: dict[str, set] = defaultdict(set)
    for m in matriz:
        f = m.get("fluxo")
        if f:
            repo_fluxos[m["repositorio"]].add(f)

    total_fluxos = len({m.get("fluxo") for m in matriz if m.get("fluxo")})
    if total_fluxos == 0:
        return []

    passo_map = {s["modulo"]: s["passo"] for s in ordem_migracao}
    alta_map  = {s["modulo"]: s["impactos_alta_complexidade"] for s in ordem_migracao}

    gargalos = []
    for repo, fluxos in repo_fluxos.items():
        n = len(fluxos)
        pct = n / total_fluxos
        if n < 3 and pct < 0.30:
            continue
        if pct >= 0.60 or n >= 10:
            nivel = "Crítico"
        elif pct >= 0.40 or n >= 6:
            nivel = "Alto"
        else:
            nivel = "Médio"
        gargalos.append({
            "repositorio": repo,
            "n_fluxos": n,
            "pct_fluxos": round(pct * 100),
            "fluxos": sorted(fluxos),
            "nivel": nivel,
            "passo_migracao": passo_map.get(repo),
            "impactos_alta": alta_map.get(repo, 0),
            "alerta": f"Atraso neste repo impacta {n} fluxo(s) ({round(pct*100)}% do total).",
        })

    gargalos.sort(key=lambda x: (-x["n_fluxos"], -x["impactos_alta"]))
    return gargalos


# Domínios críticos: se apenas 1 repo cobre o domínio, ele é SPOF
_DOMINIOS_CRITICOS: list[tuple[str, list[str]]] = [
    ("Auth/IAM",        ["auth", "iam", "identity", "login", "oauth", "sso", "keycloak", "autenticacao"]),
    ("PIX",             ["pix"]),
    ("Conta Digital",   ["conta", "account", "contadigital"]),
    ("Cartão",          ["cartao", "card", "cartoes"]),
    ("Crédito/CCB",     ["credito", "ccb", "emprestimo", "loan"]),
    ("Onboarding PJ",   ["onboarding", "aberturaconta", "pessoajuridica", "pj-onboard"]),
    ("Pagamentos",      ["pagamento", "payment", "boleto", "ted", "cobranca"]),
    ("Fiscal/SPED",     ["sped", "nfse", "fiscal", "reinf", "esocial"]),
    ("Integrações Core",["gateway", "integration", "integracao", "broker", "middleware"]),
    ("Banco de Dados Core", ["schema", "migration", "flyway", "liquibase", "db-core"]),
]


def _build_spof(matriz: list[dict], ordem_migracao: list[dict]) -> list[dict]:
    """
    Detecta repos que são o único representante de um domínio crítico.
    Se esse repo atrasar, nenhum outro pode cobrir o domínio.
    """
    from collections import defaultdict

    passo_map = {s["modulo"]: s["passo"] for s in ordem_migracao}
    alta_map  = {s["modulo"]: s["impactos_alta_complexidade"] for s in ordem_migracao}
    repos_com_impacto = {m["repositorio"] for m in matriz}

    resultado: list[dict] = []
    for dominio, keywords in _DOMINIOS_CRITICOS:
        # repos com impacto cujo nome contém alguma keyword do domínio
        matches = [
            r for r in repos_com_impacto
            if any(kw in r.lower().replace("-", "").replace("_", "") for kw in keywords)
        ]
        if len(matches) == 1:
            repo = matches[0]
            resultado.append({
                "repositorio": repo,
                "dominio": dominio,
                "motivo": f"Único repo com impacto no domínio '{dominio}'. Sem substituto se atrasar.",
                "passo_migracao": passo_map.get(repo),
                "impactos_alta": alta_map.get(repo, 0),
                "alerta": f"SPOF: atraso em '{repo}' bloqueia todo o domínio {dominio}.",
            })

    resultado.sort(key=lambda x: (-x["impactos_alta"], x["dominio"]))
    return resultado


def _build_heatmap_risco(ordem_migracao: list[dict], gargalos: list[dict],
                         spof: list[dict], trilhas: dict) -> list[dict]:
    """
    Mapa de calor de risco por sprint (passo de migração).
    Score composto: impactos Alta + SPOFs + gargalos (ponderados) + fluxos partidos.
    """
    if not ordem_migracao:
        return []
    gargalo_por_repo = {g["repositorio"]: g for g in gargalos}
    spof_repos       = {s["repositorio"] for s in spof}
    _NIVEL_PESO      = {"Médio": 1, "Alto": 2, "Crítico": 3}
    partidos_repos: set[str] = set()
    for fp in (trilhas or {}).get("fluxos_partidos", []):
        partidos_repos.update(fp.get("repositorios", []))

    sprints: list[dict] = []
    for s in ordem_migracao:
        repo  = s["modulo"]
        alta  = s["impactos_alta_complexidade"]
        score = alta * 2
        fatores: list[str] = []
        if repo in spof_repos:
            score += 5
            fatores.append("SPOF")
        g = gargalo_por_repo.get(repo)
        if g:
            score += 3 * _NIVEL_PESO.get(g["nivel"], 1)
            fatores.append(f"Gargalo {g['nivel']}")
        if repo in partidos_repos:
            score += 4
            fatores.append("Fluxo partido")
        sprints.append({"passo": s["passo"], "modulo": repo,
                        "score": score, "impactos_alta": alta, "fatores": fatores})

    max_score = max(s["score"] for s in sprints) or 1
    for s in sprints:
        s["score_normalizado"] = round(s["score"] / max_score * 100)
        raw = s["score_normalizado"]
        s["nivel_risco"] = "Crítico" if raw >= 75 else "Alto" if raw >= 50 else "Médio" if raw >= 25 else "Baixo"
    return sprints


# Critérios de aceite por área — o que deve ser verdadeiro para considerar a área migrada
_CRITERIOS_AREA: dict[str, list[str]] = {
    "Banco de Dados": [
        "Todas as colunas CNPJ têm tipo VARCHAR/CHAR com tamanho ≥ 20.",
        "Nenhuma constraint CHECK limita o campo a 14 caracteres numéricos.",
        "Scripts Flyway/Liquibase aplicados com sucesso em DEV, QA e HML.",
        "Índices recriados após alteração de tipo de coluna.",
        "Rollback da migration testado e documentado.",
    ],
    "API/Contrato": [
        "Contrato OpenAPI/Swagger atualizado: pattern aceita [A-Z0-9]{14,20}.",
        "maxLength ≥ 20 em todos os campos CNPJ do schema.",
        "Rota /v1 mantida ativa durante período de convivência dual.",
        "Contract tests passando para CNPJ numérico e alfanumérico.",
        "Consumidores notificados e confirmaram compatibilidade.",
    ],
    "Backend": [
        "Nenhuma ocorrência de regex \\d{14} para validação de CNPJ.",
        "Nenhuma chamada a Long.parseLong / Integer.parseInt com CNPJ.",
        "Nenhum substring/slice posicional sem uso de utilitário CnpjUtils.",
        "Validador de dígito verificador alfanumérico coberto por testes unitários.",
        "Testes unitários passando com CNPJ alfanumérico (ex: 12ABC34500DE35).",
    ],
    "Frontend": [
        "Campo CNPJ aceita entrada de letras maiúsculas (A-Z).",
        "Máscara atualizada para formato alfanumérico.",
        "inputMode='text' em todos os campos CNPJ.",
        "Testes E2E passando com CNPJ alfanumérico.",
        "CNPJ numérico antigo continua funcionando (regressão).",
    ],
    "Integrações": [
        "Parceiros externos confirmaram suporte ao novo formato.",
        "Adapter de conversão numérico↔alfanumérico implementado e testado.",
        "Logs de integração monitorados: zero rejeições por formato de CNPJ.",
        "Testes de integração passando com CNPJ alfanumérico.",
    ],
    "Processamento/Batch": [
        "Jobs processam CNPJ alfanumérico sem descartar registros.",
        "Alertas configurados para registros rejeitados por validação de CNPJ.",
        "Layout de arquivo atualizado: campo CNPJ com tamanho ≥ 20.",
        "Reprocessamento de registros históricos testado.",
    ],
    "Segurança/LGPD": [
        "Nenhum CNPJ real hardcoded no código (git history auditado).",
        "Secrets rotacionados após remoção de dados sensíveis.",
        "Massa de testes usa CNPJs sintéticos ou variáveis de ambiente.",
    ],
    "Infraestrutura/CI": [
        "Nenhum CNPJ hardcoded em Dockerfile, docker-compose ou Jenkinsfile.",
        "Secrets de CI atualizados e pipeline executado com sucesso.",
        "Imagens Docker antigas tagueadas para rollback rápido.",
    ],
    "Configuração": [
        "Nenhum CNPJ fixo em application.yml, .env ou properties.",
        "Variáveis de ambiente documentadas e configuradas em todos os ambientes.",
    ],
    "Testes/Qualidade": [
        "Fixtures e seeds atualizados com CNPJs alfanuméricos sintéticos.",
        "Cobertura de testes inclui cenários com CNPJ alfanumérico e numérico.",
        "Nenhum teste falhando por formato de CNPJ.",
    ],
    "Documentação": [
        "README e docs atualizados com exemplos de CNPJ alfanumérico.",
        "Nenhum exemplo de CNPJ exclusivamente numérico em documentação pública.",
    ],
    "Pessoa Jurídica/PJ": [
        "Entidades e DTOs de Empresa/PJ aceitam CNPJ alfanumérico.",
        "Fluxo de onboarding PJ testado com CNPJ alfanumérico.",
        "Templates de documentos PJ (contrato social, procuração, ficha cadastral) validados.",
        "Campos de Inscrição Estadual e NIRE não bloqueiam CNPJ alfanumérico.",
    ],
}

# Critério genérico de encerramento (aplicado a todos os módulos)
_CRITERIOS_ENCERRAMENTO = [
    "Scanner executado no repositório após a migração: zero ocorrências de impacto.",
    "Code review aprovado pelo Tech Lead.",
    "Deploy realizado em DEV, QA e HML sem erros.",
    "Homologação validada pelo PO/QA com CNPJ alfanumérico.",
]


# Esforço estimado em dias por impacto, por área e complexidade
# Fonte: heurística baseada em complexidade técnica típica de cada área
_ESFORCO_DIAS: dict[str, dict[str, float]] = {
    "Banco de Dados":      {"Alta": 3.0, "Média": 1.5, "Baixa": 0.5},
    "API/Contrato":        {"Alta": 2.5, "Média": 1.0, "Baixa": 0.5},
    "Backend":             {"Alta": 2.0, "Média": 1.0, "Baixa": 0.5},
    "Frontend":            {"Alta": 1.5, "Média": 0.5, "Baixa": 0.25},
    "Integrações":         {"Alta": 3.0, "Média": 1.5, "Baixa": 0.5},
    "Processamento/Batch": {"Alta": 2.5, "Média": 1.0, "Baixa": 0.5},
    "Segurança/LGPD":      {"Alta": 2.0, "Média": 1.0, "Baixa": 0.5},
    "Infraestrutura/CI":   {"Alta": 1.5, "Média": 0.5, "Baixa": 0.25},
    "Configuração":        {"Alta": 1.0, "Média": 0.5, "Baixa": 0.25},
    "Testes/Qualidade":    {"Alta": 1.5, "Média": 0.5, "Baixa": 0.25},
    "Documentação":        {"Alta": 0.5, "Média": 0.25, "Baixa": 0.25},
    "Pessoa Jurídica/PJ":  {"Alta": 2.0, "Média": 1.0, "Baixa": 0.5},
}
# Overhead fixo por módulo: code review + deploy + testes de regressão
_OVERHEAD_MODULO_DIAS = 2.0
# Fator adicional por compatibilidade dual (período de convivência)
_FATOR_DUAL = 1.3


def _build_esforco(ordem_migracao: list[dict], matriz: list[dict]) -> list[dict]:
    """
    Estima esforço em dias por módulo com base nos impactos detectados.
    Fórmula: Σ(dias_por_impacto × fator_dual) + overhead_fixo.
    Story points = ceil(dias / 0.5) — escala Fibonacci aproximada.
    """
    import math
    from collections import defaultdict

    # índice rápido: repo → lista de impactos
    repo_impactos: dict[str, list] = defaultdict(list)
    for m in matriz:
        repo_impactos[m["repositorio"]].append(m)

    resultado = []
    for s in ordem_migracao:
        repo   = s["modulo"]
        itens  = repo_impactos.get(repo, [])
        dias_base = 0.0
        por_area: dict[str, dict] = {}

        for m in itens:
            area  = m["area"]
            compl = m["complexidade"]
            d = _ESFORCO_DIAS.get(area, {"Alta": 2.0, "Média": 1.0, "Baixa": 0.5}).get(compl, 1.0)
            if m.get("requer_compatibilidade_dual"):
                d *= _FATOR_DUAL
            dias_base += d
            if area not in por_area:
                por_area[area] = {"dias": 0.0, "impactos": 0}
            por_area[area]["dias"] += d
            por_area[area]["impactos"] += 1

        dias_total = round(dias_base + _OVERHEAD_MODULO_DIAS, 1)
        # Story points: escala Fibonacci (1,2,3,5,8,13,21,34)
        _FIB = [1, 2, 3, 5, 8, 13, 21, 34]
        sp_raw = math.ceil(dias_total / 0.5)
        story_points = next((f for f in _FIB if f >= sp_raw), _FIB[-1])

        resultado.append({
            "passo": s["passo"],
            "modulo": repo,
            "dias_estimados": dias_total,
            "story_points": story_points,
            "overhead_dias": _OVERHEAD_MODULO_DIAS,
            "requer_dual": s["requerem_compatibilidade_dual"] > 0,
            "esforco_por_area": [
                {"area": a, "dias": round(v["dias"], 1), "impactos": v["impactos"]}
                for a, v in sorted(por_area.items(), key=lambda x: -x[1]["dias"])
            ],
        })
    return resultado


def _build_criterios_aceite(matriz: list[dict], ordem_migracao: list[dict]) -> list[dict]:
    """
    Gera critérios de aceite por módulo (repositório), agrupados por área.
    Cada módulo recebe os critérios das áreas que têm impacto nele,
    mais os critérios genéricos de encerramento.
    """
    resultado = []
    for s in ordem_migracao:
        repo = s["modulo"]
        areas_do_repo = [a["area"] for a in s["areas"]]
        criterios_por_area = [
            {
                "area": area,
                "criterios": _CRITERIOS_AREA.get(area, []),
            }
            for area in areas_do_repo
            if _CRITERIOS_AREA.get(area)
        ]
        resultado.append({
            "passo": s["passo"],
            "modulo": repo,
            "criterios_por_area": criterios_por_area,
            "criterios_encerramento": _CRITERIOS_ENCERRAMENTO,
        })
    return resultado


def build_diff(scan_anterior: dict, scan_atual: dict) -> dict:
    """
    Compara dois scans e classifica cada impacto como:
    - novo: presente no atual, ausente no anterior
    - resolvido: presente no anterior, ausente no atual
    - alterado: presente em ambos mas com complexidade ou área diferente
    - mantido: idêntico em ambos
    Chave estável: repositorio:arquivo:linha
    """
    def _idx(scan: dict) -> dict[str, dict]:
        return {
            f"{m['repositorio']}:{m['evidencia']['arquivo']}:{m['evidencia']['linha']}": m
            for m in scan.get("matriz_impacto", [])
        }

    ant = _idx(scan_anterior)
    atu = _idx(scan_atual)
    todas_chaves = set(ant) | set(atu)

    novos, resolvidos, alterados, mantidos = [], [], [], []
    for chave in sorted(todas_chaves):
        em_ant = chave in ant
        em_atu = chave in atu
        if em_atu and not em_ant:
            novos.append({**atu[chave], "_diff": "novo"})
        elif em_ant and not em_atu:
            resolvidos.append({**ant[chave], "_diff": "resolvido"})
        else:
            m_ant, m_atu = ant[chave], atu[chave]
            if m_ant["complexidade"] != m_atu["complexidade"] or m_ant["area"] != m_atu["area"]:
                alterados.append({
                    **m_atu, "_diff": "alterado",
                    "_anterior": {"complexidade": m_ant["complexidade"], "area": m_ant["area"]},
                })
            else:
                mantidos.append({**m_atu, "_diff": "mantido"})

    scan_id_ant = scan_anterior.get("scan_id", "anterior")
    scan_id_atu = scan_atual.get("scan_id", "atual")
    return {
        "scan_id_anterior": scan_id_ant,
        "scan_id_atual": scan_id_atu,
        "data_anterior": scan_anterior.get("data_execucao", ""),
        "data_atual": scan_atual.get("data_execucao", ""),
        "resumo": {
            "novos": len(novos),
            "resolvidos": len(resolvidos),
            "alterados": len(alterados),
            "mantidos": len(mantidos),
            "total_anterior": len(ant),
            "total_atual": len(atu),
            "delta": len(atu) - len(ant),
        },
        "novos": novos,
        "resolvidos": resolvidos,
        "alterados": alterados,
    }


def _build_risk_score(ordem_migracao: list[dict], gargalos: list[dict],
                      spof: list[dict], trilhas: dict, matriz: list[dict]) -> list[dict]:
    """
    Risk Score por módulo: score composto 0–100 com breakdown de fatores.
    Fórmula:
      base  = impactos_alta × 3 + impactos_media × 1
      +10   por SPOF
      +8    por Gargalo Crítico / +5 Alto / +3 Médio
      +6    por fluxo partido (por fluxo)
      +4    por requer_compatibilidade_dual
      +2    por dependências (depende_de não vazio)
    Normalizado 0–100 sobre o máximo do conjunto.
    """
    _NIVEL_PESO = {"Crítico": 8, "Alto": 5, "Médio": 3}
    gargalo_map = {g["repositorio"]: g for g in gargalos}
    spof_repos  = {s["repositorio"] for s in spof}
    partidos_map: dict[str, int] = {}  # repo → n fluxos partidos
    for fp in (trilhas or {}).get("fluxos_partidos", []):
        for r in fp.get("repositorios", []):
            partidos_map[r] = partidos_map.get(r, 0) + 1

    # índice rápido: repo → impactos
    from collections import defaultdict
    repo_imp: dict[str, list] = defaultdict(list)
    for m in matriz:
        repo_imp[m["repositorio"]].append(m)

    scores = []
    for s in ordem_migracao:
        repo  = s["modulo"]
        itens = repo_imp.get(repo, [])
        alta  = s["impactos_alta_complexidade"]
        media = sum(1 for m in itens if m["complexidade"] == "Média")
        dual  = s["requerem_compatibilidade_dual"]
        deps  = len(s.get("depende_de", []))

        raw = alta * 3 + media * 1
        fatores: list[dict] = [
            {"fator": "Impactos Alta",  "pontos": alta * 3,  "detalhe": f"{alta} × 3"},
            {"fator": "Impactos Média", "pontos": media * 1, "detalhe": f"{media} × 1"},
        ]

        if repo in spof_repos:
            raw += 10
            fatores.append({"fator": "SPOF", "pontos": 10, "detalhe": "Único repo no domínio"})

        g = gargalo_map.get(repo)
        if g:
            pts = _NIVEL_PESO.get(g["nivel"], 3)
            raw += pts
            fatores.append({"fator": f"Gargalo {g['nivel']}", "pontos": pts,
                            "detalhe": f"{g['n_fluxos']} fluxos ({g['pct_fluxos']}%)"})

        n_partidos = partidos_map.get(repo, 0)
        if n_partidos:
            pts = n_partidos * 6
            raw += pts
            fatores.append({"fator": "Fluxos partidos", "pontos": pts,
                            "detalhe": f"{n_partidos} fluxo(s) partido(s)"})

        if dual:
            raw += 4
            fatores.append({"fator": "Compatibilidade dual", "pontos": 4,
                            "detalhe": f"{dual} impacto(s) dual"})

        if deps:
            raw += 2
            fatores.append({"fator": "Dependências", "pontos": 2,
                            "detalhe": f"{deps} dependência(s)"})

        scores.append({
            "passo": s["passo"],
            "modulo": repo,
            "score_raw": raw,
            "fatores": [f for f in fatores if f["pontos"] > 0],
        })

    max_raw = max((s["score_raw"] for s in scores), default=1) or 1
    for s in scores:
        s["score"] = round(s["score_raw"] / max_raw * 100)
        raw = s["score"]
        s["nivel"] = "Crítico" if raw >= 75 else "Alto" if raw >= 50 else "Médio" if raw >= 25 else "Baixo"
    return scores


def _build_sugestoes_movimentacao(trilhas: dict, ordem_migracao: list[dict]) -> list[dict]:
    """
    Sugere movimentações de repos entre trilhas para reduzir fluxos partidos.
    Para cada fluxo partido, identifica o repo de menor carga que pode ser movido
    para a trilha que já concentra a maioria dos repos do fluxo.
    """
    if not trilhas:
        return []
    partidos = trilhas.get("fluxos_partidos", [])
    if not partidos:
        return []

    # mapa repo → trilha atual (1-based)
    repo_trilha: dict[str, int] = {}
    carga_trilha: dict[int, int] = {}
    for t in trilhas.get("trilhas", []):
        tid = t["trilha"]
        carga_trilha[tid] = t["carga_alta"]
        for r in t["repositorios"]:
            repo_trilha[r["modulo"]] = tid

    alta_map = {s["modulo"]: s["impactos_alta_complexidade"] for s in ordem_migracao}

    sugestoes = []
    for fp in partidos:
        if fp.get("gravidade") not in ("Alto", "Crítico"):
            continue  # só sugere para fluxos de alto impacto
        repos_fluxo = fp["repositorios"]
        # conta repos por trilha neste fluxo
        from collections import Counter
        contagem = Counter(repo_trilha.get(r) for r in repos_fluxo if repo_trilha.get(r))
        if len(contagem) < 2:
            continue
        trilha_destino = contagem.most_common(1)[0][0]  # trilha com mais repos do fluxo
        # repos que estão em outras trilhas
        candidatos = [
            r for r in repos_fluxo
            if repo_trilha.get(r) and repo_trilha[r] != trilha_destino
        ]
        if not candidatos:
            continue
        # escolhe o de menor carga para mover
        repo_mover = min(candidatos, key=lambda r: alta_map.get(r, 0))
        trilha_origem = repo_trilha[repo_mover]
        delta_carga = alta_map.get(repo_mover, 0)
        nova_carga_origem  = carga_trilha.get(trilha_origem, 0) - delta_carga
        nova_carga_destino = carga_trilha.get(trilha_destino, 0) + delta_carga
        sugestoes.append({
            "fluxo": fp["fluxo"],
            "gravidade": fp["gravidade"],
            "repo": repo_mover,
            "de_trilha": trilha_origem,
            "para_trilha": trilha_destino,
            "impactos_alta_repo": delta_carga,
            "nova_carga_trilha_origem": nova_carga_origem,
            "nova_carga_trilha_destino": nova_carga_destino,
            "justificativa": (
                f"Mover '{repo_mover}' da Trilha {trilha_origem} para a Trilha {trilha_destino} "
                f"consolida o fluxo '{fp['fluxo']}' em uma única trilha, "
                f"eliminando necessidade de sincronização entre equipes."
            ),
        })
    return sugestoes


def _build_oportunidades_refatoracao(matriz: list[dict], ordem_migracao: list[dict]) -> list[dict]:
    """
    Detecta padrões recorrentes que indicam oportunidades de refatoração:
    1. Mesmo padrão de impacto em >= 3 repos → extrair utilitário compartilhado
    2. Mesmo arquivo com >= 4 impactos distintos → God Object / classe com muitas responsabilidades
    3. Área Backend com >= 5 impactos de substring/slice → extrair CnpjUtils
    4. Área Frontend com >= 3 repos com máscara → extrair componente compartilhado
    """
    from collections import defaultdict, Counter
    oportunidades: list[dict] = []

    # 1. Padrão recorrente entre repos (mesma regra em >= 3 repos)
    regra_repos: dict[str, set] = defaultdict(set)
    for m in matriz:
        obs = m.get("observacoes", "")
        # extrai ID da regra do campo observacoes ("Regra: BE-001 | ...")
        if "Regra:" in obs:
            regra_id = obs.split("Regra:")[1].split("|")[0].strip()
            regra_repos[regra_id].add(m["repositorio"])

    for regra, repos in regra_repos.items():
        if len(repos) >= 3:
            oportunidades.append({
                "tipo": "Utilitário compartilhado",
                "regra": regra,
                "repositorios": sorted(repos),
                "n_repos": len(repos),
                "descricao": (
                    f"Regra {regra} detectada em {len(repos)} repositórios. "
                    f"Considere extrair a lógica para uma lib compartilhada (ex: cnpj-utils-lib) "
                    f"para centralizar a correção e evitar retrabalho."
                ),
                "acao": f"Criar lib compartilhada com utilitário CNPJ e publicar como dependência Maven/npm.",
            })

    # 2. God Object: arquivo com >= 4 impactos distintos
    arquivo_impactos: dict[tuple, list] = defaultdict(list)
    for m in matriz:
        key = (m["repositorio"], m["componente"])
        arquivo_impactos[key].append(m)

    for (repo, arquivo), itens in arquivo_impactos.items():
        if len(itens) >= 4:
            areas = sorted({m["area"] for m in itens})
            oportunidades.append({
                "tipo": "God Object / Alta coesão",
                "regra": "—",
                "repositorios": [repo],
                "n_repos": 1,
                "descricao": (
                    f"'{arquivo.split('/')[-1]}' em '{repo}' tem {len(itens)} impactos em {len(areas)} área(s): "
                    + ", ".join(areas) + ". "
                    f"Arquivo com muitas responsabilidades — candidato a refatoração."
                ),
                "acao": f"Dividir '{arquivo.split('/')[-1]}' em classes menores por responsabilidade (SRP).",
            })

    # 3. Substring/slice recorrente → extrair CnpjUtils
    substr_repos = {
        m["repositorio"] for m in matriz
        if m["area"] == "Backend" and "substring" in m.get("observacoes", "").lower()
    }
    if len(substr_repos) >= 2:
        oportunidades.append({
            "tipo": "Extrair CnpjUtils",
            "regra": "STR-001",
            "repositorios": sorted(substr_repos),
            "n_repos": len(substr_repos),
            "descricao": (
                f"Manipulação posicional de CNPJ (substring/slice) detectada em {len(substr_repos)} repos. "
                f"Extrair CnpjUtils.getRaiz(), getFilial(), getDv() para lib compartilhada."
            ),
            "acao": "Criar CnpjUtils na lib compartilhada com métodos getRaiz, getFilial, getDv, isValid.",
        })

    # 4. Máscara Frontend em >= 2 repos → extrair componente
    fe_repos = {
        m["repositorio"] for m in matriz
        if m["area"] == "Frontend"
    }
    if len(fe_repos) >= 2:
        oportunidades.append({
            "tipo": "Componente de Input compartilhado",
            "regra": "FE-001",
            "repositorios": sorted(fe_repos),
            "n_repos": len(fe_repos),
            "descricao": (
                f"Máscaras/validações de CNPJ no Frontend detectadas em {len(fe_repos)} repos. "
                f"Extrair <CnpjInput> como componente compartilhado no design system."
            ),
            "acao": "Publicar componente <CnpjInput> no bscash-uikit com suporte a alfanumérico.",
        })

    # ordena: utilitário compartilhado primeiro (mais repos = mais impacto)
    oportunidades.sort(key=lambda x: (-x["n_repos"], x["tipo"]))
    return oportunidades


def _build_checklist_rollback(matriz: list[dict]) -> dict:
    result = {}
    for area in sorted({m["area"] for m in matriz}):
        result[area] = _ROLLBACK_BASE + _ROLLBACK_AREA.get(area, [])
    return result


def _build_impacto_dados(matriz: list[dict]) -> dict:
    areas = {m["area"] for m in matriz}
    return {
        area: {
            "descricao": "Queries sugeridas para estimar volume de registros afetados. Substitua <tabela> e <coluna_cnpj> pelos nomes reais.",
            "queries": queries,
        }
        for area, queries in _SQL_QUERIES.items()
        if area in areas
    }


def _build_riscos(matriz: list[dict]) -> list[dict]:
    areas = {m["area"] for m in matriz}
    return [v for k, v in _RISCOS_AREA.items() if k in areas]


def _build_pendencias(matriz: list[dict]) -> list[dict]:
    pendencias = []
    idx = 1

    def add(desc, resp, prazo="A definir"):
        nonlocal idx
        pendencias.append({"id": f"PND-{idx:03d}", "descricao": desc, "responsavel": resp, "prazo_estimado": prazo})
        idx += 1

    repos_lgpd = sorted({m["repositorio"] for m in matriz if m["area"] == "Segurança/LGPD"})
    if repos_lgpd:
        add(f"CNPJs reais hardcoded (LGPD). Auditar git history. Repos: {', '.join(repos_lgpd)}",
            "Time de Segurança / DPO", "Imediato")

    substr = [m for m in matriz if m["area"] == "Backend" and "substring" in m.get("observacoes", "").lower()]
    if substr:
        add(f"{len(substr)} ocorrência(s) de manipulação posicional (substring/slice). Revisar lógica de raiz do CNPJ.",
            "Time de Engenharia / Backend")

    alta = [m for m in matriz if m["complexidade"] == "Alta"]
    if alta:
        add(f"{len(alta)} componente(s) de alta complexidade. Revisar validadores de DV e anotações JPA.",
            "Time de Engenharia / Backend")

    for area, resp in [
        ("Configuração",        "Time de Engenharia / DevOps"),
        ("Infraestrutura/CI",   "Time de DevOps"),
        ("Integrações",         "Time de Integrações / Parcerias"),
        ("Processamento/Batch", "Time de Engenharia / Fiscal"),
        ("Documentação",        "Time de Engenharia / Tech Writer"),
    ]:
        repos = sorted({m["repositorio"] for m in matriz if m["area"] == area})
        if repos:
            add(f"[{area}] Revisar impactos em: {', '.join(repos)}", resp)

    for repo in sorted({m["repositorio"] for m in matriz if m["area"] == "Frontend"}):
        add(f"Validar libs de terceiros em '{repo}' quanto ao suporte CNPJ alfanumérico.",
            "Time de Engenharia / Frontend")

    return pendencias


# ---------------------------------------------------------------------------
# build_output
# ---------------------------------------------------------------------------

_PONTOS_CEGOS = [
    {
        "id": "PC-001",
        "descricao": "Campos que não usam a palavra 'cnpj' no nome (ex: 'documento', 'cpfCnpj', 'nr_doc', 'taxId') podem não ser encontrados pela Search API do GitHub. O scanner cobre parcialmente esses casos via: (1) busca por aliases com --scan-aliases, (2) análise estrutural SQL de colunas VARCHAR(14-20) em tabelas com coluna 'cnpj', e (3) padrões de valor (formato XX.XXX.XXX/XXXX-XX) nas regras. Campos com nomes completamente atípicos ainda ficam fora do escopo.",
        "recomendacao": "Usar --scan-aliases para busca ativa por aliases conhecidos. Para cobertura total, executar varredura local: git clone + grep -rE '[0-9]{2}\\.[0-9]{3}\\.[0-9]{3}/[0-9]{4}-[0-9]{2}'."
    },
    {
        "id": "PC-002",
        "descricao": "A Search API do GitHub retorna no máximo 1000 resultados por repositório. Quando esse limite é atingido, o scanner baixa automaticamente todos os arquivos da tree com extensões cobertas pelas regras e confirma a presença de 'cnpj' no conteúdo antes de analisá-los. Repos muito grandes podem ter latência maior nesse modo.",
        "recomendacao": "Observe o log '[tree-full]' durante a execução. Se o repo tiver muitos arquivos grandes, use --include-large-files para garantir cobertura total."
    },
    {
        "id": "PC-003",
        "descricao": "Arquivos maiores que 500KB são ignorados pelo scanner para evitar timeout na API.",
        "recomendacao": "Verificar manualmente arquivos SQL de migração grandes (ex: scripts de carga histórica)."
    },
    {
        "id": "PC-004",
        "descricao": "Linhas que começam com comentário (// /* * #) são descartadas como falso positivo, mesmo que contenham lógica relevante em comentários de documentação.",
        "recomendacao": "Revisar manualmente comentários TODO/FIXME que mencionem CNPJ."
    },
    {
        "id": "PC-005",
        "descricao": "Repositórios sem nenhum impacto registrado podem usar aliases de campo sem a palavra 'cnpj', ou podem genuinamente não processar CNPJ.",
        "recomendacao": "Validar manualmente repos com zero impactos que sejam conhecidamente relacionados a PJ: " + ", ".join([
            "azure-sprint-kanban", "poc-forms", "bscash-uikit", "bscash-teste",
            "example-java-project", "poc-mfa", "poc-forms"
        ]) + "."
    },
    {
        "id": "PC-006",
        "descricao": "Templates de documentos de Pessoa Jurídica (contrato social, procuração, ficha cadastral PJ, NIRE, Inscrição Estadual, comprovante de abertura de conta) podem conter CNPJ em templates de geração de PDF/DOCX/HTML/JRXML que não são cobertos pelas regras de backend. Esses templates podem estar em repositórios de documentação ou em pastas de recursos estáticos.",
        "recomendacao": "Buscar por templates de documentos PJ: grep -rE 'contratoSocial|procuracao|inscricaoEstadual|NIRE|fichaCAD|quadroSocietario' --include='*.html' --include='*.jrxml' --include='*.ftl' --include='*.vm'."
    },
]


def _load_status_anteriores(output_file: str) -> dict:
    """Carrega status/responsavel/observacao do JSON anterior indexado por chave estavel."""
    import os, json
    if not os.path.exists(output_file):
        return {}
    try:
        d = json.load(open(output_file, encoding="utf-8"))
        return {
            f"{m['repositorio']}:{m['evidencia']['arquivo']}:{m['evidencia']['linha']}": {
                "status": m.get("status", "pendente"),
                "responsavel": m.get("responsavel"),
                "observacao": m.get("observacao"),
            }
            for m in d.get("matriz_impacto", [])
        }
    except Exception:
        return {}


def _build_impactos_por_repositorio(matriz: list[dict]) -> dict:
    result: dict[str, dict] = {}
    for m in matriz:
        repo = m["repositorio"]
        if repo not in result:
            result[repo] = {"total": 0, "Alta": 0, "Média": 0, "Baixa": 0, "areas": set()}
        result[repo]["total"] += 1
        result[repo][m["complexidade"]] += 1
        result[repo]["areas"].add(m["area"])
    # Serializa sets e ordena por total desc
    return dict(sorted(
        {k: {**v, "areas": sorted(v["areas"])} for k, v in result.items()}.items(),
        key=lambda x: x[1]["total"],
        reverse=True,
    ))


def build_output(raw_impacts: list[dict], cfg: dict, repos_analisados: list[str], repo_stats: dict | None = None) -> dict:
    from core.engine import requires_dual_compat, dual_compat_motivo
    tz_br = timezone(timedelta(hours=-3))
    status_anteriores = _load_status_anteriores(cfg.get("output_file", "impacto_cnpj.json"))
    matriz = []

    for idx, imp in enumerate(raw_impacts, start=1):
        rule, filepath, match = imp["_rule"], imp["filepath"], imp["match"]
        trecho = match["trecho_codigo"]
        dual = requires_dual_compat(rule["area"], trecho)
        # Chave estavel para preservar status entre execucoes: repo + arquivo + linha
        chave = f"{imp['repositorio']}:{filepath}:{match['linha']}"
        status_anterior = status_anteriores.get(chave, {"status": "pendente", "responsavel": None, "observacao": None})
        matriz.append({
            "id": f"IMP-{idx:04d}",
            "area": rule["area"],
            "repositorio": imp["repositorio"],
            "componente": filepath,
            "descricao_impacto": rule["descricao_impacto"],
            "complexidade": rule["complexidade"],
            "prioridade": _calc_prioridade(rule["complexidade"], imp.get("arquivo_critico", False)),
            "status": status_anterior["status"],
            "responsavel": status_anterior["responsavel"],
            "observacao": status_anterior["observacao"],
            "chamadores_estimados": imp.get("chamadores_estimados", 0),
            "arquivo_critico": imp.get("arquivo_critico", False),
            "requer_compatibilidade_dual": dual,
            "motivo_compatibilidade_dual": dual_compat_motivo(rule["area"], trecho) if dual else None,
            "evidencia": {"arquivo": filepath, "linha": match["linha"], "trecho_codigo": trecho},
            "observacoes": f"Regra: {rule.get('id', rule.get('area', '?'))} | Padrão: {match['pattern_matched']}",
            "fluxo": _inferir_tela(filepath, imp["repositorio"]),
        })

    areas = {}
    for m in matriz:
        areas[m["area"]] = areas.get(m["area"], 0) + 1

    repos_com_impacto = {m["repositorio"] for m in matriz}
    repos_sem_impacto = sorted(set(repos_analisados) - repos_com_impacto)
    ordem_migracao = _build_ordem_migracao(matriz, cfg)
    gargalos        = _build_gargalos(matriz, ordem_migracao)
    spof            = _build_spof(matriz, ordem_migracao)
    trilhas         = _build_trilhas(ordem_migracao, cfg, matriz)

    now = datetime.now(tz_br)
    return {
        "spec_versao": "1.2",
        "versao_regras": cfg.get("versao_regras", "scanner-config.json"),
        "scan_id": now.strftime("%Y%m%d_%H%M%S"),
        "data_execucao": now.isoformat(),
        "data_limite_migracao": cfg.get("data_limite_migracao", None),
        "sistema_escopo": cfg["sistema_escopo"],
        "estatisticas": {
            "total_repositorios_analisados": len(repos_analisados),
            "total_repositorios_com_impacto": len(repos_com_impacto),
            "total_repositorios_sem_impacto": len(repos_sem_impacto),
            "total_impactos_encontrados": len(matriz),
            "impactos_por_area": areas,
            "impactos_por_complexidade": {
                "Alta":  sum(1 for m in matriz if m["complexidade"] == "Alta"),
                "Média": sum(1 for m in matriz if m["complexidade"] == "Média"),
                "Baixa": sum(1 for m in matriz if m["complexidade"] == "Baixa"),
            },
            "impactos_por_repositorio": _build_impactos_por_repositorio(matriz),
            "candidatos_por_repositorio": repo_stats or {},
            "chamadores_criticos_total": sum(m["chamadores_estimados"] for m in matriz if m["arquivo_critico"]),
            "requerem_compatibilidade_dual": sum(1 for m in matriz if m["requer_compatibilidade_dual"]),
            "arquivos_criticos": sum(1 for m in matriz if m["arquivo_critico"]),
            "progresso": {
                "pendente":    sum(1 for m in matriz if m["status"] == "pendente"),
                "em_progresso": sum(1 for m in matriz if m["status"] == "em_progresso"),
                "resolvido":   sum(1 for m in matriz if m["status"] == "resolvido"),
                "falso_positivo": sum(1 for m in matriz if m["status"] == "falso_positivo"),
            },
        },
        "cobertura": {
            "repositorios_sem_impacto": repos_sem_impacto,
            "repos_sem_impacto_com_aliases": {},
            "pontos_cegos": _PONTOS_CEGOS,
        },
        "repositorios_analisados": repos_analisados,
        "matriz_impacto": matriz,
        "ordem_migracao": ordem_migracao,
        "arquivos_criticos": _build_arquivos_criticos(matriz),
        "checklist_rollback": _build_checklist_rollback(matriz),
        "impacto_dados": _build_impacto_dados(matriz),
        "riscos_mapeados": _build_riscos(matriz),
        "parceiros_externos": _build_parceiros_externos(matriz),
        "pendencias_identificadas": _build_pendencias(matriz),
        "telas_qa": _build_telas_qa(matriz),
        "trilhas": trilhas,
        "gargalos": gargalos,
        "spof": spof,
        "heatmap_risco": _build_heatmap_risco(ordem_migracao, gargalos, spof, trilhas),
        "criterios_aceite": _build_criterios_aceite(matriz, ordem_migracao),
        "esforco": _build_esforco(ordem_migracao, matriz),
        "risk_score": _build_risk_score(ordem_migracao, gargalos, spof, trilhas, matriz),
        "sugestoes_movimentacao": _build_sugestoes_movimentacao(trilhas, ordem_migracao),
        "oportunidades_refatoracao": _build_oportunidades_refatoracao(matriz, ordem_migracao),
    }


def _calc_prioridade(complexidade: str, critico: bool) -> str:
    if critico or complexidade == "Alta":
        return "P1"
    if complexidade == "Média":
        return "P2"
    return "P3"


# ---------------------------------------------------------------------------
# Mapeamento de telas para QA  (deve ficar antes de generate_markdown)
# ---------------------------------------------------------------------------

# Palavras-chave no caminho do arquivo → nome funcional da tela/fluxo
_TELA_KEYWORDS: list[tuple[list[str], str]] = [
    # Mobile / React Native
    (["adesao", "onboarding", "cadastro", "aberturaconta", "pessoajuridica", "pj"], "Abertura de Conta / Onboarding PJ"),
    (["pix"],                                        "PIX (chave, transferência, favorito)"),
    (["ted", "transferencia", "transfer"],           "TED / Transferência"),
    (["boleto", "cobranca", "cobrancaterceiro"],     "Boleto / Cobrança"),
    (["cartao", "card"],                             "Cartão"),
    (["ccb", "credito", "negociacao"],               "Crédito / CCB / Negociação"),
    (["saque", "saqueDigital"],                      "Saque Digital"),
    (["holerite", "remuneracao", "salario"],         "Holerite / Remuneracao"),
    (["darf"],                                       "Pagamento DARF"),
    (["nfse", "notafiscal", "nota_fiscal"],          "Emissão NFS-e"),
    (["relatorio", "report", "orcamento"],           "Relatórios / Impressão"),
    (["comprovante"],                                "Comprovante de Transação"),
    (["recibo"],                                     "Recibo"),
    (["ficha", "inscricao"],                         "Ficha de Inscrição"),
    (["lotacao"],                                    "Lotação / Importação de Arquivo"),
    (["contrato", "validacaoWS", "contratoValidacao"], "Validação de Contrato"),
    (["cadastrounico", "cadastro_unico"],            "Cadastro Único"),
    (["backgroundcheck", "background_check"],        "Background Check / Antifraude"),
    (["beneficio", "beneficios"],                    "Benefícios"),
    (["odontoprev", "saudedental"],                  "Saúde Dental / Odontoprev"),
    (["portal", "portalcliente"],                    "Portal do Cliente"),
    (["atendimento", "centralatendimento"],          "Central de Atendimento"),
    (["intermediacao", "remuneracao"],               "Intermediação / Remuneração"),
    (["conta", "contadigital"],                      "Conta Digital"),
    (["banco", "remessa", "febraban", "cnab"],       "Remessa Bancária / CNAB"),
    (["contratosocial", "procuracao", "inscricaoestadual", "fichaCAD", "nire", "quadrosocietario"], "Documentação PJ (Contrato Social / Procuração)"),
    (["input", "form", "mask", "mascara"],           "Componente de Input / Máscara CNPJ"),
    (["validacao", "validation", "validator"],       "Validação de CNPJ (shared)"),
    (["mascarautil", "mascarautil", "documentutils"], "Utilitário de Máscara/Documento"),
]


def _inferir_tela(filepath: str, repo: str) -> str | None:
    """Retorna o nome funcional da tela/fluxo inferido a partir do caminho do arquivo."""
    path_lower = filepath.lower().replace("-", "").replace("_", "")
    repo_lower = repo.lower().replace("-", "")
    combined = path_lower + " " + repo_lower
    for keywords, nome in _TELA_KEYWORDS:
        if any(kw.lower().replace("-", "").replace("_", "") in combined for kw in keywords):
            return nome
    return None


def _build_telas_qa(matriz: list[dict]) -> list[dict]:
    """
    Infere telas/funcionalidades a partir dos impactos e gera lista para o QA.
    Agrupa por tela, lista repositórios afetados, prioridade e tipo de teste sugerido.
    """
    # Áreas que têm reflexo direto em tela testável pelo QA
    _AREAS_VISIVEIS = {"Frontend", "Backend", "Processamento/Batch", "Integrações"}

    telas: dict[str, dict] = {}

    for m in matriz:
        if m["area"] not in _AREAS_VISIVEIS:
            continue
        tela = _inferir_tela(m["evidencia"]["arquivo"], m["repositorio"])
        if not tela:
            continue

        if tela not in telas:
            telas[tela] = {
                "tela": tela,
                "repositorios": set(),
                "areas_impactadas": set(),
                "prioridade_maxima": "P3",
                "impactos": 0,
                "requer_compatibilidade_dual": False,
                "tipo_teste": set(),
                "evidencias": [],
            }

        t = telas[tela]
        t["repositorios"].add(m["repositorio"])
        t["areas_impactadas"].add(m["area"])
        t["impactos"] += 1
        if m["requer_compatibilidade_dual"]:
            t["requer_compatibilidade_dual"] = True

        # Prioridade: P1 > P2 > P3
        if m["prioridade"] == "P1":
            t["prioridade_maxima"] = "P1"
        elif m["prioridade"] == "P2" and t["prioridade_maxima"] != "P1":
            t["prioridade_maxima"] = "P2"

        # Tipo de teste sugerido
        area = m["area"]
        if area == "Frontend":
            t["tipo_teste"].add("UI: campo CNPJ aceita alfanumérico")
        if area == "Backend":
            t["tipo_teste"].add("Funcional: fluxo completo com CNPJ alfanumérico")
        if area == "Processamento/Batch":
            t["tipo_teste"].add("Funcional: geração de documento/relatório com CNPJ alfanumérico")
        if area == "Integrações":
            t["tipo_teste"].add("Integração: envio/recebimento de CNPJ alfanumérico para parceiro")
        if m["requer_compatibilidade_dual"]:
            t["tipo_teste"].add("Regressão: CNPJ numérico antigo continua funcionando")

        # Guarda até 2 evidências por tela
        if len(t["evidencias"]) < 2:
            t["evidencias"].append({
                "arquivo": m["evidencia"]["arquivo"],
                "linha": m["evidencia"]["linha"],
                "trecho": m["evidencia"]["trecho_codigo"][:80],
            })

    # Serializa e ordena por prioridade
    _PRIO_ORDER = {"P1": 0, "P2": 1, "P3": 2}
    result = []
    for t in telas.values():
        result.append({
            "tela": t["tela"],
            "prioridade": t["prioridade_maxima"],
            "repositorios": sorted(t["repositorios"]),
            "areas_impactadas": sorted(t["areas_impactadas"]),
            "total_impactos": t["impactos"],
            "requer_compatibilidade_dual": t["requer_compatibilidade_dual"],
            "testes_sugeridos": sorted(t["tipo_teste"]),
            "evidencias": t["evidencias"],
        })

    result.sort(key=lambda x: (_PRIO_ORDER.get(x["prioridade"], 9), -x["total_impactos"]))
    return result


# ---------------------------------------------------------------------------
# generate_markdown  (telas_qa inserido antes de Pendencias)
# ---------------------------------------------------------------------------

def generate_markdown(output: dict) -> str:
    lines = []
    stats = output["estatisticas"]

    lines += [
        "# 📋 Análise de Impacto – CNPJ Alfanumérico\n",
        f"**Sistema:** {output['sistema_escopo']}  ",
        f"**Data:** {output['data_execucao']}  ",
        f"**Scan ID:** `{output.get('scan_id', '—')}`  ",
        f"**Versão SPEC:** {output['spec_versao']}\n",
    ]

    # Resumo
    lines += [
        "## 📊 Resumo Executivo\n",
        "| Métrica | Valor |", "|---------|-------|",
        f"| Repositórios analisados | {stats['total_repositorios_analisados']} |",
        f"| Total de impactos | {stats['total_impactos_encontrados']} |",
        f"| Requerem compatibilidade dual | {stats.get('requerem_compatibilidade_dual', 0)} |",
    ]
    for area, count in sorted(stats["impactos_por_area"].items()):
        lines.append(f"| Impactos em {area} | {count} |")
    lines.append("")

    lines += ["### Distribuição por Complexidade\n", "| Complexidade | Quantidade |", "|--------------|------------|"]
    for compl, count in stats["impactos_por_complexidade"].items():
        emoji = {"Alta": "🔴", "Média": "🟡", "Baixa": "🟢"}.get(compl, "⚪")
        lines.append(f"| {emoji} {compl} | {count} |")
    lines.append("")

    # Arquivos críticos — seção mais importante para o time de engenharia
    criticos = output.get("arquivos_criticos", [])
    if criticos:
        lines += [
            "## 🚨 Arquivos Críticos – Migrar Primeiro\n",
            "> Arquivos com maior número de chamadores estimados. "
            "Mudar estes componentes tem efeito cascata em toda a aplicação. "
            "**Devem ser os primeiros a receber testes de regressão e feature flags.**\n",
            "| # | Repositório | Arquivo | Área | Chamadores | Impactos | Dual | Linhas |",
            "|---|-------------|---------|------|------------|----------|------|--------|"]
        for i, arq in enumerate(criticos, start=1):
            dual = "✅" if arq["requer_compatibilidade_dual"] else "—"
            linhas = ", ".join(str(l) for l in sorted(set(arq["linhas_afetadas"]))[:5])
            if len(arq["linhas_afetadas"]) > 5:
                linhas += f" (+{len(arq['linhas_afetadas'])-5})"
            nome = arq["arquivo"].split("/")[-1]
            lines.append(
                f"| {i} | `{arq['repositorio']}` | `{nome}` "
                f"| {arq['area']} | **{arq['chamadores_estimados']}** "
                f"| {arq['impactos_no_arquivo']} | {dual} | {linhas} |"
            )
        lines.append("")

    # Matriz
    lines.append("## 🗂️ Matriz de Impacto\n")
    agrupado: dict[str, list] = {}
    for m in output["matriz_impacto"]:
        agrupado.setdefault(m["area"], []).append(m)

    for area, items in sorted(agrupado.items()):
        lines.append(f"### {area} ({len(items)} impacto(s))\n")
        lines += ["| ID | Repositório | Componente | Complexidade | Chamadores | Dual | Descrição |",
                  "|----|-------------|------------|--------------|------------|------|-----------|"]
        for m in items[:50]:
            dual = "✅" if m.get("requer_compatibilidade_dual") else "—"
            lines.append(
                f"| {m['id']} | {m['repositorio']} | `{m['componente']}` "
                f"| {m['complexidade']} | {m.get('chamadores_estimados', 0)} | {dual} | {m['descricao_impacto'][:80]} |"
            )
        if len(items) > 50:
            lines.append(f"| ... | +{len(items)-50} itens (ver JSON) | | | | | |")
        lines.append("")

    # Evidências
    lines += ["## 🔍 Evidências (amostra)\n", "```"]
    for m in output["matriz_impacto"][:20]:
        ev = m["evidencia"]
        lines += [f"[{m['id']}] {m['repositorio']}/{ev['arquivo']}:{ev['linha']}",
                  f"  → {ev['trecho_codigo'][:120]}", ""]
    lines += ["```\n"]

    # Ordem de migração por módulo
    lines += ["## 🗺️ Ordem de Migração por Módulo\n",
              "> Cada módulo (repositório) é migrado de forma independente. "
              "A sequência interna de áreas dentro de cada módulo segue a ordem de dependência técnica.\n"]
    for s in output.get("ordem_migracao", []):
        deps_str = ", ".join(f"`{d}`" for d in s.get("depende_de", []))
        lines.append(f"### Módulo {s['passo']}: `{s['modulo']}`\n")
        lines.append(f"**Total:** {s['total_impactos']} impactos | "
                     f"**Alta:** {s['impactos_alta_complexidade']} | "
                     f"**Dual:** {s['requerem_compatibilidade_dual']}"
                     + (f" | **Depende de:** {deps_str}" if deps_str else "") + "\n")
        lines += ["| Passo | Área | Impactos | Alta | Dual | Rationale |",
                  "|-------|------|----------|------|------|-----------|"]
        for i, a in enumerate(s["areas"], start=1):
            lines.append(
                f"| {i} | {a['area']} | {a['total_impactos']} "
                f"| {a['impactos_alta_complexidade']} | {a['requerem_compatibilidade_dual']} "
                f"| {a['rationale'][:80]} |"
            )
        lines.append("")

    # Mapa de calor de risco por sprint
    heatmap = output.get("heatmap_risco", [])
    if heatmap:
        _H_EMOJI = {"Crítico": "🔴", "Alto": "🟠", "Médio": "🟡", "Baixo": "🟢"}
        lines += [
            "## 🌡️ Mapa de Calor de Risco por Sprint\n",
            "> Score composto: impactos Alta (×2) + SPOF (+5) + Gargalo (+3×nível) + Fluxo partido (+4). "
            "Normalizado 0–100.\n",
            "| Sprint | Módulo | Nível | Score | Fatores |",
            "|--------|--------|-------|-------|---------|"]
        for h in heatmap:
            emoji = _H_EMOJI.get(h["nivel_risco"], "")
            fatores = ", ".join(h["fatores"]) or "—"
            lines.append(
                f"| {h['passo']} | `{h['modulo']}` "
                f"| {emoji} {h['nivel_risco']} | {h['score_normalizado']} "
                f"| {fatores} |"
            )
        lines.append("")

    # SPOFs
    spof = output.get("spof", [])
    if spof:
        lines += [
            "## ⚡ SPOFs — Pontos Únicos de Falha\n",
            "> Repos que são o **único** representante de um domínio crítico. "
            "Qualquer atraso neles bloqueia o domínio inteiro sem substituto.\n",
            "| Domínio | Repositório | Sprint | Impactos Alta | Alerta |",
            "|---------|------------|--------|---------------|--------|"]
        for s in spof:
            lines.append(
                f"| **{s['dominio']}** | `{s['repositorio']}` "
                f"| {s.get('passo_migracao', '—')} | {s['impactos_alta']} "
                f"| {s['alerta']} |"
            )
        lines.append("")

    # Gargalos arquiteturais
    gargalos = output.get("gargalos", [])
    if gargalos:
        _G_EMOJI = {"Crítico": "🔴", "Alto": "🟠", "Médio": "🟡"}
        lines += [
            "## 🔥 Gargalos Arquiteturais\n",
            "> Repos que participam de muitos fluxos. Qualquer atraso neles atrasa a migração inteira.\n",
            "| Nível | Repositório | Fluxos | % do Total | Sprint | Alerta |",
            "|-------|------------|--------|------------|--------|--------|"]
        for g in gargalos:
            emoji = _G_EMOJI.get(g["nivel"], "")
            lines.append(
                f"| {emoji} {g['nivel']} | `{g['repositorio']}` "
                f"| {g['n_fluxos']} | {g['pct_fluxos']}% "
                f"| {g.get('passo_migracao', '—')} | {g['alerta']} |"
            )
        lines.append("")

    # Trilhas paralelas
    trilhas_data = output.get("trilhas")
    if trilhas_data:
        n = trilhas_data["n_trilhas"]
        delta = trilhas_data["desequilibrio_pct"]
        lines += [
            f"## 🔀 Divisão em {n} Trilhas Paralelas\n",
            f"> Repos agrupados por similaridade de áreas impactadas e divididos em {n} trilhas com carga equilibrada.",
            f"> Desequilíbrio de carga: **{delta}%** (quanto menor, mais equilibrado).\n",
        ]

        # Grupos
        lines.append("### Grupos de Repos com Perfil Parecido\n")
        lines += ["| Grupo | Perfil de Áreas | Repos | Impactos Difíceis | Total |",
                  "|-------|----------------|-------|-------------------|-------|"]
        for g in trilhas_data["grupos"]:
            repos_str = ", ".join(f"`{r['modulo']}`" for r in g["repositorios"])
            lines.append(f"| {g['grupo']} | {g['perfil']} | {repos_str} | {g['total_alta']} | {g['total_impactos']} |")
        lines.append("")

        # Trilhas
        for t in trilhas_data["trilhas"]:
            lines.append(f"### Trilha {t['trilha']}  —  {t['carga_alta']} impactos difíceis | {t['total_impactos']} total\n")
            completos = t.get("fluxos_completos", [])
            if completos:
                lines.append("**Fluxos completos nesta trilha:** " + " · ".join(f"`{f}`" for f in completos) + "\n")
            lines += ["| Ordem | Repo | Difíceis | Total | Áreas | Fluxos |",
                      "|-------|------|----------|-------|-------|--------|"]
            for r in t["repositorios"]:
                fluxos_str = ", ".join(r.get("fluxos", [])) or "—"
                lines.append(f"| {r['passo']} | `{r['modulo']}` | {r['alta']} | {r['total']} | {r['perfil']} | {fluxos_str} |")
            lines.append("")

        # Fluxos partidos
        partidos = trilhas_data.get("fluxos_partidos", [])
        if partidos:
            lines.append("### ⚠️ Fluxos Partidos entre Trilhas — Coordenar Entrega\n")
            lines.append("> Estes fluxos têm repos em trilhas diferentes. As trilhas precisam sincronizar antes do go-live.\n")
            lines += ["| Gravidade | Fluxo | Trilhas | Repos | Repositórios |",
                      "|-----------|-------|---------|-------|-------------|"]
            _G_EMOJI = {"Crítico": "🔴", "Alto": "🟠", "Médio": "🟡", "Baixo": "🟢"}
            for fp in partidos:
                g = fp.get("gravidade", "—")
                trilhas_str = ", ".join(f"T{t}" for t in fp["trilhas"])
                repos_str = ", ".join(f"`{r}`" for r in fp["repositorios"])
                lines.append(f"| {_G_EMOJI.get(g, '')} {g} | **{fp['fluxo']}** | {trilhas_str} | {fp.get('n_repositorios', len(fp['repositorios']))} | {repos_str} |")
            lines.append("")

        # Grafo de dependências entre trilhas
        grafo = trilhas_data.get("grafo_dependencias", {})
        arestas = grafo.get("arestas", [])
        if arestas:
            lines.append("### 🔗 Dependências entre Trilhas\n")
            lines.append("> Trilha de origem deve ser concluída antes da trilha de destino.\n")
            lines += ["| De | Para | Motivo |",
                      "|----|------|--------|"]
            for a in arestas:
                motivos = "; ".join(a["motivos"][:3])
                if len(a["motivos"]) > 3:
                    motivos += f" (+{len(a['motivos'])-3})"
                lines.append(f"| Trilha {a['de']} | Trilha {a['para']} | {motivos} |")
            lines.append("")

        # Dependências cruzadas
        deps = trilhas_data.get("dependencias_cruzadas", [])
        if deps:
            lines.append("### ⚠️ Coordenar antes do merge\n")
            for dep in deps:
                repos_str = ", ".join(f"`{m}`" for m in dep["repositorios"])
                lines.append(f"- **{dep['area']}**: {repos_str} — definir quem faz a migration/versão de API primeiro.")
            lines.append("")

    # Estimativa de esforço por módulo
    esforco = output.get("esforco", [])
    if esforco:
        dias_total_geral = sum(e["dias_estimados"] for e in esforco)
        sp_total = sum(e["story_points"] for e in esforco)
        lines += [
            "## ⏱️ Estimativa de Esforço por Módulo\n",
            f"> Total estimado: **{dias_total_geral:.1f} dias** | **{sp_total} story points**  ",
            "> Fórmula: Σ(dias por impacto × fator dual) + overhead fixo (2 dias). Story points em escala Fibonacci.\n",
            "| Sprint | Módulo | Dias | SP | Dual | Maior Área |",
            "|--------|--------|------|----|------|-----------|"]
        for e in esforco:
            maior = e["esforco_por_area"][0]["area"] if e["esforco_por_area"] else "—"
            dual  = "✅" if e["requer_dual"] else "—"
            lines.append(
                f"| {e['passo']} | `{e['modulo']}` "
                f"| {e['dias_estimados']} | **{e['story_points']}** "
                f"| {dual} | {maior} |"
            )
        lines.append("")

    # Critérios de aceite por módulo
    criterios = output.get("criterios_aceite", [])
    if criterios:
        lines += [
            "## ✅ Critérios de Aceite por Módulo\n",
            "> Condições que devem ser verdadeiras para considerar o módulo migrado e pronto para go-live.\n",
        ]
        for c in criterios:
            lines.append(f"### Módulo {c['passo']}: `{c['modulo']}`\n")
            for ca in c["criterios_por_area"]:
                lines.append(f"**{ca['area']}**\n")
                lines += [f"- [ ] {cr}" for cr in ca["criterios"]]
                lines.append("")
            lines.append("**Encerramento**\n")
            lines += [f"- [ ] {cr}" for cr in c["criterios_encerramento"]]
            lines.append("")

    # Checklist rollback
    lines.append("## 🔄 Checklist de Rollback\n")
    for area, perguntas in output.get("checklist_rollback", {}).items():
        lines.append(f"### {area}\n")
        lines += [f"- [ ] {p}" for p in perguntas]
        lines.append("")

    # Impacto em dados
    if output.get("impacto_dados"):
        lines.append("## 🗄️ Impacto em Dados – Queries de Estimativa\n")
        for area, info in output["impacto_dados"].items():
            lines += [f"### {area}\n", f"_{info['descricao']}_\n"]
            for q in info["queries"]:
                lines += ["```sql", q, "```\n"]
        lines.append("")

    # Riscos
    lines += ["## ⚠️ Riscos Mapeados\n",
              "| Risco | Impacto | Mitigação |", "|-------|---------|-----------|"]
    for r in output["riscos_mapeados"]:
        lines.append(f"| {r['risco']} | {r['impacto'][:80]} | {r['mitigacao'][:80]} |")
    lines.append("")

    # Parceiros externos
    parceiros = output.get("parceiros_externos", [])
    if parceiros:
        lines += [
            "## 🤝 Parceiros Externos — Alinhamento Necessário\n",
            "> Parceiros detectados nos impactos que podem rejeitar CNPJ alfanumérico. "
            "**Cada um precisa confirmar suporte antes do go-live.**\n",
            "| Parceiro | Descrição | Repositórios | Status |",
            "|----------|-----------|-------------|--------|"]
        for p in parceiros:
            repos_str = ", ".join(f"`{r}`" for r in p["repositorios"])
            lines.append(f"| **{p['parceiro']}** | {p['descricao']} | {repos_str} | {p['status_alinhamento']} |")
        lines.append("")

    # Progresso
    prog = stats.get("progresso", {})
    if prog:
        total = stats["total_impactos_encontrados"]
        resolvidos = prog.get("resolvido", 0) + prog.get("falso_positivo", 0)
        pct = round(resolvidos / total * 100) if total else 0
        lines += [
            "## 📈 Progresso da Migração\n",
            f"> {resolvidos}/{total} impactos endereçados ({pct}%)\n",
            "| Status | Quantidade |", "|--------|------------|"]
        for status, count in prog.items():
            emoji = {"pendente": "⏳", "em_progresso": "🔄", "resolvido": "✅", "falso_positivo": "🚫"}.get(status, "")
            lines.append(f"| {emoji} {status} | {count} |")
        lines.append("")

    # Pessoa Jurídica — documentos e fluxos
    lines += [
        "## 🏢 Pessoa Jurídica — Documentos e Fluxos Impactados\n",
        "> O CNPJ alfanumérico impacta diretamente todos os documentos e fluxos de Pessoa Jurídica. "
        "Os itens abaixo devem ser revisados independentemente dos impactos de código detectados.\n",
        "### Documentos PJ que referenciam CNPJ\n",
        "| Documento | Impacto | Ação Necessária |",
        "|-----------|---------|----------------|",
        "| Contrato Social | CNPJ do sócio/empresa em campo numérico | Atualizar template para aceitar alfanumérico |",
        "| Procuração | CNPJ do outorgante/outorgado | Atualizar validação e máscara no formulário |",
        "| Ficha Cadastral PJ | Campo CNPJ com máscara numérica | Atualizar máscara e regex de validação |",
        "| Inscrição Estadual | Vinculada ao CNPJ da empresa | Verificar se validação cruzada usa CNPJ numérico |",
        "| NIRE (Junta Comercial) | Número vinculado ao CNPJ | Revisar integração com Junta Comercial |",
        "| Comprovante de Abertura de Conta PJ | CNPJ impresso no documento | Atualizar template de geração (PDF/DOCX) |",
        "| NFS-e / Nota Fiscal | CNPJ do prestador/tomador no XML | Já coberto pelas regras BATCH-001 / XSD-001 |",
        "| CNAB / Remessa Bancária | CNPJ do cedente em layout fixo | Já coberto pelas regras INT-001 |",
        "| eSocial / EFD-Reinf / SPED | CNPJ em layout fiscal fixo | Já coberto pelas regras BATCH-001 |",
        "",
        "### Fluxos de Onboarding PJ\n",
        "| Etapa | Risco | Recomendação |",
        "|-------|-------|-------------|",
        "| Digitação do CNPJ | Máscara numérica bloqueia letras | Atualizar máscara para aceitar `[A-Z0-9]` |",
        "| Consulta Receita Federal | API pode retornar CNPJ alfanumérico | Validar resposta da API de consulta CNPJ |",
        "| Upload de Documentos | Metadados do arquivo com CNPJ numérico | Atualizar extração de metadados |",
        "| Geração de Contrato | Template com máscara `##.###.###/####-##` | Atualizar template para formato alfanumérico |",
        "| Assinatura Digital | CNPJ no certificado pode ser alfanumérico | Verificar compatibilidade com ICP-Brasil |",
        "| KYC / Background Check | Parceiro pode rejeitar CNPJ alfanumérico | Alinhar com CAF/parceiro de KYC |",
        "",
        "### Representante Legal / Sócios PJ\n",
        "> CNPJs de sócios pessoas jurídicas (holdings, empresas controladoras) também serão alfanuméricos.\n",
        "| Campo | Localização Típica | Ação |",
        "|-------|-------------------|------|",
        "| CNPJ do sócio PJ | Quadro societário / QSA | Atualizar campo e validação |",
        "| CNPJ do procurador PJ | Formulário de procuração | Atualizar máscara |",
        "| CNPJ do grupo econômico | Cadastro de grupo | Atualizar campo |",
        "",
    ]

    # Telas para QA
    telas_qa = output.get("telas_qa", [])
    if telas_qa:
        lines += [
            "## Telas para QA\n",
            "> Telas e fluxos inferidos a partir dos impactos de codigo. "
            "Testar com CNPJ alfanumerico (ex: `12.ABC.345/01DE-35`) "
            "e verificar que CNPJ numerico antigo continua funcionando.\n",
            "| Prioridade | Tela / Fluxo | Repositorios | Testes Sugeridos | Dual? |",
            "|------------|-------------|-------------|-----------------|-------|"]
        for t in telas_qa:
            repos_str = ", ".join(f"`{r}`" for r in t["repositorios"])
            testes_str = " / ".join(t["testes_sugeridos"])
            dual = "Sim" if t["requer_compatibilidade_dual"] else "Nao"
            lines.append(
                f"| **{t['prioridade']}** | {t['tela']} | {repos_str} "
                f"| {testes_str[:120]} | {dual} |"
            )
        lines.append("")

    # Pendencias
    lines += ["## 📌 Pendências\n",
              "| ID | Descrição | Responsável | Prazo |", "|----|-----------|-------------|-------|"]
    for p in output["pendencias_identificadas"]:
        lines.append(f"| {p['id']} | {p['descricao'][:100]} | {p['responsavel']} | {p['prazo_estimado']} |")
    lines.append("")

    # Cobertura / pontos cegos
    cobertura = output.get("cobertura", {})
    sem_impacto = cobertura.get("repositorios_sem_impacto", [])
    pontos_cegos = cobertura.get("pontos_cegos", [])
    if pontos_cegos:
        lines.append("## ⚠️ Limitações de Cobertura\n")
        lines.append("> Esta varredura é baseada em análise estática por regex. Os pontos abaixo representam riscos de falso negativo.\n")
        for pc in pontos_cegos:
            lines += [f"**{pc['id']}** — {pc['descricao']}", f"_Recomendação:_ {pc['recomendacao']}", ""]
    aliases_suspeitos = cobertura.get("repos_sem_impacto_com_aliases", {})
    if aliases_suspeitos:
        lines.append("### ⚠️ Repos sem impacto mas com aliases suspeitos\n")
        lines.append("> Estes repos não usam a palavra 'cnpj' mas contêm campos que podem processar CNPJ indiretamente. **Requerem revisão manual.**\n")
        lines += ["| Repositório | Aliases encontrados |", "|-------------|---------------------|"]
        for repo, aliases in aliases_suspeitos.items():
            lines.append(f"| `{repo}` | {', '.join(f'`{a}`' for a in aliases)} |")
        lines.append("")
    if sem_impacto:
        lines.append(f"### Repositórios sem impacto detectado ({len(sem_impacto)})\n")
        lines.append("> Podem ser genuinamente não afetados ou usar aliases de campo sem a palavra 'cnpj'.\n")
        lines += [f"- `{r}`" for r in sem_impacto]
        lines.append("")

    # Repositórios
    lines.append("## 📦 Repositórios Analisados\n")
    lines += [f"- `{r}`" for r in output["repositorios_analisados"]]
    lines += ["", "---\n", "*Gerado automaticamente pelo CNPJ Impact Scanner*"]

    return "\n".join(lines)
