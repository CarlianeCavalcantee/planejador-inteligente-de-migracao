"""Testes para core/engine.py"""

import pytest

from core.engine import (
    classify_line,
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
    # comentários e imports
    "// validateCNPJ(cnpj)",
    "/* cnpj check */",
    " * @param cnpj",
    "# cnpj config",
    "import com.example.CnpjValidator;",
    "",
    "   ",
    # propagação pura — sem operação relevante
    "private String cnpj;",
    "private String documento;",
    "return cnpj;",
    "return this.cnpj;",
    "return documento;",
    "this.cnpj = cnpj;",
    "this.documento = documento;",
    "this.numeroDocumentoCobranca = cobranca.getNumeroDocumentoCobranca();",
    "this.tipoDocumento = cobranca.getTipoDocumento();",
    "this.documento = cobranca.getDocumento();",
    "dto.setCnpj(cnpj);",
    "dto.setDocumento(documento);",
    "empresa.getCnpj();",
    "cliente.getDocumento();",
    "map.put(\"cnpj\", empresa.getCnpj());",
    ".cnpj(cnpj)",
    ".documento(doc)",
    "public String getCnpj() {",
    "public void setCnpj(String cnpj) {",
    "public String getDocumento() {",
    "public static String formatCnpj(String cnpj) {",
    "if (TipoDocumentoEnum.CPF.equals(cobranca.getTipoDocumento()))",
    "String cpf = StringHelper.apenasNumeros(documento);",
])
def test_is_false_positive_returns_true_for_noise(line):
    assert is_false_positive(line) is True


def test_is_false_positive_cpf_block_with_context():
    """apenasNumeros em bloco isPF não é impacto de CNPJ alfanumérico."""
    context = "if (isPF) {\n    numeroInscricao = StringHelper.preencherZerosEsquerda("
    line = "StringHelper.apenasNumeros(documentoRaw), 14);"
    assert is_false_positive(line, context=context) is True


def test_is_false_positive_cnpj_apenas_numeros_still_impact():
    line = 'String cnpj = StringHelper.apenasNumeros(documento);'
    assert is_false_positive(line) is False


def test_is_false_positive_column_name_documento_is_noise_via_rules():
    """@Column(name=documento) sem length não é impacto — coberto pelas regras ORM/JPA."""
    from core.config import load_config, _compile_rules
    from core.engine import scan_file
    cfg = load_config("scanner-config.yaml")
    _compile_rules(cfg)
    content = "\n".join([
        '@Column(name = "pagadordocumento")',
        "private String pagadorDocumento;",
        '@Column(name = "documento")',
        "private String documento;",
        '@Column(name = "cnpj", length = 14)',
        "private String cnpj;",
    ])
    impacts = []
    for rule in cfg["regras"]:
        if ".java" not in rule.get("extensoes", []):
            continue
        impacts.extend(scan_file(content, "Entity.java", rule, []))
    # Só o @Column com length=14 + cnpj deve aparecer (se a regra JPA casar)
    pending = [m for m in impacts if m["status_migracao"] == "impacto"]
    assert all("length" in m["trecho_codigo"].lower() or "cnpj" in m["trecho_codigo"].lower()
               for m in pending)
    assert not any("pagadordocumento" in m["trecho_codigo"].lower() for m in pending)


@pytest.mark.parametrize("line", [
    'if (!validateCNPJ(cnpj)) throw new Exception("invalid");',
    "cnpj VARCHAR(14) NOT NULL,",
    "cnpj.replaceAll(\"[^0-9]\", \"\");",
    "if (cnpj.length() != 14) throw new Exception();",
    "Long.parseLong(cnpj);",
    "Pattern.compile(\"^[0-9]{14}$\");",
    "@Column(length=14, name=\"cnpj\")",
    "cnpj.substring(0, 8);",
])
def test_is_false_positive_returns_false_for_real_code(line):
    assert is_false_positive(line) is False


def test_is_false_positive_getter():
    assert is_false_positive("public String getCnpj() {") is True


def test_is_false_positive_setter():
    assert is_false_positive("dto.setDocumento(documento);") is True


def test_is_false_positive_field_declaration():
    assert is_false_positive("private String documento;") is True


