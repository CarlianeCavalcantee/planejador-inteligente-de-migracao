"""Testes para core/flow_validator.py — checks e status."""

from core.flow_validator import _build_result, _check_positive, _compute_status


_POSITIVE_CHECK = {
    "id": "CHK-007",
    "label": "Validacao compativel presente (DocumentoUtils ou [A-Z0-9]{14})",
    "patterns": [],
    "severity": "review",
    "is_positive": True,
}


def test_check_positive_passes_when_no_impacts():
    """Sem pontos no fluxo: check positivo não se aplica."""
    result = _check_positive(_POSITIVE_CHECK, [])
    assert result.passed is True
    assert result.is_positive is True


def test_check_positive_passes_when_compatible_present():
    impacts = [{"status_migracao": "compativel", "match": {}}]
    result = _check_positive(_POSITIVE_CHECK, impacts)
    assert result.passed is True


def test_check_positive_fails_when_only_pending_impacts():
    impacts = [
        {"status_migracao": "impacto", "match": {}},
        {"match": {"status_migracao": "impacto"}},
    ]
    result = _check_positive(_POSITIVE_CHECK, impacts)
    assert result.passed is False


def test_compute_status_aprovado_sem_review():
    assert _compute_status(100.0, critical=0, review=0, pending=0) == "APROVADO"


def test_compute_status_quase_pronto_com_review():
    assert _compute_status(100.0, critical=0, review=1, pending=0) == "QUASE PRONTO"


def test_build_result_zero_impacts_is_aprovado(cfg):
    result = _build_result("boleto", "Boleto", ["atualizabanco"], [], cfg)
    assert result.total_points == 0
    assert result.pending == 0
    assert result.review_failures == 0
    assert result.status == "APROVADO"
    positive = next(c for c in result.checks if c.is_positive)
    assert positive.passed is True
