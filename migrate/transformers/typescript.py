"""
Plugin TypeScript / JavaScript.

Por ora sem pós-processamento além das regras YAML.
Estrutura pronta para evoluir (ex: atualizar package.json de validators,
remover imports de libs de máscara substituídas, etc.).
"""

from __future__ import annotations

from migrate.transformers.base import LanguagePlugin, PluginResult


class TypeScriptPlugin(LanguagePlugin):
    extensions = {".ts", ".tsx", ".js", ".jsx"}

    def post_process(self, content: str, filepath: str, imports_pending: list[str]) -> PluginResult:
        return PluginResult(content=content)
