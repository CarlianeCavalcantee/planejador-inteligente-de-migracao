"""Testes para core/config.py"""

import json
import re
import tempfile
from pathlib import Path

import pytest

from core.config import _compile_rules, area_priority, load_config


def test_compile_rules_populates_compiled(minimal_rule):
    assert "_compiled" in minimal_rule
    assert all(isinstance(p, re.Pattern) for p in minimal_rule["_compiled"])


def test_compile_rules_skips_invalid_pattern():
    rule = {
        "id": "X",
        "area": "Backend",
        "extensoes": [".java"],
        "nomes_arquivo": [],
        "padroes": ["[invalid(regex", r"\d{14}"],
        "descricao_impacto": "test",
        "complexidade": "Alta",
    }
    _compile_rules({"regras": [rule]})
    # padrão inválido é ignorado, padrão válido é compilado
    assert len(rule["_compiled"]) == 1


def test_area_priority_returns_correct_order(cfg):
    priority = area_priority(cfg)
    assert priority["Segurança/LGPD"] < priority["Banco de Dados"]
    assert priority["Banco de Dados"] < priority["Backend"]
    assert priority["Backend"] < priority["Frontend"]


def test_area_priority_unknown_area_not_in_result(cfg):
    priority = area_priority(cfg)
    assert "AreaInexistente" not in priority


def test_load_config_compiles_rules(tmp_path):
    config = {
        "sistema_escopo": "Test",
        "github_org": "org",
        "output_file": "out.json",
        "output_markdown": "out.md",
        "ignore_paths": [],
        "prioridade_area": ["Backend"],
        "regras": [
            {
                "id": "BE-001",
                "area": "Backend",
                "extensoes": [".java"],
                "nomes_arquivo": [],
                "padroes": [r"\d{14}"],
                "descricao_impacto": "test",
                "complexidade": "Alta",
            }
        ],
    }
    config_file = tmp_path / "scanner-config.json"
    config_file.write_text(json.dumps(config), encoding="utf-8")

    loaded = load_config(str(config_file))
    assert loaded["regras"][0]["_compiled"]
    assert loaded["github_org"] == "org"
