"""
validator.py — detecta o build tool de cada repo clonado e executa os testes.

Suporte:
  Maven   : pom.xml          -> mvn test -q
  Gradle  : build.gradle(.kts) -> ./gradlew test  (ou gradlew.bat no Windows)
  npm/yarn: package.json     -> npm test / yarn test
  Python  : pytest.ini / pyproject.toml / setup.py -> pytest

Retorna ValidateResult por repo com status, saída e duração.
"""

from __future__ import annotations

import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ValidateResult:
    repo:     str
    tool:     str          # maven | gradle | npm | yarn | pytest | unknown
    success:  bool
    duration: float        # segundos
    output:   str          # stdout + stderr truncado
    skipped:  bool = False # True se nenhum build tool foi encontrado


def _run(cmd: list[str], cwd: str, timeout: int) -> tuple[int, str]:
    try:
        r = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
        return r.returncode, (r.stdout + r.stderr)[-4000:]  # últimas 4k chars
    except subprocess.TimeoutExpired:
        return -1, f"Timeout após {timeout}s"
    except FileNotFoundError as e:
        return -1, f"Comando não encontrado: {e}"


def _detect_tool(repo_path: Path) -> str:
    if (repo_path / "pom.xml").exists():
        return "maven"
    if (repo_path / "build.gradle").exists() or (repo_path / "build.gradle.kts").exists():
        return "gradle"
    if (repo_path / "package.json").exists():
        pkg = (repo_path / "package.json").read_text(encoding="utf-8", errors="ignore")
        return "yarn" if (repo_path / "yarn.lock").exists() else "npm"
    if any((repo_path / f).exists() for f in ("pytest.ini", "pyproject.toml", "setup.py")):
        return "pytest"
    return "unknown"


def _cmd_for(tool: str, repo_path: Path) -> list[str]:
    if tool == "maven":
        return ["mvn", "test", "-q", "--no-transfer-progress"]
    if tool == "gradle":
        wrapper = "gradlew.bat" if sys.platform == "win32" else "./gradlew"
        return [wrapper, "test", "--quiet"]
    if tool == "npm":
        return ["npm", "test", "--", "--watchAll=false"]
    if tool == "yarn":
        return ["yarn", "test", "--watchAll=false"]
    if tool == "pytest":
        return ["python", "-m", "pytest", "-q"]
    return []


def validate_repo(repo_path: str, timeout: int = 300) -> ValidateResult:
    """Detecta o build tool e executa os testes do repo."""
    path = Path(repo_path)
    repo = path.name
    tool = _detect_tool(path)

    if tool == "unknown":
        return ValidateResult(
            repo=repo, tool=tool, success=True,
            duration=0.0, output="Nenhum build tool detectado.",
            skipped=True,
        )

    cmd = _cmd_for(tool, path)
    t0 = time.monotonic()
    code, output = _run(cmd, cwd=str(path), timeout=timeout)
    duration = time.monotonic() - t0

    return ValidateResult(
        repo=repo,
        tool=tool,
        success=(code == 0),
        duration=round(duration, 1),
        output=output,
    )


def validate_directory(root: str, timeout: int = 300) -> list[ValidateResult]:
    """
    Valida cada subdiretório imediato de `root` que pareça um repo
    (contém ao menos um build file reconhecido).
    Se `root` em si for um repo único, valida diretamente.
    """
    root_path = Path(root)

    # Verifica se o próprio root é um repo
    if _detect_tool(root_path) != "unknown":
        return [validate_repo(root, timeout=timeout)]

    results = []
    for child in sorted(root_path.iterdir()):
        if not child.is_dir():
            continue
        if child.name.startswith("."):
            continue
        if _detect_tool(child) == "unknown":
            continue
        results.append(validate_repo(str(child), timeout=timeout))

    return results
