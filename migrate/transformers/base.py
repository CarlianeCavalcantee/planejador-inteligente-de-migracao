"""
Interface base para plugins de linguagem.

Cada plugin recebe o conteúdo já transformado pelas regras YAML e pode
aplicar pós-processamento específico da linguagem (injeção de imports,
formatação, validações estruturais, etc.).
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class PluginResult:
    content: str                  # conteúdo final após pós-processamento
    imports_added: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)  # avisos opcionais para o relatório


class LanguagePlugin:
    """Plugin base — comportamento padrão: não faz nada além de repassar o conteúdo."""

    # Extensões que este plugin atende (ex: {".java", ".kt"})
    extensions: set[str] = set()

    def post_process(self, content: str, filepath: str, imports_pending: list[str]) -> PluginResult:
        """
        Chamado após a aplicação das regras YAML.

        content          - conteúdo já com patches auto aplicados
        filepath         - caminho do arquivo (para contexto)
        imports_pending  - imports que as regras pediram para injetar
        """
        return PluginResult(content=content)
