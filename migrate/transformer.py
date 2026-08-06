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

# ---------------------------------------------------------------------------
# Falsos positivos — espelhado de core/engine.py
# ---------------------------------------------------------------------------

_FP_COMMENT = re.compile(
    r"^\s*(?://|/\*|\*|#|<!--)"
)
_FP_IMPORT = re.compile(
    r"^\s*import\s"
)

# Propagação pura: não opera sobre o valor, apenas o transporta
_PURE_PROPAGATION = re.compile(
    r"""(?ix)
    ^\s*(?:private|public|protected|val|var|let|const|readonly)\s+\w+\s+\w+\s*;
    |^\s*return\s+(?:this\.)?\w+\s*;
    |^\s*(?:this\.)?\w+\s*=\s*(?:this\.)?\w+\s*;
    |^\s*[\w.]+\.get\w+\s*\(\s*\)\s*;
    |^\s*[\w.]+\.set\w+\s*\([^)]*\)\s*;
    |^\s*\.\w+\s*\([^)]*\)\s*$
    |^\s*[\w.]+\.put\s*\([^)]*\)\s*;
    |^\s*(?:public|private|protected)?\s*\w+\s+(?:get|set)\w+\s*\(
    """
)

# Campos sensíveis ao domínio do documento
_SENSITIVE_FIELD = re.compile(
    r"(?i)"
    r"(?:\b(cnpj|cpfCnpj|cpf_cnpj|taxId|tax_id|federalId|federal_id"
    r"|docNumber|doc_number|nrDoc|nr_doc|numDoc|num_doc"
    r"|documentoFederal|documento_federal|corporateId|corporate_id"
    r"|companyId|company_id|registrationNumber|registration_number"
    r"|documento|empresa|company)\b"
    r"|(?:get|set|is|has|with|find|fetch|load|save|update|build|map|to|from|by)"
    r"(?:Cnpj|CpfCnpj|Documento|Empresa|Company|TaxId|FederalId|DocNumber"
    r"|NrDoc|NumDoc|CorporateId|CompanyId|RegistrationNumber)\w*\s*\()"
)

# Operações claramente incompatíveis com CNPJ alfanumérico
_INCOMPATIBLE_OP = re.compile(
    r"(?i)"
    r"\.replaceAll\s*\(|\.replace\s*\(|\.replaceFirst\s*\("
    r"|\.substring\s*\(|\.substr\s*\(|\.slice\s*\(|\.charAt\s*\("
    r"|\.matches\s*\("
    r"|\.length\s*\(\s*\)\s*[=!<>]|\.length\s*[=!<>]"
    r"|\bLENGTH\s*\(\s*\w"
    r"|Long\.parseLong|Integer\.parseInt"
    r"|BigInteger\s*\(|BigDecimal\s*\("
    r"|\btoLong\s*\(|\btoInt\s*\(|\bparseInt\s*\(|Number\s*\("
    r"|Pattern\.compile|\bcompile\s*\(|new\s+RegExp"
    r"|/\^?\[0-9\]|/\^?\\d|\\d\{14\}|\[0-9\]\{14\}"
    r"|(?:validar|validate|check|calcular)(?:Cnpj|CpfCnpj|Documento|Document)"
    r"|validarCNPJ|validateCNPJ|isCpf\b|isCnpj\b"
    r"|@Pattern\s*\(|@Digits\b|@Size\s*\(|@Min\s*\(|@Max\s*\(|@CNPJ\b"
    r"|formataCNPJ|formatarCNPJ|maskCNPJ|unmaskCnpj|formatCNPJ"
    r"|\bCnpjUtils\s*\."
    r"|\bpadStart\s*\(|\bpadEnd\s*\(|\blpad\s*\(|\brpad\s*\("
    r"|StringUtils\.leftPad|StringUtils\.rightPad|CNPJ_FORMATADOR"
    r"|\[\^0-9\]|/\\D/g"
    r"|onlyNumbers|onlyDigits|digitsOnly|somenteNumeros|apenasNumeros"
    r"|\bNUMBER\s*\(|\bBIGINT\s*\(|\bNUMERIC\s*\("
    r"|VARCHAR\s*\(\s*1[0-9]|CHAR\s*\(\s*14"
    r"|@Column\s*\(|@Convert\s*\("
    r"|\bMD5\b|\bSHA256\b|DigestUtils|MessageDigest"
    r"|maxLength\s*:\s*14|pattern\s*:\s*['\"].*(?:\\d\{14\}|\[0-9\]\{14\})"
)


def _is_false_positive(line: str) -> bool:
    """Descarta linhas que não representam risco real de migração."""
    stripped = line.strip()
    if not stripped:
        return True
    if _FP_COMMENT.match(line) or _FP_IMPORT.match(line):
        return True
    if _PURE_PROPAGATION.match(line):
        return True
    # campo sensível presente mas nenhuma operação incompatível → propagação semântica
    if _SENSITIVE_FIELD.search(line) and not _INCOMPATIBLE_OP.search(line):
        return True
    return False

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
        replace_str = rule.get("replace") or ""
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
            if _is_false_positive(line):
                continue
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
