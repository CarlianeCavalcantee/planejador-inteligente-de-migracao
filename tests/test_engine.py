"""Testes para core/engine.py"""

import pytest

from core.engine import (
    deduplicate,
    is_false_positive,
    process_repo,
    scan_file,
    scan_sql_structural,
)


# ---------------------------------------------------------------------------
# is_false_positive
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("line", [
    "// validateCNPJ(cnpj)",
    "/* cnpj check */",
    " * @param cnpj",
    "# cnpj config",
    "import com.example.CnpjValidator;",
    "",
    "   ",
])
def test_is_false_positive_returns_true_for_noise(line):
    assert is_false_positive(line) is True


@pytest.mark.parametrize("line", [
    'if (!validateCNPJ(cnpj)) throw new Exception("invalid");',
    "cnpj VARCHAR(14) NOT NULL,",
    'String cnpj = "12345678000195";',
    "@Column(length=14, name=\"cnpj\")",
])
def test_is_false_positive_returns_false_for_real_code(line):
    assert is_false_positive(line) is False


def test_is_false_positive_log_statement():
    assert is_false_positive('log.info("cnpj: {}", cnpj)') is True


def test_is_false_positive_getter():
    assert is_false_positive("getCnpj()") is True


# ---------------------------------------------------------------------------
# scan_file
# ---------------------------------------------------------------------------

def test_scan_file_finds_match(minimal_rule):
    content = "\n".join([
        "public class CnpjService {",
        '    if (!validateCNPJ(cnpj)) throw new Exception("invalid");',
        "}",
    ])
    matches = scan_file(content, "CnpjService.java", minimal_rule)
    assert len(matches) == 1
    assert matches[0]["linha"] == 2


def test_scan_file_skips_comment_lines(minimal_rule):
    content = "\n".join([
        "// validateCNPJ is called here",
        "/* validateCNPJ */",
        "validateCNPJ(cnpj);",
    ])
    matches = scan_file(content, "Service.java", minimal_rule)
    assert len(matches) == 1
    assert matches[0]["linha"] == 3


def test_scan_file_no_match_returns_empty(minimal_rule):
    content = "public class Foo { String name; }"
    assert scan_file(content, "Foo.java", minimal_rule) == []


def test_scan_file_truncates_trecho_at_200_chars(minimal_rule):
    long_line = "validateCNPJ(" + "x" * 300 + ")"
    matches = scan_file(long_line, "F.java", minimal_rule)
    assert len(matches) == 1
    assert len(matches[0]["trecho_codigo"]) <= 200


# ---------------------------------------------------------------------------
# scan_sql_structural
# ---------------------------------------------------------------------------

def test_scan_sql_structural_detects_alias_in_table_with_cnpj_col():
    sql = """
CREATE TABLE empresa (
    id BIGINT PRIMARY KEY,
    cnpj VARCHAR(14) NOT NULL,
    documento VARCHAR(14) NOT NULL
);
"""
    matches = scan_sql_structural(sql, "empresa.sql")
    # 'documento' é alias em tabela que tem coluna 'cnpj'
    assert any("documento" in m["trecho_codigo"].lower() for m in matches)


def test_scan_sql_structural_detects_known_alias_name():
    sql = """
CREATE TABLE parceiro (
    id BIGINT PRIMARY KEY,
    tax_id VARCHAR(20) NOT NULL
);
"""
    matches = scan_sql_structural(sql, "parceiro.sql")
    assert any("tax_id" in m["trecho_codigo"].lower() for m in matches)


def test_scan_sql_structural_ignores_unrelated_table():
    sql = """
CREATE TABLE produto (
    id BIGINT PRIMARY KEY,
    nome VARCHAR(100) NOT NULL
);
"""
    matches = scan_sql_structural(sql, "produto.sql")
    assert matches == []


# ---------------------------------------------------------------------------
# deduplicate
# ---------------------------------------------------------------------------

def test_deduplicate_keeps_higher_priority_area(cfg, minimal_rule, db_rule):
    from core.config import area_priority
    priority = area_priority(cfg)

    impact_backend = {
        "_rule": minimal_rule,  # Backend
        "repositorio": "repo",
        "filepath": "src/Foo.java",
        "match": {"linha": 10, "trecho_codigo": "validateCNPJ(x)", "pattern_matched": "p"},
    }
    impact_db = {
        "_rule": db_rule,  # Banco de Dados — maior prioridade
        "repositorio": "repo",
        "filepath": "src/Foo.java",
        "match": {"linha": 10, "trecho_codigo": "validateCNPJ(x)", "pattern_matched": "p"},
    }
    result = deduplicate([impact_backend, impact_db], priority)
    assert len(result) == 1
    assert result[0]["_rule"]["area"] == "Banco de Dados"


def test_deduplicate_keeps_different_lines(cfg, minimal_rule):
    from core.config import area_priority
    priority = area_priority(cfg)

    impacts = [
        {
            "_rule": minimal_rule,
            "repositorio": "repo",
            "filepath": "src/Foo.java",
            "match": {"linha": 10, "trecho_codigo": "a", "pattern_matched": "p"},
        },
        {
            "_rule": minimal_rule,
            "repositorio": "repo",
            "filepath": "src/Foo.java",
            "match": {"linha": 20, "trecho_codigo": "b", "pattern_matched": "p"},
        },
    ]
    result = deduplicate(impacts, priority)
    assert len(result) == 2


# ---------------------------------------------------------------------------
# process_repo
# ---------------------------------------------------------------------------

def test_process_repo_returns_impacts_with_callers(minimal_rule):
    from core.config import area_priority

    content = "\n".join([
        "public class CnpjService {",
        "    validateCNPJ(cnpj);",
        "    validateCNPJ(other);",
        "}",
    ])
    candidates = [("src/CnpjService.java", "abc123", [minimal_rule])]
    content_map = {"src/CnpjService.java": content}
    priority = {"Backend": 0}

    impacts = process_repo("repo-x", candidates, content_map, priority)
    assert len(impacts) >= 1
    assert all("chamadores_estimados" in imp for imp in impacts)
    assert all("arquivo_critico" in imp for imp in impacts)


def test_process_repo_skips_missing_content(minimal_rule):
    candidates = [("src/Missing.java", "sha", [minimal_rule])]
    content_map = {}
    impacts = process_repo("repo", candidates, content_map, {"Backend": 0})
    assert impacts == []
