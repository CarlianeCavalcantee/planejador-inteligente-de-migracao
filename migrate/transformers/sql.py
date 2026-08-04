"""
Plugin SQL.

Pós-processamento específico:
  - Linhas onde VARCHAR(14)/NUMBER(14) foram substituídas por VARCHAR(20)
    recebem um comentário inline sinalizando revisão obrigatória.
    Isso garante que o DBA veja exatamente o que mudou no diff.
"""

from __future__ import annotations

import re

from migrate.transformers.base import LanguagePlugin, PluginResult

_CHANGED_COL = re.compile(r"(?i)\bVARCHAR\s*\(\s*20\s*\)")
_ALREADY_MARKED = re.compile(r"--\s*CNPJ_MIGRATE")


class SqlPlugin(LanguagePlugin):
    extensions = {".sql"}

    def post_process(self, content: str, filepath: str, imports_pending: list[str]) -> PluginResult:
        lines = content.splitlines(keepends=True)
        result: list[str] = []
        annotated = 0

        for line in lines:
            if _CHANGED_COL.search(line) and not _ALREADY_MARKED.search(line):
                line = line.rstrip("\n") + "  -- CNPJ_MIGRATE: revisar tamanho e tipo\n"
                annotated += 1
            result.append(line)

        notes = [f"{annotated} coluna(s) SQL anotadas para revisao do DBA."] if annotated else []
        return PluginResult(content="".join(result), notes=notes)
