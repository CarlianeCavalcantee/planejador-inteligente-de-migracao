"""
Registry de plugins de linguagem.

Adicionar suporte a uma nova linguagem:
  1. Crie migrate/transformers/minhalinguagem.py com uma classe que herda LanguagePlugin.
  2. Importe e registre em _PLUGINS abaixo.
  3. Pronto — o transformer.py usa get_plugin() automaticamente.
"""

from __future__ import annotations

from migrate.transformers.base import LanguagePlugin, PluginResult
from migrate.transformers.java import JavaPlugin
from migrate.transformers.sql import SqlPlugin
from migrate.transformers.typescript import TypeScriptPlugin

_BASE = LanguagePlugin()

_PLUGINS: list[LanguagePlugin] = [
    JavaPlugin(),
    SqlPlugin(),
    TypeScriptPlugin(),
]

# Índice extensão → plugin
_EXT_INDEX: dict[str, LanguagePlugin] = {}
for _plugin in _PLUGINS:
    for _ext in _plugin.extensions:
        _EXT_INDEX[_ext] = _plugin


def get_plugin(filepath: str) -> LanguagePlugin:
    """Retorna o plugin adequado para o arquivo, ou o plugin base (no-op)."""
    from pathlib import Path
    ext = Path(filepath).suffix.lower()
    return _EXT_INDEX.get(ext, _BASE)
