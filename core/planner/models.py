"""
Modelos internos do planner.
Substituem dicionários soltos por estruturas com semântica clara.
"""
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Impact:
    id: str
    area: str
    repositorio: str
    componente: str
    complexidade: str
    prioridade: str
    fluxo: Optional[str]
    requer_compatibilidade_dual: bool
    chamadores_estimados: int
    arquivo_critico: bool


@dataclass
class RepoNode:
    modulo: str
    areas: frozenset
    total: int
    alta: int
    dual: int
    fluxos: frozenset = field(default_factory=frozenset)


@dataclass
class Trail:
    id: int
    repos: list
    carga_alta: int
    total_impactos: int
    fluxos_completos: list = field(default_factory=list)
    fluxos: list = field(default_factory=list)


@dataclass
class SimulationResult:
    n_trilhas: int
    desequilibrio_pct: int
    fluxos_partidos: int
    dias_estimados: float
    score: int
    recomendada: bool = False
