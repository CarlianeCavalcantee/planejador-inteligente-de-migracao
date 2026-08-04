"""
Transformer: aplica regras declarativas de migrate/rules.yaml nos arquivos.

Fluxo:
  1. Carrega regras do YAML
  2. Para cada arquivo, tenta cada regra compatível com a linguagem
  3. Regras 'auto' → aplica direto; 'review' → marca sem alterar
  4. Injeta imports Java ausentes
  5. Retorna TransformResult com patches aplicados e itens para revisão
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import yaml

from migrate.transformers import get_plugin

_RULES_PATH = Path(__file__).parent / "rules.yaml"

_EXT_TO_LANG: dict[str, str] = {
    ".java": "java", ".kt": "java",
    ".ts": "ts", ".tsx": "ts", ".js": "js", ".jsx": "js",
    ".sql": "sql",
    ".yaml": "any", ".yml": "any", ".json": "any", ".xml": "any",
    ".properties": "any",
}


@dataclass
class Patch:
    rule_id: str
    line: int
    original: str
    replacement: str
    confidence: Literal["auto", "review"]


@dataclass
class TransformResult:
    filepath: str
    original: str
    transformed: str
    patches: list[Patch] = field(default_factory=list)
    review_items: list[Patch] = field(default_factory=list)
    imports_added: list[str] = field(default_factory=list)

    @property
    def changed(self) -> bool:
        return self.original != self.transformed

    @property
    def auto_count(self) -> int:
        return sum(1 for p in self.patches if p.confidence == "auto")

    @property
    def review_count(self) -> int:
        return len(self.review_items)


@dataclass
class ScanStats:
    """Contadores globais de uma execução sobre um diretório."""
    projects: int = 0        # subdiretórios de primeiro nível (proxies de projetos)
    files_scanned: int = 0   # total de arquivos elegíveis visitados
    results: list[TransformResult] = field(default_factory=list)


def _load_rules() -> list[dict]:
    with open(_RULES_PATH, encoding="utf-8") as f:
        rules = yaml.safe_load(f) or []
    return sorted(rules, key=lambda r: r.get("priority", 50), reverse=True)


def _lang_for(filepath: str) -> str:
    ext = Path(filepath).suffix.lower()
    return _EXT_TO_LANG.get(ext, "any")


def _rule_applies(rule: dict, lang: str) -> bool:
    rule_lang = rule.get("language", "any")
    return rule_lang == "any" or rule_lang == lang


def transform_file(filepath: str, content: str, rules: list[dict] | None = None) -> TransformResult:
    """
    Aplica todas as regras compatíveis no conteúdo do arquivo.
    Regras 'auto' modificam o conteúdo; 'review' apenas registram.
    Após as regras, delega pós-processamento ao plugin da linguagem.
    """
    if rules is None:
        rules = _load_rules()

    lang = _lang_for(filepath)
    lines = content.splitlines(keepends=True)
    result_lines = list(lines)
    patches: list[Patch] = []
    review_items: list[Patch] = []
    imports_pending: list[str] = []  # coletados das regras, injetados pelo plugin

    for rule in rules:
        if not _rule_applies(rule, lang):
            continue

        pattern_str = rule.get("match", "")
        replace_str = rule.get("replace", "")
        confidence  = rule.get("confidence", "review")
        rule_id     = rule.get("id", "?")

        flags_str = rule.get("flags", "")
        flags = 0
        if "IGNORECASE" in flags_str:
            flags |= re.IGNORECASE
        if "MULTILINE" in flags_str:
            flags |= re.MULTILINE
        try:
            pat = re.compile(pattern_str, flags)
        except re.error:
            continue

        for i, line in enumerate(result_lines):
            if not pat.search(line):
                continue

            new_line = pat.sub(replace_str, line)
            patch = Patch(
                rule_id=rule_id,
                line=i + 1,
                original=line.rstrip("\n"),
                replacement=new_line.rstrip("\n"),
                confidence=confidence,
            )

            if confidence == "auto":
                result_lines[i] = new_line
                patches.append(patch)
                imp = rule.get("add_import")
                if imp and imp not in imports_pending:
                    imports_pending.append(imp)
            else:
                review_items.append(patch)

    # Delega pós-processamento (injeção de imports, limpeza, anotações) ao plugin
    plugin = get_plugin(filepath)
    plugin_result = plugin.post_process(
        content="".join(result_lines),
        filepath=filepath,
        imports_pending=imports_pending,
    )

    return TransformResult(
        filepath=filepath,
        original=content,
        transformed=plugin_result.content,
        patches=patches,
        review_items=review_items,
        imports_added=plugin_result.imports_added,
    )


_IGNORE_DIRS = {"node_modules", ".git", "dist", "build", "__pycache__", ".venv"}


def transform_directory(
    root: str,
    rules: list[dict] | None = None,
    dry_run: bool = False,
    extensions: set[str] | None = None,
) -> ScanStats:
    """
    Percorre `root` recursivamente e transforma todos os arquivos elegíveis.
    Se `dry_run=True`, não escreve nada em disco.
    Retorna ScanStats com contadores globais e lista de TransformResult.
    """
    if rules is None:
        rules = _load_rules()

    eligible_exts = extensions or set(_EXT_TO_LANG.keys())
    root_path = Path(root)
    stats = ScanStats()

    # Conta projetos: subdiretórios imediatos que contêm ao menos um arquivo elegível
    # (ou o próprio root se for um único projeto)
    top_dirs: set[str] = set()

    for path in root_path.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix.lower() not in eligible_exts:
            continue
        if set(path.parts) & _IGNORE_DIRS:
            continue

        stats.files_scanned += 1

        # Determina o "projeto" como o subdiretório imediato abaixo de root
        try:
            rel = path.relative_to(root_path)
            top = rel.parts[0] if len(rel.parts) > 1 else "."
        except ValueError:
            top = "."
        top_dirs.add(top)

        try:
            content = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue

        result = transform_file(str(path), content, rules)
        if result.changed or result.review_items:
            stats.results.append(result)
            if result.changed and not dry_run:
                path.write_text(result.transformed, encoding="utf-8")

    stats.projects = len(top_dirs)
    return stats
