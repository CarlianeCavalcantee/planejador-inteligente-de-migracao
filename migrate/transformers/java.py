"""
Plugin Java/Kotlin.

Pós-processamento específico:
  1. Injeta imports solicitados pelas regras logo após o último import existente.
  2. Remove declarações de Pattern constants que foram substituídas por CnpjUtils
     e que agora ficaram sem uso (CNPJ_REMOVE_MASCARA, CNPJ_SEM_MASCARA, etc.).
"""

from __future__ import annotations

import re

from migrate.transformers.base import LanguagePlugin, PluginResult

# Patterns legados (numéricos) que podem ficar órfãos após a migração.
# NÃO inclui os nomes da CnpjUtils oficial (que são alfanuméricos e ficam na lib).
_LEGACY_PATTERNS = re.compile(
    r"^\s*private\s+static\s+final\s+Pattern\s+"
    r"(CNPJ_REMOVE_MASCARA_LEGADO|CNPJ_SEM_MASCARA_LEGADO|CNPJ_COM_MASCARA_LEGADO"
    r"|CNPJ_FORMATADOR_LEGADO"
    r"|CNPJ_PATTERN|CNPJ_REGEX|CNPJ_VALIDATOR|CNPJ_MASK_PATTERN"
    r"|CNPJ_UNMASK_PATTERN|CNPJ_FORMAT_PATTERN)"
    r"\s*=\s*compile\s*\([^)]+\)\s*;\s*$"
)

# Import legado do compile estático que pode ficar sem uso
_LEGACY_IMPORT = re.compile(
    r"^\s*import\s+static\s+java\.util\.regex\.Pattern\.compile\s*;\s*$"
)


def _inject_import(content: str, import_stmt: str) -> tuple[str, bool]:
    if import_stmt in content:
        return content, False
    lines = content.splitlines(keepends=True)
    last_import = -1
    for i, line in enumerate(lines):
        if line.strip().startswith("import "):
            last_import = i
    if last_import == -1:
        return content, False
    lines.insert(last_import + 1, import_stmt + "\n")
    return "".join(lines), True


def _uses_pattern_compile(content: str) -> bool:
    """Verifica se ainda há algum uso de compile() além das declarações legadas."""
    for line in content.splitlines():
        if _LEGACY_PATTERNS.match(line):
            continue
        if re.search(r"\bcompile\s*\(", line):
            return True
    return False


class JavaPlugin(LanguagePlugin):
    extensions = {".java", ".kt"}

    def post_process(self, content: str, filepath: str, imports_pending: list[str]) -> PluginResult:
        imports_added: list[str] = []
        notes: list[str] = []

        # 1. Injeta imports solicitados pelas regras
        for imp in imports_pending:
            content, added = _inject_import(content, imp)
            if added:
                imports_added.append(imp)

        # 2. Remove declarações de Pattern legadas que ficaram sem uso
        lines = content.splitlines(keepends=True)
        cleaned: list[str] = []
        removed_patterns: list[str] = []
        for line in lines:
            m = _LEGACY_PATTERNS.match(line)
            if m:
                removed_patterns.append(m.group(1))
                continue
            cleaned.append(line)

        if removed_patterns:
            content = "".join(cleaned)
            notes.append(
                f"Pattern constants removidas (substituidas por CnpjUtils): "
                + ", ".join(removed_patterns)
            )

            # 3. Remove import estático de compile se não há mais usos
            if not _uses_pattern_compile(content):
                content = "".join(
                    l for l in content.splitlines(keepends=True)
                    if not _LEGACY_IMPORT.match(l)
                )
                notes.append("Import 'import static java.util.regex.Pattern.compile' removido (sem uso).")

        return PluginResult(content=content, imports_added=imports_added, notes=notes)
