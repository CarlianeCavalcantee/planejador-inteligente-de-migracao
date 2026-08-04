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

from migrate.transformer import transform_file, _load_rules

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
        # Regra review: verifica que o replacement sugerido bate com o after
        assert patch.replacement.strip() == after.strip(), (
            f"Regra {rule_id} (review)\n"
            f"  before    : {before!r}\n"
            f"  esperado  : {after!r}\n"
            f"  sugerido  : {patch.replacement.strip()!r}"
        )


# ─── teste de regressão: linhas sem match não devem ser alteradas ─────────────

@pytest.mark.parametrize("filepath, line", [
    ("Test.java",  "String cnpj = cliente.getCnpj();"),
    ("Test.java",  "// replaceAll('[^0-9]', '') comentario"),
    ("Test.java",  "log.info(\"cnpj={}\", cnpj);"),
    ("schema.sql", "cnpj VARCHAR(20) NOT NULL,"),   # já migrado
    ("Test.ts",    "const x = value.replace(/\\s/g, '');"),  # replace diferente
])
def test_no_false_positive(filepath: str, line: str) -> None:
    result = transform_file(filepath, line, _RULES)
    assert not result.patches, (
        f"Falso positivo em {filepath!r}:\n  {line!r}\n"
        f"  Regras disparadas: {[p.rule_id for p in result.patches]}"
    )


# ─── teste de sanidade: todas as regras têm ao menos um exemplo ───────────────

def test_all_rules_have_examples() -> None:
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
