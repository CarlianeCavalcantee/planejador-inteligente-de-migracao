"""Testes para core/output.py"""

import pytest

from core.output import _calc_prioridade, build_output, generate_markdown


# ---------------------------------------------------------------------------
# _calc_prioridade
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("complexidade,critico,expected", [
    ("Alta", False, "P1"),
    ("Média", True, "P1"),
    ("Baixa", True, "P1"),
    ("Média", False, "P2"),
    ("Baixa", False, "P3"),
])
def test_calc_prioridade(complexidade, critico, expected):
    assert _calc_prioridade(complexidade, critico) == expected


# ---------------------------------------------------------------------------
# build_output
# ---------------------------------------------------------------------------

def test_build_output_structure(raw_impacts, cfg):
    output = build_output(raw_impacts, cfg, ["repo-a", "repo-b"])

    assert "matriz_impacto" in output
    assert "estatisticas" in output
    assert "ordem_migracao" in output
    assert "checklist_rollback" in output
    assert "parceiros_externos" in output
    assert "cobertura" in output
    assert "telas_qa" in output


def test_build_output_impact_count(raw_impacts, cfg):
    output = build_output(raw_impacts, cfg, ["repo-a", "repo-b"])
    stats = output["estatisticas"]
    assert stats["total_impactos_encontrados"] == len(raw_impacts)
    assert stats["total_repositorios_analisados"] == 2


def test_build_output_repos_sem_impacto(raw_impacts, cfg):
    output = build_output(raw_impacts, cfg, ["repo-a", "repo-b", "repo-c"])
    assert "repo-c" in output["cobertura"]["repositorios_sem_impacto"]


def test_build_output_ids_are_sequential(raw_impacts, cfg):
    output = build_output(raw_impacts, cfg, ["repo-a", "repo-b"])
    ids = [m["id"] for m in output["matriz_impacto"]]
    assert ids == ["IMP-0001", "IMP-0002"]


def test_build_output_preserves_status_pendente(raw_impacts, cfg):
    output = build_output(raw_impacts, cfg, ["repo-a", "repo-b"])
    for m in output["matriz_impacto"]:
        assert m["status"] == "pendente"


def test_build_output_complexidade_stats(raw_impacts, cfg):
    output = build_output(raw_impacts, cfg, ["repo-a", "repo-b"])
    compl = output["estatisticas"]["impactos_por_complexidade"]
    assert compl["Alta"] + compl["Média"] + compl["Baixa"] == len(raw_impacts)


def test_build_output_ordem_migracao_ordered_by_alta(raw_impacts, cfg):
    output = build_output(raw_impacts, cfg, ["repo-a", "repo-b"])
    ordem = output["ordem_migracao"]
    # repo-a tem impacto Alta, deve vir primeiro
    assert ordem[0]["modulo"] == "repo-a"


def test_build_output_checklist_rollback_has_base_items(raw_impacts, cfg):
    output = build_output(raw_impacts, cfg, ["repo-a", "repo-b"])
    for area, items in output["checklist_rollback"].items():
        assert len(items) >= 4  # pelo menos os 4 itens base


# ---------------------------------------------------------------------------
# generate_markdown
# ---------------------------------------------------------------------------

def test_generate_markdown_contains_key_sections(raw_impacts, cfg):
    output = build_output(raw_impacts, cfg, ["repo-a", "repo-b"])
    md = generate_markdown(output)

    assert "Matriz de Impacto" in md
    assert "Ordem de Migração" in md
    assert "Checklist de Rollback" in md
    assert "Riscos Mapeados" in md


def test_generate_markdown_contains_repo_names(raw_impacts, cfg):
    output = build_output(raw_impacts, cfg, ["repo-a", "repo-b"])
    md = generate_markdown(output)
    assert "repo-a" in md
    assert "repo-b" in md


def test_generate_markdown_is_string(raw_impacts, cfg):
    output = build_output(raw_impacts, cfg, ["repo-a", "repo-b"])
    md = generate_markdown(output)
    assert isinstance(md, str)
    assert len(md) > 100
