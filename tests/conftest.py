"""Fixtures compartilhadas entre todos os testes."""

import pytest
from core.config import _compile_rules


@pytest.fixture
def minimal_rule() -> dict:
    rule = {
        "id": "BE-001",
        "area": "Backend",
        "extensoes": [".java"],
        "nomes_arquivo": [],
        "padroes": [r"(?i)\\d\{14\}", r"(?i)validateCNPJ"],
        "descricao_impacto": "Validador numérico de CNPJ.",
        "complexidade": "Alta",
    }
    _compile_rules({"regras": [rule]})
    return rule


@pytest.fixture
def db_rule() -> dict:
    rule = {
        "id": "DB-001",
        "area": "Banco de Dados",
        "extensoes": [".sql"],
        "nomes_arquivo": [],
        "padroes": [r"(?i)VARCHAR2?\s*\(\s*1[0-9]\s*\).{0,30}cnpj"],
        "descricao_impacto": "Coluna VARCHAR com tamanho fixo.",
        "complexidade": "Média",
    }
    _compile_rules({"regras": [rule]})
    return rule


@pytest.fixture
def cfg(minimal_rule, db_rule) -> dict:
    return {
        "sistema_escopo": "TestSystem",
        "github_org": "test-org",
        "output_file": "impacto_cnpj.json",
        "output_markdown": "impacto_cnpj.md",
        "ignore_paths": ["node_modules", "dist", "*.min.js"],
        "prioridade_area": [
            "Segurança/LGPD",
            "Banco de Dados",
            "API/Contrato",
            "Infraestrutura/CI",
            "Configuração",
            "Integrações",
            "Processamento/Batch",
            "Backend",
            "Testes/Qualidade",
            "Documentação",
            "Frontend",
        ],
        "regras": [minimal_rule, db_rule],
    }


@pytest.fixture
def raw_impact(minimal_rule) -> dict:
    return {
        "_rule": minimal_rule,
        "repositorio": "repo-a",
        "filepath": "src/main/java/CnpjValidator.java",
        "match": {
            "linha": 42,
            "trecho_codigo": 'if (!validateCNPJ(cnpj)) throw new Exception("invalid");',
            "pattern_matched": r"(?i)validateCNPJ",
        },
        "chamadores_estimados": 5,
        "arquivo_critico": False,
    }


@pytest.fixture
def raw_impacts(raw_impact, db_rule) -> list[dict]:
    second = {
        "_rule": db_rule,
        "repositorio": "repo-b",
        "filepath": "db/migrations/V1__create_empresa.sql",
        "match": {
            "linha": 10,
            "trecho_codigo": "cnpj VARCHAR(14) NOT NULL,",
            "pattern_matched": r"(?i)VARCHAR2?\s*\(\s*1[0-9]\s*\).{0,30}cnpj",
        },
        "chamadores_estimados": 0,
        "arquivo_critico": False,
    }
    return [raw_impact, second]