def test_is_false_positive_return_simple():
    assert is_false_positive("return this.cnpj;") is True


def test_is_false_positive_map_put_getter():
    assert is_false_positive('map.put("cnpj", empresa.getCnpj());') is True


def test_is_false_positive_replace_is_impact():
    assert is_false_positive('cnpj.replaceAll("[^0-9]", "");') is False


def test_is_false_positive_length_check_is_impact():
    assert is_false_positive("if (cnpj.length() != 14)") is False


# ---------------------------------------------------------------------------
# classify_line
# ---------------------------------------------------------------------------

_COMPAT_RULES = [
    {
        "id": "COMPAT-001",
        "motivo": "Utiliza CnpjUtils",
        "_pat": __import__("re").compile(r"CnpjUtils\.(isValid|removeMask|format)\s*\("),
    },
    {
        "id": "COMPAT-002",
        "motivo": "Regex alfanumérico",
        "_pat": __import__("re").compile(r"\[A-Z0-9\]\{14\}"),
    },
]


@pytest.mark.parametrize("line,expected_status", [
    # 🔴 impacto — operação claramente incompatível
    ('cnpj.replaceAll("[^0-9]", "")',        "impacto"),
    ("Long.parseLong(cnpj)",                 "impacto"),
    ('cnpj.matches("\\\\d{14}")',             "impacto"),
    ("cnpj.substring(0, 8)",                 "impacto"),
    ("@Column(length=14, name=\"cnpj\")",     "impacto"),
    # 🟢 compatível — já usa API adaptada
    ("CnpjUtils.isValid(cnpj)",              "compativel"),
    ("CnpjUtils.removeMask(cnpj)",           "compativel"),
    ("Pattern.compile(\"[A-Z0-9]{14}\");",   "compativel"),
    # 🟡 revisão — ambíguo
    ("if (cnpj.length() != 14)",             "revisao"),
    ("cnpj.contains(prefix)",                "revisao"),
    ("cnpj.startsWith(\"00\")",              "revisao"),
])
def test_classify_line(line, expected_status):
    status, _ = classify_line(line, _COMPAT_RULES)
    assert status == expected_status


def test_classify_line_compatible_returns_motivo():
    status, motivo = classify_line("CnpjUtils.isValid(cnpj)", _COMPAT_RULES)
    assert status == "compativel"
    assert motivo == "Utiliza CnpjUtils"


def test_classify_line_impacto_motivo_is_none():
    status, motivo = classify_line('cnpj.replaceAll("[^0-9]", "")', _COMPAT_RULES)
    assert status == "impacto"
    assert motivo is None


def test_classify_line_revisao_motivo_is_none():
    status, motivo = classify_line("if (cnpj.length() != 14)", _COMPAT_RULES)
    assert status == "revisao"
    assert motivo is None


def test_scan_file_includes_status_migracao(minimal_rule):
    content = 'if (!validateCNPJ(cnpj)) throw new Exception("invalid");'
    matches = scan_file(content, "Foo.java", minimal_rule, [])
    assert len(matches) == 1
    assert matches[0]["status_migracao"] == "impacto"
    assert "motivo_status" in matches[0]


def test_scan_file_compatible_status():
    import re
    from core.config import _compile_rules
    compat = [{"id": "C1", "motivo": "usa CnpjUtils", "_pat": re.compile(r"CnpjUtils\.isValid")}]
    # Regra que bate em validateCNPJ; linha também usa CnpjUtils.isValid → compat
    rule = {
        "id": "X", "area": "Backend", "extensoes": [".java"], "nomes_arquivo": [],
        "padroes": [r"validateCNPJ|CnpjUtils\.isValid"],
        "descricao_impacto": "test", "complexidade": "Alta",
    }
    _compile_rules({"regras": [rule]})
    content = "if (!CnpjUtils.isValid(cnpj)) throw new Exception();"
    matches = scan_file(content, "Foo.java", rule, compat)
    assert len(matches) == 1
    assert matches[0]["status_migracao"] == "compativel"
    assert matches[0]["motivo_status"] == "usa CnpjUtils"


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
    tax_id VARCHAR(14) NOT NULL
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
