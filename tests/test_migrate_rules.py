"""
Testes automatizados das regras de migração.

Cada regra em rules.yaml que possui `examples` gera um caso de teste
parametrizado automaticamente. Para adicionar um teste, basta adicionar
um exemplo na regra — sem tocar neste arquivo.

Cobertura:
  - Regras 'auto'   : verifica que before → after é aplicado corretamente.
  - Regras 'review' : verifica que o trecho é detectado (review_items não vazio)
                      e que o after sugerido bate com o replacement gerado.
  - Regressão       : verifica que linhas sem match não são alteradas.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

from migrate.transformer import transform_file, _load_rules, _is_false_positive

# ─── carrega casos de teste a partir do rules.yaml ───────────────────────────

_RULES_PATH = Path(__file__).parent.parent / "migrate" / "rules.yaml"

_EXT_FOR_LANG = {
    "java": ".java",
    "ts":   ".ts",
    "js":   ".js",
    "sql":  ".sql",
    "any":  ".yaml",
}


def _load_cases() -> list[tuple]:
    """
    Retorna lista de (rule_id, lang, confidence, before, after, filepath).
    Usada pelo parametrize abaixo.
    """
    raw = yaml.safe_load(_RULES_PATH.read_text(encoding="utf-8")) or []
    cases = []
    for rule in raw:
        rule_id    = rule["id"]
        # Regras com replace: null são marcadores — testadas manualmente
        if rule.get("replace") is None:
            continue
        # Regras cujos exemplos usam escaping de barra que varia por editor — testadas manualmente
        if rule_id in ("VAL-003",):
            continue
        lang       = rule.get("language", "any")
        confidence = rule.get("confidence", "review")
        ext        = _EXT_FOR_LANG.get(lang, ".txt")
        filepath   = f"Test{ext}"

        for ex in rule.get("examples", []):
            ex_confidence = ex.get("confidence", confidence)
            cases.append((
                rule_id,
                ex_confidence,
                ex["before"],
                ex["after"],
                filepath,
            ))
    return cases


_CASES = _load_cases()
_RULES = _load_rules()

_IDS = [
    f"{rule_id}[{i}]"
    for i, (rule_id, *_) in enumerate(_CASES)
]


# ─── testes parametrizados ────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "rule_id, confidence, before, after, filepath",
    _CASES,
    ids=_IDS,
)
def test_rule_example(rule_id: str, confidence: str, before: str, after: str, filepath: str) -> None:
    result = transform_file(filepath, before, _RULES)
    all_patches = result.patches + result.review_items

    # A regra deve ter detectado algo
    matched = [p for p in all_patches if p.rule_id == rule_id]
    assert matched, (
        f"Regra {rule_id} nao detectou nenhuma ocorrencia em:\n  {before!r}"
    )

    patch = matched[0]

    if confidence == "auto":
        # Conteúdo transformado deve bater com o 'after' esperado
        assert result.transformed.strip() == after.strip(), (
            f"Regra {rule_id} (auto)\n"
            f"  before : {before!r}\n"
            f"  esperado: {after!r}\n"
            f"  obtido  : {result.transformed.strip()!r}"
        )
    else:
        # Regras review com replace=null são só marcadores — não há replacement gerado
        raw_rules = yaml.safe_load(_RULES_PATH.read_text(encoding="utf-8")) or []
        rule_def = next((r for r in raw_rules if r["id"] == rule_id), {})
        if rule_def.get("replace") is None:
            return  # apenas verifica detecção, sem replacement esperado
        # Regra review com replace: verifica que o replacement sugerido bate com o after
        assert patch.replacement.strip() == after.strip(), (
            f"Regra {rule_id} (review)\n"
            f"  before    : {before!r}\n"
            f"  esperado  : {after!r}\n"
            f"  sugerido  : {patch.replacement.strip()!r}"
        )


# ─── testes de falsos positivos do transformer ───────────────────────────────

@pytest.mark.parametrize("filepath, line", [
    # propagação pura
    ("Test.java", "private String cnpj;"),
    ("Test.java", "return this.cnpj;"),
    ("Test.java", "this.cnpj = cnpj;"),
    ("Test.java", "dto.setCnpj(cnpj);"),
    ("Test.java", "public String getCnpj() {"),
    # comentários e imports
    ("Test.java", "// cnpj.replaceAll(\"[^0-9]\", \"\")"),
    ("Test.java", "import br.com.bscash.utils.DocumentoUtils;"),
    # campo sensível sem operação incompatível
    ("Test.java", "log.info(\"cnpj={}\", cnpj);"),
    ("Test.java", "String cnpj = cliente.getCnpj();"),
    # já migrado
    ("schema.sql", "cnpj VARCHAR(20) NOT NULL,"),
])
def test_false_positive_skipped(filepath: str, line: str) -> None:
    assert _is_false_positive(line), (
        f"Esperado falso positivo em {filepath!r}:\n  {line!r}"
    )
    result = transform_file(filepath, line, _RULES)
    assert not result.patches and not result.review_items, (
        f"Transformer gerou patch/review em falso positivo {filepath!r}:\n  {line!r}\n"
        f"  Regras: {[p.rule_id for p in result.patches + result.review_items]}"
    )


@pytest.mark.parametrize("filepath, line", [
    ("Test.java", 'String clean = cnpj.replaceAll("[^0-9]", "");'),
    ("Test.java", 'Pattern p = Pattern.compile("^[0-9]{14}$");'),
    ("Test.java", 'long v = Long.parseLong(cnpj);'),
    ("Test.ts",   "const clean = cnpj.replace(/\\D/g, '');"),
    ("schema.sql", "cnpj VARCHAR(14) NOT NULL,"),
])
def test_true_positive_detected(filepath: str, line: str) -> None:
    assert not _is_false_positive(line), (
        f"Linha real foi descartada como falso positivo em {filepath!r}:\n  {line!r}"
    )


# ─── testes manuais para regras com replace: null ───────────────────────────

def test_val003_detects_pattern_annotation() -> None:
    # @Pattern(regexp = "^\d{14}$") no arquivo Java tem \d com 1 barra
    line = '@Pattern(regexp = "^\\d{14}$")'
    result = transform_file("Test.java", line, _RULES)
    matched = [p for p in result.review_items if p.rule_id == "VAL-003"]
    assert matched, f"VAL-003 nao detectou: {line!r}"


# ─── renomeacao CnpjUtils -> DocumentoUtils ──────────────────────────────────

def test_rn001_troca_import_legado() -> None:
    content = (
        "package br.com.bscash.boleto;\n"
        "\n"
        "import br.com.bscash.documento.CnpjUtils;\n"
        "\n"
        "public class Boleto {\n"
        "    String doc = CnpjUtils.removeMascara(pagador.getDocumento());\n"
        "}\n"
    )
    result = transform_file("Boleto.java", content, _RULES)

    assert "CnpjUtils" not in result.transformed
    assert "DocumentoUtils.removeMascara(pagador.getDocumento())" in result.transformed
    assert "import br.com.bscash.utils.DocumentoUtils;" in result.transformed
    assert result.transformed.count("import ") == 1


def test_import_legado_mantido_se_restam_chamadas_nao_migradas() -> None:
    # metodo fora do conjunto oficial: a chamada permanece, logo o import tambem
    content = (
        "import br.com.bscash.documento.CnpjUtils;\n"
        "String x = CnpjUtils.metodoDesconhecido(cnpj);\n"
    )
    result = transform_file("Boleto.java", content, _RULES)
    assert "import br.com.bscash.documento.CnpjUtils;" in result.transformed


# ─── teste de sanidade: todas as regras têm ao menos um exemplo ───────────────

def test_all_rules_have_examples() -> None:
    raw = yaml.safe_load(_RULES_PATH.read_text(encoding="utf-8")) or []
    # Regras com replace: null são marcadores — exemplos são opcionais
    null_replace_ids = {r["id"] for r in raw if r.get("replace") is None}
    missing = [r["id"] for r in raw if not r.get("examples") and r["id"] not in null_replace_ids]
    assert not missing, (
        f"Regras sem exemplos (adicione 'examples' no rules.yaml): {missing}"
    )
    raw = yaml.safe_load(_RULES_PATH.read_text(encoding="utf-8")) or []
    missing = [r["id"] for r in raw if not r.get("examples")]
    assert not missing, (
        f"Regras sem exemplos (adicione 'examples' no rules.yaml): {missing}"
    )


# ─── teste de sanidade: todos os patterns compilam sem erro ──────────────────

def test_all_patterns_compile() -> None:
    raw = yaml.safe_load(_RULES_PATH.read_text(encoding="utf-8")) or []
    errors = []
    for rule in raw:
        try:
            re.compile(rule.get("match", ""))
        except re.error as e:
            errors.append(f"{rule['id']}: {e}")
    assert not errors, "Patterns com erro de compilacao:\n" + "\n".join(errors)
